from django.db.models import Q
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.nutrition.allergens import ALERGENICOS
from apps.nutrition.services.calculator import calculate_recipe
from apps.nutrition.services.previa import montar as montar_previa

from apps.nutrition.models import NutritionIngredient, ProductRecipe, ProductNutritionProfile
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
        """Copia um alimento oficial (TACO/POF) para dentro da loja.

        O catálogo oficial é compartilhado entre todos os lojistas e por isso é
        somente leitura. Só que a etiqueta se recusa a declarar alergênico
        enquanto houver ingrediente não revisado na receita — e o lojista não
        podia revisar nenhum alimento oficial. As 27 receitas em produção
        ficaram assim: travadas, com um botão de revisar que só sabia dar 400.

        Adotar cria uma cópia editável na loja (com a procedência preservada),
        aplica a revisão de alergênicos que veio no mesmo POST e reaponta as
        receitas DAQUELA loja para a cópia. O oficial fica intocado.
        """
        from django.core.exceptions import ValidationError as DjangoValidationError
        from django.db import transaction
        from rest_framework import status
        from rest_framework.exceptions import ValidationError as DRFValidationError

        from apps.nutrition.models import NUTRIENT_FIELDS, RecipeItem
        from apps.stores.models import Store

        oficial = self.get_object()
        if oficial.store_id is not None:
            raise DRFValidationError(
                "Este ingrediente já é da loja — edite direto, não há o que adotar."
            )

        store_id = request.data.get("store")
        store = Store.objects.filter(id=store_id).first() if store_id else None
        if not store:
            raise DRFValidationError({"store": "Informe a loja que vai adotar o alimento."})
        user = request.user
        if not (user.is_superuser or store.owner_id == user.id
                or store.staff.filter(id=user.id).exists()):
            raise DRFValidationError({"store": "Loja não autorizada."})

        campos_copiados = (
            "canonical_name", "display_name", "category", "preparation_state",
            "default_unit", "density_g_ml", "source", "source_code",
            "source_edition", "source_reference", "source_accessed_at", "notes",
            "allergens", "may_contain", "allergens_reviewed", *NUTRIENT_FIELDS,
        )
        valores = {campo: getattr(oficial, campo) for campo in campos_copiados}

        # A revisão de alergênicos pode vir junto: o lojista clica no alimento,
        # marca o que contém e salva uma vez só.
        for campo in ("allergens", "may_contain", "allergens_reviewed",
                      "display_name", "category", *NUTRIENT_FIELDS):
            if campo in request.data:
                valores[campo] = request.data[campo]

        with transaction.atomic():
            copia, criada = NutritionIngredient.objects.get_or_create(
                store=store,
                canonical_name=valores["canonical_name"],
                preparation_state=valores["preparation_state"],
                defaults=valores,
            )
            if not criada:
                # Adotar de novo é a via de reeditar: aplica o que veio agora
                # sem criar uma segunda cópia (o unique da loja proibiria).
                for campo, valor in valores.items():
                    setattr(copia, campo, valor)
                copia.is_active = True
            try:
                copia.full_clean(exclude=("store",))
            except DjangoValidationError as erro:
                # Sem traduzir, um alergênico fora da RDC 26 virava 500 e a
                # tela mostrava "erro interno" no lugar do campo errado.
                raise DRFValidationError(erro.message_dict)
            copia.save()

            # Sem reapontar, a cópia nasce órfã e a etiqueta segue travada.
            RecipeItem.objects.filter(
                ingredient=oficial, recipe__product__store=store,
            ).update(ingredient=copia)

        dados = self.get_serializer(copia).data
        return Response(
            dados,
            status=status.HTTP_201_CREATED if criada else status.HTTP_200_OK,
        )

    def perform_destroy(self, instance):
        if instance.store_id is None and not self.request.user.is_superuser:
            from rest_framework.exceptions import PermissionDenied
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
