from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.nutrition.allergens import ALERGENICOS
from apps.core.permissions import user_can_access_store
from apps.nutrition.services.calculator import calculate_recipe, peso_total
from apps.nutrition.services.custo import custo_dos_itens, ficha_de_custo
from apps.nutrition.services.previa import montar as montar_previa

from apps.nutrition.models import (
    CAMPOS_DE_CUSTO, NutritionIngredient, ProductNutritionProfile, ProductRecipe, RecipeItem,
)
from apps.stores.models import Store, StoreProduct
from .permissions import ExigeAdicionalEtiqueta, lojas_liberadas
from .serializers import NutritionIngredientSerializer, ProductRecipeSerializer, ProductNutritionProfileSerializer


class NutritionIngredientViewSet(viewsets.ModelViewSet):
    serializer_class = NutritionIngredientSerializer
    permission_classes = (IsAuthenticated, ExigeAdicionalEtiqueta)
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("canonical_name", "display_name", "category", "source_code")
    ordering_fields = ("display_name", "category", "source")

    def get_queryset(self):
        qs = NutritionIngredient.objects.filter(is_active=True)
        qs = qs.filter(Q(store__isnull=True) | lojas_liberadas(self.request.user)).distinct()
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

    @action(detail=False, methods=["get"], url_path="pendentes")
    def pendentes(self, request):
        """Ingredientes EM USO em receita que ainda não tiveram alergênico revisado.

        Só os que estão em receita: revisar os 2.500 da base inteira seria
        trabalho sem consequência, porque só entra na etiqueta o que compõe um
        prato. É isso que transforma "51 pendências" em algo que acaba.
        """
        qs = self.get_queryset().filter(allergens_reviewed=False, recipe_items__isnull=False)
        loja = request.query_params.get("store")
        if loja:
            qs = qs.filter(Q(store_id=loja) | Q(store__isnull=True),
                           recipe_items__recipe__product__store_id=loja)
        return Response(NutritionIngredientSerializer(
            qs.distinct().order_by("display_name"), many=True).data)

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
        if not Store.objects.filter(Q(pk=loja_id) & (Q(owner=request.user) | Q(staff=request.user))).exists():
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
        # O preço também: a receita da loja aponta para a base, e o lojista
        # informa quanto paga no mesmo formulário em que adota.
        for campo in ("allergens", "may_contain", "allergens_reviewed",
                      "display_name", "category", *NUTRIENT_FIELDS, *CAMPOS_DE_CUSTO):
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
    permission_classes = (IsAuthenticated, ExigeAdicionalEtiqueta)
    def get_queryset(self):
        qs = ProductRecipe.objects.select_related("product", "product__store").prefetch_related("items__ingredient")
        qs = qs.filter(lojas_liberadas(self.request.user, "product__store__")).distinct()
        product = self.request.query_params.get("product")
        return qs.filter(product_id=product) if product else qs


    @action(detail=False, methods=["post"])
    def previa(self, request):
        """Calcula sem gravar, para a tela responder enquanto a pessoa digita.

        Mesmo cálculo do salvo: duas implementações divergiriam justamente
        onde dói, com o número visto na tela diferente do impresso.
        """
        dados = request.data or {}
        # Com o produto, a prévia devolve também a margem contra o preço dele.
        # O preço só sai para quem acessa a loja do produto (IDOR de leitura).
        preco = None
        if dados.get("product"):
            produto = _produto_acessivel(request.user, dados["product"])
            if produto is None:
                raise NotFound("Produto não encontrado.")
            preco = produto.price
        receita = montar_previa(
            itens_crus=dados.get("items") or [],
            serving_size_g=dados.get("serving_size_g", 100),
            prepared_weight_g=dados.get("prepared_weight_g"),
            physical_form=dados.get("physical_form", "solido"),
        )
        calculo = calculate_recipe(receita)
        return Response({**calculo, "custo": ficha_de_custo(calculo, preco)})


def _produto_acessivel(user, produto_id):
    try:
        produto = StoreProduct.objects.select_related("store").filter(pk=produto_id).first()
    except DjangoValidationError:  # id que não é UUID
        return None
    return produto if produto and user_can_access_store(user, produto.store) else None


class ProductNutritionProfileViewSet(viewsets.ModelViewSet):
    serializer_class = ProductNutritionProfileSerializer
    permission_classes = (IsAuthenticated, ExigeAdicionalEtiqueta)
    def get_queryset(self):
        qs = ProductNutritionProfile.objects.select_related("product", "recipe")
        qs = qs.filter(lojas_liberadas(self.request.user, "product__store__")).distinct()
        product = self.request.query_params.get("product")
        return qs.filter(product_id=product) if product else qs


class CustosDaLojaView(APIView):
    """Custo e margem de todo prato com receita, pior margem primeiro.

    É a lista que responde "onde estou perdendo dinheiro": o prato com CMV
    alto aparece no topo. Prato com ingrediente sem preço vai para o FIM,
    marcado — ordenar um custo incompleto junto dos outros o poria entre os
    de margem boa, e é margem que ele não tem.

    Escopo pela régua comum (`user_can_access_store`): dono, staff ou membro
    da equipe. Loja alheia responde 404 — confirmar que ela existe já é
    informação sobre o vizinho.
    """
    # Mesma porta das receitas: custo e margem nascem da receita, que é do adicional.
    permission_classes = (IsAuthenticated, ExigeAdicionalEtiqueta)

    def get(self, request):
        loja_id = request.query_params.get("store")
        if not loja_id:
            raise DRFValidationError({"store": "Informe a loja."})
        try:
            loja = Store.objects.filter(pk=loja_id).first()
        except DjangoValidationError:
            loja = None
        if loja is None or not user_can_access_store(request.user, loja):
            raise NotFound("Loja não encontrada.")

        receitas = (ProductRecipe.objects.filter(product__store=loja)
                    .select_related("product").prefetch_related("items__ingredient"))
        linhas = []
        for receita in receitas:
            itens = list(receita.items.all())
            custo = ficha_de_custo(
                custo_dos_itens(itens, peso_total(receita, itens), receita.serving_size_g),
                receita.product.price)
            linhas.append({
                "produto_id": str(receita.product_id),
                "produto": receita.product.name,
                **custo,
                "completo": custo["margem_bruta_pct"] is not None,
            })
        linhas.sort(key=lambda l: (not l["completo"], l["margem_bruta_pct"] or 0, l["produto"]))
        return Response(linhas)


class AlergenicosView(APIView):
    """Lista os grupos alergênicos da RDC 26/2015 para o painel montar a UI.

    Vem da API de propósito: repetir a lista legal em TypeScript garante que
    um dia as duas divirjam, e a que o lojista marca na tela é a que vale na
    etiqueta.
    """
    permission_classes = (IsAuthenticated, ExigeAdicionalEtiqueta)

    def get(self, request):
        return Response({
            "alergenicos": [
                {"valor": chave, "rotulo": rotulo, "gluten": gluten}
                for chave, (rotulo, gluten) in ALERGENICOS.items()
            ],
        })
