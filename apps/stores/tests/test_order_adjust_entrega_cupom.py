"""Edição do pedido no painel: entrega/retirada, endereço e cupom.

27/10, Carlos (CE-2610277336): o bot marcou ENTREGA para quem ia retirar, e o
manipulador de pedidos não tinha como trocar no painel — nem endereço, nem
cupom. A edição só cobria itens, desconto, acréscimo e taxa.
"""
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder, StoreOrderItem, StoreProduct
from apps.stores.models.coupon import StoreCoupon

User = get_user_model()


class AjusteDeEntregaECupomTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='oe', email='oe@x.com', password='x')
        self.store = Store.objects.create(name='LE', slug='le', owner=self.owner, status='active')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=self.owner).key}')
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='Carlos', customer_phone='6300000000',
            subtotal=Decimal('50.00'), delivery_fee=Decimal('8.00'), total=Decimal('58.00'),
            delivery_method='delivery',
            delivery_address={'raw_address': 'Retirada na loja', 'lat': -10.2, 'lng': -48.3},
        )
        p = StoreProduct.objects.create(
            store=self.store, name='P', slug='p', price=Decimal('50.00'),
            track_stock=False, stock_quantity=0, status=StoreProduct.ProductStatus.ACTIVE,
        )
        StoreOrderItem.objects.create(
            order=self.order, product=p, product_name='P', sku='',
            unit_price=Decimal('50.00'), quantity=1, subtotal=Decimal('50.00'),
        )
        self.url = f'/api/v1/stores/{self.store.slug}/orders/{self.order.id}/adjust/'

    def _post(self, corpo):
        r = self.client.post(self.url, corpo, format='json')
        self.order.refresh_from_db()
        return r

    def test_trocar_para_retirada_zera_frete_e_tira_o_endereco(self):
        r = self._post({'delivery_method': 'pickup'})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.order.delivery_method, 'pickup')
        self.assertEqual(self.order.delivery_fee, Decimal('0.00'))
        self.assertEqual(self.order.total, Decimal('50.00'))
        self.assertFalse(self.order.delivery_address.get('lat'))

    def test_trocar_para_entrega_com_endereco_cota_o_frete(self):
        self.order.delivery_method = 'pickup'
        self.order.delivery_fee = Decimal('0')
        self.order.delivery_address = {}
        self.order.save()
        cotacao = {'fee': 9.5, 'is_valid': True, 'distance_km': 4.1, 'zone_name': 'Z',
                   'lat': -10.18, 'lng': -48.33, 'coordinate_source': 'endereco_escrito'}
        with patch('apps.stores.services.checkout_service.CheckoutService.calculate_delivery_fee_for_payload',
                   return_value=cotacao):
            r = self._post({'delivery_method': 'delivery', 'delivery_address': {
                'street': 'Quadra 110 Sul Alameda 3', 'number': '51', 'city': 'Palmas', 'state': 'TO'}})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.order.delivery_method, 'delivery')
        self.assertEqual(self.order.delivery_fee, Decimal('9.50'))
        self.assertEqual(self.order.delivery_address['street'], 'Quadra 110 Sul Alameda 3')
        self.assertEqual(self.order.total, Decimal('59.50'))

    def test_frete_digitado_vence_a_cotacao(self):
        with patch('apps.stores.services.checkout_service.CheckoutService.calculate_delivery_fee_for_payload',
                   return_value={'fee': 30, 'is_valid': True}):
            r = self._post({'delivery_address': {'street': 'Rua X', 'number': '1'}, 'delivery_fee': '5.00'})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.order.delivery_fee, Decimal('5.00'))

    def test_entrega_sem_endereco_e_recusada(self):
        self.order.delivery_method = 'pickup'
        self.order.delivery_address = {}
        self.order.save()
        r = self._post({'delivery_method': 'delivery'})
        self.assertEqual(r.status_code, 400, r.content)

    def test_endereco_fora_da_area_sem_frete_digitado_e_recusado(self):
        with patch('apps.stores.services.checkout_service.CheckoutService.calculate_delivery_fee_for_payload',
                   return_value={'fee': None, 'is_valid': False, 'message': 'Fora da área'}):
            r = self._post({'delivery_address': {'street': 'Longe', 'number': '1'}})
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn('Fora da área', r.content.decode())

    def test_aplicar_cupom_calcula_o_desconto(self):
        StoreCoupon.objects.create(store=self.store, code='DEZ', discount_type='percentage', valid_from=timezone.now() - timedelta(days=1), valid_until=timezone.now() + timedelta(days=1),
                                   discount_value=Decimal('10'), is_active=True)
        r = self._post({'coupon_code': 'dez'})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.order.coupon_code, 'DEZ')
        self.assertEqual(self.order.discount, Decimal('5.00'))
        self.assertEqual(self.order.total, Decimal('53.00'))

    def test_cupom_invalido_e_recusado(self):
        r = self._post({'coupon_code': 'NAOEXISTE'})
        self.assertEqual(r.status_code, 400, r.content)

    def test_tirar_o_cupom_tira_o_desconto(self):
        self.order.coupon_code = 'DEZ'
        self.order.discount = Decimal('5.00')
        self.order.save()
        r = self._post({'coupon_code': ''})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.order.coupon_code, '')
        self.assertEqual(self.order.discount, Decimal('0.00'))

    def test_vale_recalcula_o_acrescimo_quando_o_frete_muda(self):
        """Lais (27/10): frete caiu de 40 para 12,58 e o acréscimo de 10% do
        vale tinha que cair junto — à mão foi preciso recalcular."""
        self.order.payment_method = 'voucher_link'
        self.order.voucher_fee = Decimal('5.80')
        self.order.save()
        with patch('apps.stores.services.acrescimo_do_vale.percentual_do_vale', return_value=Decimal('10')):
            r = self._post({'delivery_method': 'pickup'})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.order.voucher_fee, Decimal('5.00'))
        self.assertEqual(self.order.total, Decimal('55.00'))
