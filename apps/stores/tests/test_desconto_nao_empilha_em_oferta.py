"""26/11: item já em oferta ("de R$ 39,99 por R$ 20,00") ganhou cupom 5% + retirada 20%
por cima. Regra do dono: cupom e desconto de retirada NÃO valem em item que já está em oferta.

"Em oferta" = product.preco_de_referencia() não é None (promoção do dia ativa OU
compare_at_price acima do preço vigente).
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.stores.models import Store, StoreCategory, StoreCoupon, StoreProduct
from apps.stores.services.cart_service import CartService
from apps.stores.services.checkout_service import CheckoutService

User = get_user_model()


class DescontoNaoEmpilhaEmOfertaTest(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dono-oferta', password='x')
        self.store = Store.objects.create(name='Loja', slug='loja-oferta', owner=dono, status='active',
                                          metadata={'desconto_retirada': {'ativo': True, 'percentual': 20}})
        cat = StoreCategory.objects.create(store=self.store, name='Saladas', slug='saladas')
        self.oferta = StoreProduct.objects.create(
            store=self.store, category=cat, name='Sobra', slug='sobra', price=Decimal('20.00'),
            compare_at_price=Decimal('39.99'), is_active=True, track_stock=False)
        self.normal = StoreProduct.objects.create(
            store=self.store, category=cat, name='Normal', slug='normal', price=Decimal('40.00'),
            is_active=True, track_stock=False)
        StoreCoupon.objects.create(store=self.store, code='VIP5', discount_type='percentage',
                                   discount_value=Decimal('5'), is_active=True,
                                   valid_from=timezone.now() - timezone.timedelta(days=1),
                                   valid_until=timezone.now() + timezone.timedelta(days=1))

    def _pedido(self, itens, cupom=''):
        carrinho = CartService.get_or_create_cart(self.store, None, 'cart-oferta')
        for produto, qtd in itens:
            CartService.add_product(carrinho, produto, qtd)
        return CheckoutService.create_order(
            cart=carrinho, customer_data={'name': 'Cliente', 'phone': '5563900000001'},
            delivery_data={'method': 'pickup'}, coupon_code=cupom,
        )

    def test_so_item_em_oferta_nao_ganha_cupom_nem_retirada(self):
        pedido = self._pedido([(self.oferta, 3)], cupom='VIP5')
        self.assertEqual(pedido.subtotal, Decimal('60.00'))
        self.assertEqual(pedido.discount, Decimal('0.00'))
        self.assertEqual(pedido.total, Decimal('60.00'))

    def test_misto_desconta_so_o_item_normal(self):
        pedido = self._pedido([(self.oferta, 1), (self.normal, 1)], cupom='VIP5')
        # cupom: 5% de 40 = 2,00; retirada: 20% de (40 - 2) = 7,60
        self.assertEqual(pedido.discount, Decimal('9.60'))
        self.assertEqual(pedido.total, Decimal('50.40'))

    def test_validar_cupom_ja_mostra_zero_para_sacola_em_oferta(self):
        carrinho = CartService.get_or_create_cart(self.store, None, 'cart-oferta-v')
        CartService.add_product(carrinho, self.oferta, 2)
        r = CheckoutService.validate_coupon(self.store, 'VIP5', Decimal('40.00'),
                                            items=CheckoutService._coupon_items(carrinho))
        self.assertTrue(r['valid'])
        self.assertEqual(r['discount'], 0.0)

    def test_sacola_marca_item_em_oferta(self):
        from apps.stores.api.serializers import StoreCartSerializer
        carrinho = CartService.get_or_create_cart(self.store, None, 'cart-oferta-s')
        CartService.add_product(carrinho, self.oferta, 1)
        CartService.add_product(carrinho, self.normal, 1)
        dados = StoreCartSerializer(carrinho).data
        por_nome = {i['product_name']: i['em_oferta'] for i in dados['items']}
        self.assertEqual(por_nome, {'Sobra': True, 'Normal': False})
