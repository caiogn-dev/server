"""Indicação (gamificação Fase 2): cupom pessoal + recompensa do indicador."""
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store, StoreCoupon, StoreOrder
from apps.stores.services.referral_service import ReferralService

User = get_user_model()

REFERRER = '5563999770001'


class ReferralCouponTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='o-ref', email='ref@x.com', password='x')
        self.store = Store.objects.create(name='Loja Ref', slug='loja-ref', owner=self.owner, status='active')

    def test_cria_cupom_pessoal_idempotente(self):
        c1, created1 = ReferralService.get_or_create_referral_coupon(self.store, REFERRER)
        c2, created2 = ReferralService.get_or_create_referral_coupon(self.store, REFERRER)
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(c1.id, c2.id)
        self.assertTrue(c1.code.startswith('INDICA-'))
        self.assertTrue(c1.first_order_only)
        self.assertEqual(c1.metadata['referrer_phone'], REFERRER)

    def _order(self, phone):
        return StoreOrder.objects.create(
            store=self.store, customer_name='Amigo', customer_phone=phone,
            subtotal=Decimal('50'), total=Decimal('45'),
        )

    def test_resgate_premia_indicador(self):
        coupon, _ = ReferralService.get_or_create_referral_coupon(self.store, REFERRER)
        order = self._order('5563999880002')
        with mock.patch.object(ReferralService, '_notify_referrer') as notify:
            ReferralService.reward_referrer_if_applicable(order, coupon)
        reward = StoreCoupon.objects.get(metadata__type='referral_reward')
        self.assertTrue(reward.code.startswith('AMIGO5-'))
        self.assertEqual(reward.usage_limit, 1)
        notify.assert_called_once()

    def test_auto_indicacao_nao_premia(self):
        coupon, _ = ReferralService.get_or_create_referral_coupon(self.store, REFERRER)
        order = self._order(REFERRER)
        ReferralService.reward_referrer_if_applicable(order, coupon)
        self.assertFalse(StoreCoupon.objects.filter(metadata__type='referral_reward').exists())

    def test_cupom_comum_nao_premia(self):
        common = StoreCoupon.objects.create(
            store=self.store, code='NORMAL', discount_type='fixed', discount_value=5,
            valid_from='2020-01-01T00:00:00Z', valid_until='2030-01-01T00:00:00Z',
        )
        ReferralService.reward_referrer_if_applicable(self._order('556399'), common)
        self.assertFalse(StoreCoupon.objects.filter(metadata__type='referral_reward').exists())
