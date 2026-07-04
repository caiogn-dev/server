"""Regressão de segurança: is_staff vazava PII cross-tenant nos intent logs.

`_accessible_companies` retornava `CompanyProfile.objects.all()` quando
`user.is_staff` — e IntentLog carrega `phone_number` e `message_text` do
cliente. Assim, qualquer conta com is_staff (acesso ao /admin) lia telefones
e conteúdo de mensagens de TODOS os tenants. Só is_superuser deve ter acesso
cross-tenant.

Cenários:
  1. Atacante is_staff NÃO vê os logs (PII) de outro tenant.
  2. superuser continua vendo (guarda de não-regressão).
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.whatsapp.models import WhatsAppAccount
from apps.automation.models import CompanyProfile
from apps.automation.models.logging import IntentLog

User = get_user_model()

LOGS_URL = '/api/v1/whatsapp/intents/logs/'
SECRET_PHONE = '+5511987650000'
SECRET_TEXT = 'quero 2 marmitas na Rua Secreta 123'


def _items(response):
    data = response.data
    if isinstance(data, dict) and 'results' in data:
        return data['results']
    return data


class IntentLogsStaffIDORTest(APITestCase):
    def setUp(self):
        self.victim = User.objects.create_user(username='il-victim', email='v@t.com', password='x')
        self.victim_acc = WhatsAppAccount.objects.create(
            name='victim', phone_number_id='pn-v', waba_id='wa-v',
            phone_number='+5511444440', display_phone_number='+5511444440',
            access_token_encrypted='x', webhook_verify_token='x', owner=self.victim,
        )
        # CompanyProfile é auto-criado por signal no post_save do WhatsAppAccount.
        self.victim_company = CompanyProfile.objects.get(account=self.victim_acc)
        self.log = IntentLog.objects.create(
            company=self.victim_company,
            phone_number=SECRET_PHONE,
            message_text=SECRET_TEXT,
            intent_type='order',
            method='regex',
            confidence=0.9,
            processing_time_ms=10,
        )
        # Atacante: is_staff=True (acesso ao /admin), SEM contas próprias.
        self.attacker = User.objects.create_user(
            username='il-att', email='a@t.com', password='x', is_staff=True,
        )
        self.superuser = User.objects.create_superuser(username='il-super', email='s@t.com', password='x')

    def test_staff_nao_ve_logs_pii_de_outro_tenant(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.get(LOGS_URL)
        self.assertEqual(resp.status_code, 200, resp.content)
        ids = [item['id'] for item in _items(resp)]
        self.assertNotIn(str(self.log.id), ids)
        self.assertNotIn(SECRET_PHONE, resp.content.decode())
        self.assertNotIn('Rua Secreta', resp.content.decode())

    def test_superuser_continua_vendo(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.get(LOGS_URL)
        self.assertEqual(resp.status_code, 200, resp.content)
        ids = [item['id'] for item in _items(resp)]
        self.assertIn(str(self.log.id), ids)
