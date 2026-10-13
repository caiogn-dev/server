"""O que o SERVIDOR cobra com salada grátis + cupom, saladas avulsas.

13/10, Cê Saladas — o dono testou no celular: Especial Filé (39,99) + Magnifico
Camarão (48,99), cupom NUTRI.TANIA (5%) e a salada grátis marcada. A tela dizia
"Item grátis aplicada! −R$ 0,00" e total R$ 84,53.

A causa estava no storefront (o item da sacola não traz categoria e a
estimativa da grátis zerava toda salada avulsa). Este teste trava o lado do
dinheiro: o servidor SEMPRE abateu — cupom sobre o subtotal cheio, grátis =
salada qualificante mais barata, os dois somados — e é esse número que a tela
precisa mostrar.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.stores.models import (
    Store, StoreCartItem, StoreCategory, StoreCoupon, StoreLoyaltyAccount, StoreProduct,
)
from apps.stores.services import cart_service, checkout_service
from apps.stores.services.checkout_service import CheckoutService

User = get_user_model()


class GratisAvulsaComCupomTest(TestCase):
    def setUp(self):
        self.cliente = User.objects.create_user(
            username='cliente-gratis-cupom', email='gratis.cupom@example.com', password='x',
        )
        dono = User.objects.create_user(username='dono-gratis-cupom', password='x')
        self.loja = Store.objects.create(
            owner=dono, name='Cê', slug='ce-gratis-cupom',
            store_type=Store.StoreType.FOOD, status=Store.StoreStatus.ACTIVE, currency='BRL',
        )
        saladas = StoreCategory.objects.create(store=self.loja, name='Saladas Especiais', slug='saladas')
        combos = StoreCategory.objects.create(store=self.loja, name='Combos Especiais', slug='combos-especiais')
        self.loja.metadata = {
            'loyalty_enabled': True,
            'loyalty_salads_required': 10,
            'loyalty_qualifying_categories': [str(saladas.id), str(combos.id)],
        }
        self.loja.save(update_fields=['metadata'])
        self.especial = StoreProduct.objects.create(
            store=self.loja, category=saladas, name='Especial Filé de Frango',
            slug='especial-file', price=Decimal('39.99'), status=StoreProduct.ProductStatus.ACTIVE,
            track_stock=False,
        )
        self.magnifico = StoreProduct.objects.create(
            store=self.loja, category=saladas, name='Magnifico Camarão',
            slug='magnifico-camarao', price=Decimal('48.99'), status=StoreProduct.ProductStatus.ACTIVE,
            track_stock=False,
        )
        StoreCoupon.objects.create(
            store=self.loja, code='NUTRI.TANIA',
            discount_type=StoreCoupon.DiscountType.PERCENTAGE, discount_value=Decimal('5'),
            is_active=True, valid_from=timezone.now() - timedelta(days=1),
            valid_until=timezone.now() + timedelta(days=365),
        )
        # 10 carimbos = 1 grátis disponível (conta existente: sem backfill).
        StoreLoyaltyAccount.objects.create(store=self.loja, user=self.cliente, qualified_count=10)
        self.carrinho = cart_service.get_or_create_cart(self.loja, user=self.cliente, session_key=None)
        StoreCartItem.objects.create(cart=self.carrinho, product=self.especial, quantity=1)
        StoreCartItem.objects.create(cart=self.carrinho, product=self.magnifico, quantity=1)

    def _fechar(self, **extra):
        return checkout_service.create_order(
            cart=self.carrinho,
            customer_data={'name': 'Dono Testando', 'email': self.cliente.email, 'phone': '61999990000'},
            delivery_data={'method': 'pickup', 'address': {}, 'notes': ''},
            payment_method='pix',
            **extra,
        )

    def test_salada_avulsa_qualifica_pela_categoria_do_produto(self):
        self.assertEqual(
            CheckoutService._cart_salad_discount(self.carrinho), Decimal('39.99'),
        )

    def test_cupom_e_gratis_somam_e_o_total_e_44_54(self):
        pedido = self._fechar(coupon_code='NUTRI.TANIA', use_loyalty_reward=True)

        self.assertEqual(pedido.subtotal, Decimal('88.98'))
        # 4,449 do cupom (5% do subtotal CHEIO) + 39,99 da grátis = 44,439 → 44,44.
        self.assertEqual(pedido.discount, Decimal('44.44'))
        self.assertEqual(pedido.total, Decimal('44.54'))
        self.assertEqual(pedido.coupon_code, 'NUTRI.TANIA')
        self.assertTrue(pedido.metadata['loyalty_reward']['applied'])
        self.assertEqual(pedido.metadata['loyalty_reward']['discount'], 39.99)

    def test_sem_a_gratis_o_total_e_o_que_a_tela_mostrava(self):
        # R$ 84,53 é o total SEM a grátis — era o que a tela exibia com o cartão
        # marcado. Ou seja: a tela errava para MAIS, o servidor nunca cobrou isso
        # com a grátis pedida.
        pedido = self._fechar(coupon_code='NUTRI.TANIA', use_loyalty_reward=False)
        self.assertEqual(pedido.total, Decimal('84.53'))
