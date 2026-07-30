"""Multiplicador de fidelidade por produto (30/jul).

Caso real: "Combo Tilápia" (Cê Saladas) é UM produto que contém 4 saladas —
ficava fora da categoria qualificante e, mesmo se entrasse, valeria 1 selo.
`attributes['loyalty_units']` no produto resolve os dois lados:
- units > 0 → o produto qualifica EXPLICITAMENTE (ignora filtro de categoria)
  e cada unidade comprada vale `units` selos;
- sem o atributo → regra de categoria como sempre (1 selo por unidade).
"""
from types import SimpleNamespace
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store
from apps.stores.services.loyalty_service import LoyaltyService

User = get_user_model()


def _item(quantity=1, category_id=None, attributes=None, name='Produto'):
    product = SimpleNamespace(
        category_id=category_id,
        category=None,
        product_type=None,
        attributes=attributes or {},
        name=name,
    )
    return SimpleNamespace(
        product=product, product_name=name, variant_name='', options={}, quantity=quantity,
    )


class LoyaltyUnitsTest(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='dono-lu', password='x')
        self.store = Store.objects.create(name='Loja LU', slug='loja-lu', owner=owner, status='active')
        # Só a categoria de saladas avulsas qualifica (como na Cê Saladas)
        self.store.metadata = {'loyalty_qualifying_categories': ['cat-saladas']}
        self.store.save(update_fields=['metadata'])

    def test_combo_com_loyalty_units_conta_multiplicado(self):
        combo = _item(quantity=1, category_id='cat-combos',
                      attributes={'loyalty_units': 4}, name='Combo Tilápia')
        assert LoyaltyService.item_qualified_units(self.store, combo) == 4

    def test_loyalty_units_multiplica_pela_quantidade(self):
        combo = _item(quantity=2, category_id='cat-combos',
                      attributes={'loyalty_units': 3}, name='Combo Camarão')
        assert LoyaltyService.item_qualified_units(self.store, combo) == 6

    def test_loyalty_units_qualifica_mesmo_fora_da_categoria(self):
        # Sem o atributo, cat-combos não qualifica…
        sem_attr = _item(quantity=1, category_id='cat-combos', name='Combo Salmão')
        assert LoyaltyService.item_qualified_units(self.store, sem_attr) == 0
        # …com o atributo, qualifica explicitamente.
        com_attr = _item(quantity=1, category_id='cat-combos',
                         attributes={'loyalty_units': 2}, name='Combo Salmão')
        assert LoyaltyService.item_qualified_units(self.store, com_attr) == 2

    def test_item_comum_qualificante_continua_valendo_1_por_unidade(self):
        salada = _item(quantity=3, category_id='cat-saladas', name='Tilápia Suprema')
        assert LoyaltyService.item_qualified_units(self.store, salada) == 3

    def test_loyalty_units_invalido_cai_na_regra_de_categoria(self):
        ruim = _item(quantity=2, category_id='cat-saladas',
                     attributes={'loyalty_units': 'abc'}, name='Salada X')
        assert LoyaltyService.item_qualified_units(self.store, ruim) == 2
        ruim_fora = _item(quantity=2, category_id='cat-combos',
                          attributes={'loyalty_units': 0}, name='Combo Y')
        assert LoyaltyService.item_qualified_units(self.store, ruim_fora) == 0
