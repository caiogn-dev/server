"""Regressão de segurança: IDOR cross-tenant no CompanyProfile.

`store_data` (detail=False) resolvia uma Store por slug/account_id e devolvia
nome, endereço, telefone, email e horários SEM verificar acesso — qualquer
usuário autenticado lia os dados de QUALQUER loja. `create` anexava um
CompanyProfile a um store_id arbitrário sem checar ownership.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()


class CompanyProfileStoreDataIDORTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='cp-owner', email='cp-o@t.com', password='x')
        self.attacker = User.objects.create_user(username='cp-att', email='cp-a@t.com', password='x')
        self.store = Store.objects.create(
            name='Loja Secreta', slug='loja-secreta', store_type='food',
            owner=self.owner, email='secreta@loja.com', phone='+5511888887777',
            address='Rua Privada 123',
        )
        self.url = '/api/v1/automation/companies/store_data/'

    def test_owner_can_read_store_data(self):
        self.client.force_authenticate(self.owner)
        resp = self.client.get(self.url, {'store_slug': 'loja-secreta'})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['company_name'], 'Loja Secreta')

    def test_attacker_cannot_read_other_store_data(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.get(self.url, {'store_slug': 'loja-secreta'})
        self.assertEqual(resp.status_code, 404, resp.content)
        # não vaza dados da loja
        self.assertNotIn('company_name', getattr(resp, 'data', {}) or {})

    def test_attacker_cannot_create_profile_on_other_store(self):
        # Conta WhatsApp do próprio atacante (passa a validação do serializer),
        # mas store_id da vítima — deve ser barrado pelo check de ownership.
        acc = WhatsAppAccount.objects.create(
            name='att-acc', phone_number_id='pn-att', waba_id='wa-att',
            phone_number='+5511000999', display_phone_number='+5511000999',
            access_token_encrypted='x', webhook_verify_token='x',
            owner=self.attacker,
        )
        self.client.force_authenticate(self.attacker)
        resp = self.client.post(
            '/api/v1/automation/companies/',
            {'account_id': str(acc.id), 'store_id': str(self.store.id), 'company_name': 'Hijack'},
            format='json',
        )
        self.assertEqual(resp.status_code, 404, resp.content)
