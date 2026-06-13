"""LGPD art. 18: anonimização de dados do titular (direito ao esquecimento)."""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.core.services.customer_identity import CustomerIdentityService
from apps.stores.models import Store, StoreCustomer, StoreCustomerAddress

User = get_user_model()


class LGPDDeletionTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='o-lgpd', email='o-lgpd@t.com', password='x')
        self.store = Store.objects.create(name='L', slug='l-lgpd', owner=self.owner, status='active')
        # Cliente com PII
        CustomerIdentityService.sync_checkout_customer(
            store=self.store, customer_name='João Silva', phone='5599888887777',
            email='joao@cliente.com', accepts_marketing=True,
            delivery_address={'street': 'Rua X', 'number': '10', 'city': 'SP', 'state': 'SP', 'zip_code': '01000000'},
        )
        self.customer_user = User.objects.get(email='joao@cliente.com')

    def test_anonimizacao_remove_pii_e_mantem_usuario(self):
        CustomerIdentityService.anonymize_user(self.customer_user)
        self.customer_user.refresh_from_db()
        self.assertNotIn('joao', self.customer_user.email)
        self.assertIn('anonimizado.local', self.customer_user.email)
        self.assertFalse(self.customer_user.is_active)
        # StoreCustomer sem telefone, sem consentimento; endereços apagados
        sc = StoreCustomer.objects.get(store=self.store, user=self.customer_user)
        self.assertEqual(sc.phone, '')
        self.assertFalse(sc.accepts_marketing)
        self.assertEqual(StoreCustomerAddress.objects.filter(customer=sc).count(), 0)

    def test_endpoint_de_exclusao_anonimiza(self):
        self.client.force_authenticate(self.customer_user)
        resp = self.client.post('/api/v1/core/lgpd/request_deletion/')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['status'], 'anonymized')
        self.customer_user.refresh_from_db()
        self.assertFalse(self.customer_user.is_active)

    def test_anonimizacao_idempotente(self):
        CustomerIdentityService.anonymize_user(self.customer_user)
        CustomerIdentityService.anonymize_user(self.customer_user)  # não deve quebrar
        self.customer_user.refresh_from_db()
        self.assertIn('anonimizado.local', self.customer_user.email)
