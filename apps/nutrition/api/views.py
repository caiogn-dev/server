from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.nutrition.allergens import ALERGENICOS
from apps.nutrition.services.calculator import calculate_recipe
from apps.nutrition.services.previa import montar as montar_previa

from apps.nutrition.models import NutritionIngredient, ProductRecipe, ProductNutritionProfile, RecipeItem
from apps.stores.models import Store
from .serializers import NutritionIngredientSerializer, ProductRecipeSerializer, ProductNutritionProfileSerializer


def stores_for(user):
    return Q(store__owner=user) | Q(store__staff=user)


class NutritionIngredientViewSet(viewsets.ModelViewSet):
    serializer_class = NutritionIngredientSerializer
    permission_classes = (IsAuthenticated,)
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("canonical_name", "display_name", "category", "source_code")
    ordering_fields = ("display_name", "category", "source")

    def get_queryset(self):
        qs = NutritionIngredient.objects.filter(is_active=True)
        if not self.request.user.is_superuser:
            qs = qs.filter(Q(store__isnull=True) | stores_for(self.request.user)).distinct()
        store = self.request.query_params.get("store")
        category = self.request.query_params.get("category")
        # `escopo` separa o que é da loja do catálogo oficial. Sem isso os ~70
        # ingredientes do lojista ficam espalhados em ordem alfabética no meio
        # de 2.555 alimentos de TACO e POF, e a tela dele mostra um punhado ao
        # acaso — foi o que aconteceu quando a base pública cresceu.
        escopo = self.request.query_params.get("escopo")
        if escopo == "loja":
            qs = qs.filter(store_id=store) if store else qs.filter(store__isnull=False)
        elif escopo == "base":
            qs = qs.filter(store__isnull=True)
        elif store:
            qs = qs.filter(Q(store__isnull=True) | Q(store_id=store))
        if category:
            qs = qs.filter(category=category)
        return qs

    @action(detail=True, methods=["post"])
    def adotar(self, request, pk=None):
        """Cria uma cópia do alimento oficial dentro da loja e adota-a.

        As receitas da loja apontam direto para a base pública, então copiar
        sem repontuar deixaria a cópia órfã e a receita continuaria presa no
        original que ela não pode editar. Repontuar só os itens DESTA loja: a
        receita de outra continua no oficial, que é o certo.

        A REVISÃO PODE VIR NO MESMO POST. É o que faz a tela funcionar em um
        clique: o lojista abre o alimento dentro da receita, marca o que contém
        e salva uma vez. Sem isso a cópia nasce não revisada, a etiqueta segue
        se recusando a declarar alergênico, e o botão "revisar" continua sem
        efeito visível — que era o bug original.
        """
        from apps.nutrition.models import NUTRIENT_FIELDS

        original = self.get_object()
        if original.store_id is not None:
            return Response({"detail": "Este ingrediente já é da sua loja."}, status=400)

        loja_id = request.data.get("store")
        if not loja_id:
            return Response({"detail": "Informe a loja que vai adotar o ingrediente."}, status=400)
        if not Store.objects.filter(Q(pk=loja_id) & (Q(owner=request.user) | Q(staff=request.user))).exists() \
                and not request.user.is_superuser:
            raise PermissionDenied("Loja não pertence a você.")

        copia = NutritionIngredient.objects.filter(
            store_id=loja_id, canonical_name=original.canonical_name,
            preparation_state=original.preparation_state).first()
        criada = copia is None
        if criada:
            copia = NutritionIngredient.objects.get(pk=original.pk)
            copia.pk = None
            copia.store_id = loja_id
            # A cópia nasce não revisada de propósito: adotar é dizer "quero
            # cuidar deste", não "já conferi". Quem já conferiu diz isso no
            # payload, logo abaixo.
            copia.allergens_reviewed = False
            copia.notes = (f"{original.notes}\nCópia de {original.get_source_display()} "
                           f"#{original.source_code} adotada pela loja para revisão própria.").strip()

        # O que o formulário mandou vence a cópia crua. Adotar de novo é a via
        # de reeditar: o unique (store, canonical_name, preparation_state)
        # proíbe uma segunda cópia, então a mesma linha é atualizada.
        for campo in ("allergens", "may_contain", "allergens_reviewed",
                      "display_name", "category", *NUTRIENT_FIELDS):
            if campo in request.data:
                setattr(copia, campo, request.data[campo])

        try:
            copia.full_clean(exclude=("store",))
        except DjangoValidationError as erro:
            # Sem traduzir, um alergênico fora da RDC 26 virava 500 e a tela
            # mostrava "erro interno" no lugar do campo errado.
            raise DRFValidationError(erro.message_dict)
        copia.save()

        repontuados = RecipeItem.objects.filter(
            ingredient=original, recipe__product__store_id=loja_id).update(ingredient=copia)

        return Response(
            {**NutritionIngredientSerializer(copia).data, "itens_repontuados": repontuados},
            status=status.HTTP_201_CREATED if criada else status.HTTP_200_OK,
        )

    def perform_destroy(self, instance):
        if instance.store_id is None and not self.request.user.is_superuser:
            raise PermissionDenied("Ingredientes oficiais globais são somente leitura.")
        instance.is_active = False
        instance.save(update_fields=("is_active", "updated_at"))


class ProductRecipeViewSet(viewsets.ModelViewSet):
    serializer_class = ProductRecipeSerializer
    permission_classes = (IsAuthenticated,)
    def get_queryset(self):
        qs = ProductRecipe.objects.select_related("product", "product__store").prefetch_related("items__ingredient")
        if not self.request.user.is_superuser:
            qs = qs.filter(Q(product__store__owner=self.request.user) | Q(product__store__staff=self.request.user)).distinct()
        product = self.request.query_params.get("product")
        return qs.filter(product_id=product) if product else qs


    @action(detail=False, methods=["post"])
    def previa(self, request):
        """Calcula sem gravar, para a tela responder enquanto a pessoa digita.

        Mesmo cálculo do salvo: duas implementações divergiriam justamente
        onde dói, com o número visto na tela diferente do impresso.
        """
        dados = request.data or {}
        receita = montar_previa(
            itens_crus=dados.get("items") or [],
            serving_size_g=dados.get("serving_size_g", 100),
            prepared_weight_g=dados.get("prepared_weight_g"),
            physical_form=dados.get("physical_form", "solido"),
        )
        return Response(calculate_recipe(receita))


class ProductNutritionProfileViewSet(viewsets.ModelViewSet):
    serializer_class = ProductNutritionProfileSerializer
    permission_classes = (IsAuthenticated,)
    def get_queryset(self):
        qs = ProductNutritionProfile.objects.select_related("product", "recipe")
        if not self.request.user.is_superuser:
            qs = qs.filter(Q(product__store__owner=self.request.user) | Q(product__store__staff=self.request.user)).distinct()
        product = self.request.query_params.get("product")
        return qs.filter(product_id=product) if product else qs


class AlergenicosView(APIView):
    """Lista os grupos alergênicos da RDC 26/2015 para o painel montar a UI.

    Vem da API de propósito: repetir a lista legal em TypeScript garante que
    um dia as duas divirjam, e a que o lojista marca na tela é a que vale na
    etiqueta.
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        return Response({
            "alergenicos": [
                {"valor": chave, "rotulo": rotulo, "gluten": gluten}
                for chave, (rotulo, gluten) in ALERGENICOS.items()
            ],
        })
