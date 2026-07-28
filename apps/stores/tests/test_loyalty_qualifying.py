from types import SimpleNamespace
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store
from apps.stores.services.loyalty_service import LoyaltyService

User = get_user_model()


def _item(category_id=None, product_name=''):
    # `_is_salad_order_item` (heurística legada, sem config) acessa
    # product.category/product_type como objetos (não só o _id) — adaptação
    # pontual do fixture do brief para casar com o código real.
    product = SimpleNamespace(category_id=category_id, category=None, product_type=None)
    return SimpleNamespace(
        product=product, product_name=product_name, variant_name='',
        options={}, quantity=1,
    )


class LoyaltyQualifyingTest(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='dono', password='x')
        self.store = Store.objects.create(name='Loja', slug='loja-q', owner=owner, status='active')

    def test_sem_config_usa_heuristica_salada(self):
        assert LoyaltyService.order_item_qualifies(self.store, _item(product_name='Salada Caesar')) is True
        assert LoyaltyService.order_item_qualifies(self.store, _item(product_name='Suco de Uva')) is False

    def test_com_config_categoria_listada_qualifica(self):
        self.store.metadata = {'loyalty_qualifying_categories': ['cat-1']}
        self.store.save(update_fields=['metadata'])
        assert LoyaltyService.order_item_qualifies(self.store, _item(category_id='cat-1', product_name='Suco de Uva')) is True

    def test_com_config_categoria_fora_nao_qualifica_mesmo_sendo_salada(self):
        self.store.metadata = {'loyalty_qualifying_categories': ['cat-1']}
        self.store.save(update_fields=['metadata'])
        assert LoyaltyService.order_item_qualifies(self.store, _item(category_id='cat-2', product_name='Salada Caesar')) is False
