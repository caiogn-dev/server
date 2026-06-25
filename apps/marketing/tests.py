"""Regressão de segurança: IDOR cross-tenant no Marketing.

Vários endpoints aceitavam store_id arbitrário (import_csv, stats, send_coupon/
send_welcome, automation trigger/test) ou furavam o get_queryset (campaign
send), permitindo a qualquer autenticado disparar emails, ler estatísticas e
importar/acionar dados de OUTRO tenant.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store
from apps.marketing.models import EmailCampaign

User = get_user_model()


class MarketingCrossTenantIDORTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='mk-owner', email='mk-o@t.com', password='x')
        self.attacker = User.objects.create_user(username='mk-att', email='mk-a@t.com', password='x')
        self.store = Store.objects.create(
            name='Vitima MK', slug='vitima-mk', store_type='food', owner=self.owner,
        )
        self.campaign = EmailCampaign.objects.create(
            store=self.store, name='Promo', subject='Oi',
        )

    def test_attacker_cannot_send_campaign(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.post(f'/api/v1/marketing/campaigns/{self.campaign.id}/send/', {}, format='json')
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_attacker_cannot_read_stats(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.get('/api/v1/marketing/stats/', {'store': str(self.store.id)})
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_owner_can_read_stats(self):
        self.client.force_authenticate(self.owner)
        resp = self.client.get('/api/v1/marketing/stats/', {'store': str(self.store.id)})
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_attacker_cannot_import_subscribers(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.post(
            '/api/v1/marketing/subscribers/import_csv/',
            {'store': str(self.store.id), 'contacts': [{'email': 'x@y.com'}]},
            format='json',
        )
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_attacker_cannot_send_coupon(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.post(
            '/api/v1/marketing/actions/send_coupon/',
            {'store': str(self.store.id), 'to_email': 'v@v.com', 'customer_name': 'V',
             'coupon_code': 'X', 'discount_value': '10'},
            format='json',
        )
        self.assertEqual(resp.status_code, 403, resp.content)
