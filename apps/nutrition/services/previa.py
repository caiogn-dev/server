"""
Cálculo de receita sem gravar nada.

A tela monta a receita mexendo em gramas, e os números da porção precisam
acompanhar enquanto a pessoa digita. Salvar a cada tecla encheria o banco de
versões intermediárias — e pior, mudaria a etiqueta de um produto que está no
ar enquanto alguém ainda está experimentando proporção.

Então a prévia monta objetos de mentira com a mesma forma que `calculate_recipe`
espera, e o cálculo é exatamente o mesmo código do salvo. Duas implementações
divergiriam, e a divergência apareceria justamente onde dói: o número que a
pessoa viu na tela não seria o impresso.
"""
from decimal import Decimal, InvalidOperation

from apps.nutrition.models import NutritionIngredient


class _Itens:
    """Imita o manager de itens: `.select_related(...).all()`."""

    def __init__(self, itens):
        self._itens = itens

    def select_related(self, *_args, **_kwargs):
        return self

    def all(self):
        return self._itens

    def __iter__(self):
        return iter(self._itens)


class _Item:
    def __init__(self, ingredient, quantity_g, prepared_quantity_g=None):
        self.ingredient = ingredient
        self.quantity_g = quantity_g
        self.prepared_quantity_g = prepared_quantity_g


class _Receita:
    def __init__(self, itens, serving_size_g, prepared_weight_g, profile):
        self.items = _Itens(itens)
        self.serving_size_g = serving_size_g
        self.prepared_weight_g = prepared_weight_g
        self.profile = profile


class _Perfil:
    def __init__(self, physical_form):
        self.physical_form = physical_form


def _decimal(valor, padrao=None):
    if valor in (None, ""):
        return padrao
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return padrao


def montar(itens_crus, serving_size_g=100, prepared_weight_g=None, physical_form="solido"):
    """Monta a receita de mentira a partir do payload da tela.

    Ingrediente inexistente ou quantidade não positiva é ignorado em silêncio:
    a prévia roda enquanto a pessoa digita, e uma linha ainda pela metade não é
    erro, é trabalho em andamento.
    """
    ids = [i.get("ingredient") for i in itens_crus if i.get("ingredient")]
    por_id = {str(i.id): i for i in NutritionIngredient.objects.filter(id__in=ids)}

    itens = []
    for cru in itens_crus:
        ingrediente = por_id.get(str(cru.get("ingredient")))
        quantidade = _decimal(cru.get("quantity_g"))
        if not ingrediente or quantidade is None or quantidade <= 0:
            continue
        itens.append(_Item(ingrediente, quantidade, _decimal(cru.get("prepared_quantity_g"))))

    return _Receita(
        itens=itens,
        serving_size_g=_decimal(serving_size_g, Decimal("100")) or Decimal("100"),
        prepared_weight_g=_decimal(prepared_weight_g),
        profile=_Perfil(physical_form or "solido"),
    )
