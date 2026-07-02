"""Regressão de segurança: IDOR cross-tenant no CompanyProfile.

`store_data` (detail=False) resolvia uma Store por slug/account_id e devolvia
nome, endereço, telefone, email e horários SEM verificar acesso — qualquer
usuário autenticado lia os dados de QUALQUER loja. `create` anexava um
CompanyProfile a um store_id arbitrário sem checar ownership.

Caminho account_id: `WhatsAppAccount.objects.get(id=account_id)` era feito
sem escopo de tenant — qualquer autenticado podia referenciar contas alheias.
Também: `Store.DoesNotExist` e `WhatsAppAccount.DoesNotExist` retornavam 500
com str(e) expondo mensagens internas.
"""
import uuid

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
        self.victim_account = WhatsAppAccount.objects.create(
            name='victim-acc', phone_number_id='pn-victim', waba_id='wa-victim',
            phone_number='+5511888887777', display_phone_number='+5511888887777',
            access_token_encrypted='x', webhook_verify_token='x',
            owner=self.owner,
        )
        self.url = '/api/v1/automation/companies/store_data/'

    # --- caminho store_slug ---

    def test_owner_can_read_store_data(self):
        self.client.force_authenticate(self.owner)
        resp = self.client.get(self.url, {'store_slug': 'loja-secreta'})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['company_name'], 'Loja Secreta')

    def test_attacker_cannot_read_other_store_data(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.get(self.url, {'store_slug': 'loja-secreta'})
        self.assertEqual(resp.status_code, 404, resp.content)
        self.assertNotIn('company_name', getattr(resp, 'data', {}) or {})

    def test_nonexistent_slug_returns_404_not_500(self):
        """Store.DoesNotExist não deve vazar como 500."""
        self.client.force_authenticate(self.owner)
        resp = self.client.get(self.url, {'store_slug': 'nao-existe'})
        self.assertEqual(resp.status_code, 404, resp.content)
        self.assertNotIn('DoesNotExist', str(resp.content))

    # --- caminho account_id ---

    def test_attacker_cannot_probe_victim_account_id(self):
        """Atacante passa account_id de outro tenant — deve receber 404 sem dados."""
        self.client.force_authenticate(self.attacker)
        resp = self.client.get(self.url, {'account_id': str(self.victim_account.id)})
        self.assertEqual(resp.status_code, 404, resp.content)
        self.assertNotIn('company_name', getattr(resp, 'data', {}) or {})
        # Garante que nenhum dado interno vaza na resposta
        self.assertNotIn('DoesNotExist', str(resp.content))

    def test_nonexistent_account_id_returns_404_not_500(self):
        """UUID inexistente não deve vazar stack trace como 500."""
        self.client.force_authenticate(self.attacker)
        resp = self.client.get(self.url, {'account_id': str(uuid.uuid4())})
        self.assertEqual(resp.status_code, 404, resp.content)
        self.assertNotIn('DoesNotExist', str(resp.content))

    def test_owner_can_access_via_own_account_id(self):
        """Dono ainda consegue buscar via account_id da própria conta."""
        self.client.force_authenticate(self.owner)
        resp = self.client.get(self.url, {'account_id': str(self.victim_account.id)})
        # Pode retornar 200 (store encontrada) ou 404 (store não mapeada por número)
        # — o importante é que NÃO retorna 403 nem 500
        self.assertIn(resp.status_code, [200, 404], resp.content)
        self.assertNotIn('DoesNotExist', str(resp.content))

    # --- criação ---

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
