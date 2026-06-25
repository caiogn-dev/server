"""Regressão de segurança: IDOR cross-tenant em Campaigns.

As actions de detalhe (start/pause/resume/cancel/schedule/stats/process/
add_recipients) chamavam o service com `str(pk)` cru, ignorando o escopo do
get_queryset — qualquer autenticado controlava a campanha de OUTRO tenant pelo
UUID. import_csv/create aceitavam account_id arbitrário.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.campaigns.models import Campaign
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()


class CampaignCrossTenantIDORTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='cmp-owner', email='cmp-o@t.com', password='x')
        self.attacker = User.objects.create_user(username='cmp-att', email='cmp-a@t.com', password='x')
        self.victim_account = WhatsAppAccount.objects.create(
            name='victim', phone_number_id='pn-cv', waba_id='wa-cv',
            phone_number='+5511333331', display_phone_number='+5511333331',
            access_token_encrypted='x', webhook_verify_token='x', owner=self.owner,
        )
        self.attacker_account = WhatsAppAccount.objects.create(
            name='att', phone_number_id='pn-ca', waba_id='wa-ca',
            phone_number='+5511333332', display_phone_number='+5511333332',
            access_token_encrypted='x', webhook_verify_token='x', owner=self.attacker,
        )
        self.campaign = Campaign.objects.create(
            account=self.victim_account, name='Vitima', is_active=True,
        )

    def test_attacker_cannot_get_stats(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.get(f'/api/v1/campaigns/campaigns/{self.campaign.id}/stats/')
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_attacker_cannot_start_campaign(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.post(f'/api/v1/campaigns/campaigns/{self.campaign.id}/start/', {}, format='json')
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_attacker_cannot_pause_campaign(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.post(f'/api/v1/campaigns/campaigns/{self.campaign.id}/pause/', {}, format='json')
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_owner_can_get_stats(self):
        self.client.force_authenticate(self.owner)
        resp = self.client.get(f'/api/v1/campaigns/campaigns/{self.campaign.id}/stats/')
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_attacker_cannot_import_csv_into_victim_account(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.post(
            '/api/v1/campaigns/contacts/import_csv/',
            {'account_id': str(self.victim_account.id), 'name': 'leak',
             'csv_content': 'phone,name\n+551199,Joao'},
            format='json',
        )
        self.assertEqual(resp.status_code, 403, resp.content)
