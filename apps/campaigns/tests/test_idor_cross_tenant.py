"""Regressão de segurança: IDOR cross-tenant em Campaigns.

As actions de detalhe (start/pause/resume/cancel/schedule/stats/process/
add_recipients) chamavam o service com `str(pk)` cru, ignorando o escopo do
get_queryset — qualquer autenticado controlava a campanha de OUTRO tenant pelo
UUID. import_csv/create aceitavam account_id arbitrário.

Também cobre: info-disclosure via str(e) em handlers de exceção genéricos
(CampaignViewSet.process e ContactListViewSet.import_csv).
"""
import unittest
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate

# langchain_core é necessário para importar os views de campaigns.
# Em ambientes mínimos (container de CI sem as deps de IA), os testes
# de str(e) são pulados mas executam normalmente no Docker de produção.
try:
    from apps.campaigns.api.views import CampaignViewSet, ContactListViewSet
    _CAMPAIGNS_IMPORTABLE = True
except ImportError:
    CampaignViewSet = None
    ContactListViewSet = None
    _CAMPAIGNS_IMPORTABLE = False

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


_STR_E_SECRET = 'Internal DB password=s3cr3t host=prod-postgres trace=abc'


@unittest.skipUnless(_CAMPAIGNS_IMPORTABLE, 'langchain_core não instalado — roda no Docker')
class CampaignProcessStrELeakTest(SimpleTestCase):
    """CampaignViewSet.process não expõe str(e) em HTTP 500."""

    def setUp(self):
        self.factory = APIRequestFactory()

    @patch('apps.campaigns.api.views.CampaignService')
    @patch.object(CampaignViewSet, 'get_object')
    def test_process_excecao_nao_expoe_str_e(self, mock_get_obj, mock_svc_cls):
        mock_campaign = MagicMock()
        mock_campaign.status = 'running'
        mock_get_obj.return_value = mock_campaign
        mock_svc_cls.return_value.process_campaign_batch.side_effect = Exception(_STR_E_SECRET)

        req = self.factory.post('/fake/')
        force_authenticate(req, user=MagicMock(is_authenticated=True))
        resp = CampaignViewSet.as_view({'post': 'process'})(req, pk='uuid-test')

        self.assertEqual(resp.status_code, 500)
        self.assertNotIn(_STR_E_SECRET, str(resp.data))
        self.assertNotIn('prod-postgres', str(resp.data))

    @patch('apps.campaigns.api.views.CampaignService')
    @patch.object(CampaignViewSet, 'get_object')
    def test_process_retorna_mensagem_generica(self, mock_get_obj, mock_svc_cls):
        mock_campaign = MagicMock()
        mock_campaign.status = 'running'
        mock_get_obj.return_value = mock_campaign
        mock_svc_cls.return_value.process_campaign_batch.side_effect = Exception(_STR_E_SECRET)

        req = self.factory.post('/fake/')
        force_authenticate(req, user=MagicMock(is_authenticated=True))
        resp = CampaignViewSet.as_view({'post': 'process'})(req, pk='uuid-test')

        self.assertIn('error', resp.data)
        self.assertNotIn(_STR_E_SECRET, str(resp.data['error']))


@unittest.skipUnless(_CAMPAIGNS_IMPORTABLE, 'langchain_core não instalado — roda no Docker')
class ContactListImportCsvStrELeakTest(SimpleTestCase):
    """ContactListViewSet.import_csv não expõe str(e) em erros de importação."""

    def setUp(self):
        self.factory = APIRequestFactory()

    @patch('apps.campaigns.api.views.CampaignService')
    @patch('apps.campaigns.api.views._user_can_use_account', return_value=True)
    def test_import_csv_excecao_nao_expoe_str_e(self, _perm, mock_svc_cls):
        mock_svc_cls.return_value.import_contacts_from_csv.side_effect = Exception(_STR_E_SECRET)

        req = self.factory.post('/fake/', {
            'account_id': 'uuid-acc',
            'name': 'Lista Teste',
            'csv_content': 'phone,name\n+5511999,Joao',
        }, format='json')
        force_authenticate(req, user=MagicMock(is_authenticated=True))

        with patch('apps.campaigns.api.views.ImportContactsSerializer') as mock_ser_cls:
            mock_ser = MagicMock()
            mock_ser.is_valid.return_value = True
            mock_ser.validated_data = {
                'account_id': 'uuid-acc',
                'name': 'Lista Teste',
                'csv_content': 'phone,name\n+5511999,Joao',
            }
            mock_ser_cls.return_value = mock_ser

            resp = ContactListViewSet.as_view({'post': 'import_csv'})(req)

        self.assertEqual(resp.status_code, 400)
        self.assertNotIn(_STR_E_SECRET, str(resp.data))
        self.assertNotIn('prod-postgres', str(resp.data))

    @patch('apps.campaigns.api.views.CampaignService')
    @patch('apps.campaigns.api.views._user_can_use_account', return_value=True)
    def test_import_csv_retorna_mensagem_generica(self, _perm, mock_svc_cls):
        mock_svc_cls.return_value.import_contacts_from_csv.side_effect = Exception(_STR_E_SECRET)

        req = self.factory.post('/fake/', {}, format='json')
        force_authenticate(req, user=MagicMock(is_authenticated=True))

        with patch('apps.campaigns.api.views.ImportContactsSerializer') as mock_ser_cls:
            mock_ser = MagicMock()
            mock_ser.is_valid.return_value = True
            mock_ser.validated_data = {
                'account_id': 'uuid-acc',
                'name': 'Lista',
                'csv_content': 'phone\n+551199',
            }
            mock_ser_cls.return_value = mock_ser

            resp = ContactListViewSet.as_view({'post': 'import_csv'})(req)

        self.assertIn('error', resp.data)
        self.assertNotIn(_STR_E_SECRET, str(resp.data['error']))
