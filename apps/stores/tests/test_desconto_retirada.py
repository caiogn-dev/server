"""Black Friday 26/11 (Cê Saladas): pedido de RETIRADA ganha X% no total.

Mora em store.metadata['desconto_retirada'] = {ativo, percentual, inicio?, fim?}.
O cardápio recebe o bloco para mostrar e somar igual ao servidor.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store, StoreCategory, StoreProduct
from apps.stores.services.cart_service import CartService
from apps.stores.services.checkout_service import CheckoutService
from apps.stores.services.desconto_retirada import desconto_da_retirada, promocao_para_vitrine

User = get_user_model()


class DescontoNaRetiradaTest(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dono-retirada', password='x')
        self.store = Store.objects.create(name='Cê', slug='ce-retirada', owner=dono, status='active',
                                          metadata={'desconto_retirada': {'ativo': True, 'percentual': 20}})
        cat = StoreCategory.objects.create(store=self.store, name='Saladas', slug='saladas')
        self.produto = StoreProduct.objects.create(store=self.store, category=cat, name='Salada', slug='salada',
                                                   price=Decimal('39.99'), is_active=True, track_stock=False)

    def _pedido(self, metodo):
        carrinho = CartService.get_or_create_cart(self.store, None, f'cart-ret-{metodo}')
        CartService.add_product(carrinho, self.produto, 2)
        dados = {'method': metodo}
        if metodo == 'delivery':
            dados['address'] = {'street': 'Rua', 'lat': -10.18, 'lng': -48.33}
        return CheckoutService.create_order(
            cart=carrinho, customer_data={'name': 'Ana', 'phone': '5563999990000'},
            delivery_data=dados, trusted_delivery_fee=Decimal('0') if metodo == 'delivery' else None,
        )

    def test_retirada_ganha_20_por_cento_no_total(self):
        pedido = self._pedido('pickup')
        self.assertEqual(pedido.subtotal, Decimal('79.98'))
        self.assertEqual(pedido.discount, Decimal('16.00'))
        self.assertEqual(pedido.total, Decimal('63.98'))
        self.assertEqual(Decimal(pedido.metadata['desconto_retirada']), Decimal('16.00'))

    def test_desligado_nao_da_desconto(self):
        self.store.metadata = {'desconto_retirada': {'ativo': False, 'percentual': 20}}
        self.store.save(update_fields=['metadata'])
        self.assertEqual(self._pedido('pickup').discount, Decimal('0.00'))

    def test_fora_da_janela_nao_vale(self):
        promo = {'ativo': True, 'percentual': 20, 'fim': '2020-01-01T00:00:00-03:00'}
        self.store.metadata = {'desconto_retirada': promo}
        self.assertEqual(desconto_da_retirada(self.store, Decimal('100'), 'pickup'), Decimal('0'))
        self.assertIsNone(promocao_para_vitrine(self.store))

    def test_entrega_nao_ganha(self):
        self.assertEqual(desconto_da_retirada(self.store, Decimal('100'), 'delivery'), Decimal('0'))

    def test_vitrine_recebe_o_percentual(self):
        self.assertEqual(promocao_para_vitrine(self.store), {'percentual': 20.0})
