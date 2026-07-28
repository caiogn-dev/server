from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.stores import billing
from apps.stores.models import Store, StoreCoupon

User = get_user_model()


class FeaturedCouponModelTest(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='dono2', password='x')
        self.store = Store.objects.create(name='Loja', slug='loja-fc', owner=owner, status='active')

    def test_is_featured_default_false(self):
        now = timezone.now()
        c = StoreCoupon.objects.create(
            store=self.store, code='BEMVINDO10',
            discount_type='percentage', discount_value=10,
            valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=30),
        )
        assert c.is_featured is False
        c.is_featured = True
        c.save(update_fields=['is_featured'])
        assert StoreCoupon.objects.get(id=c.id).is_featured is True

    def test_plan_gate_coupon_banner(self):
        assert billing.plan_allows('free', 'coupon_banner') is False
        assert billing.plan_allows('starter', 'coupon_banner') is False
        assert billing.plan_allows('pro', 'coupon_banner') is True
        assert billing.plan_allows('premium', 'coupon_banner') is True
