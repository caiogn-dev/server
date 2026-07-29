from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreCoupon

User = get_user_model()


class AppConfigLoyaltyTest(APITestCase):
    def setUp(self):
        owner = User.objects.create_user(username='dono3', password='x')
        self.store = Store.objects.create(
            name='Loja', slug='loja-ac', owner=owner, status='active',
            plan='pro', metadata={'loyalty_enabled': True, 'loyalty_salads_required': 8},
        )
        now = timezone.now()
        StoreCoupon.objects.create(
            store=self.store, code='BEMVINDO10', discount_type='percentage',
            discount_value=10, is_active=True, is_featured=True, first_order_only=True,
            valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=30),
        )

    def _get(self):
        resp = self.client.get(f'/api/v1/stores/{self.store.slug}/app-config/')
        assert resp.status_code == 200, resp.content
        return resp.json()

    def test_loyalty_program_no_app_config(self):
        data = self._get()
        assert data['loyalty_program'] == {
            'enabled': True, 'threshold': 8,
            'item_label': 'item', 'item_label_plural': 'itens',
            'qualifying_categories': [],
        }

    def test_featured_coupon_no_app_config_plano_pro(self):
        data = self._get()
        assert data['featured_coupon']['code'] == 'BEMVINDO10'
        assert data['featured_coupon']['discount_type'] == 'percentage'

    def test_featured_coupon_oculto_em_plano_free(self):
        self.store.plan = 'free'
        self.store.save(update_fields=['plan'])
        assert self._get()['featured_coupon'] is None
