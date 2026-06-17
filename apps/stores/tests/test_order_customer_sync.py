"""
Regressão: ao criar pedido com cliente NOVO (Novo Pedido no dashboard),
o cliente tem que virar UnifiedUser (modelo que a busca CRM consulta),
senão some da base e exige recadastro.
"""
from django.test import TestCase
from django.contrib.auth.models import User
from apps.stores.models import Store, StoreCustomer
from apps.core.services.customer_identity import CustomerIdentityService
from apps.users.models import UnifiedUser


class OrderCustomerSyncTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@x.com', 'x')
        self.store = Store.objects.create(
            name='Loja', slug='loja', owner=self.owner, status=Store.StoreStatus.ACTIVE
        )

    def test_cliente_novo_vira_unified_user_pesquisavel(self):
        # email vazio → o serializer gera placeholder .invalid; simulamos isso
        res = CustomerIdentityService.sync_checkout_customer(
            store=self.store,
            customer_name='Maria Cliente',
            email='99887766@local.invalid',  # placeholder — deve ser ignorado
            phone='+5563999887766',
            delivery_method='pickup',
        )
        self.assertIsNotNone(res['store_customer'])

        # UnifiedUser foi CRIADO e é encontrável por telefone (o que a busca CRM faz)
        u = UnifiedUser.objects.filter(phone_number__icontains='999887766').first()
        self.assertIsNotNone(u, 'UnifiedUser não foi criado para o cliente novo')
        self.assertEqual(u.name, 'Maria Cliente')
        # placeholder .invalid não vazou pro email do UnifiedUser
        self.assertFalse((u.email or '').endswith('.invalid'))

        # StoreCustomer ficou linkado ao UnifiedUser
        sc = res['store_customer']
        sc.refresh_from_db()
        self.assertEqual(sc.unified_user_id, u.id)

    def test_idempotente_nao_duplica(self):
        for _ in range(2):
            CustomerIdentityService.sync_checkout_customer(
                store=self.store, customer_name='João', email='',
                phone='+5563911112222', delivery_method='pickup',
            )
        self.assertEqual(
            UnifiedUser.objects.filter(phone_number__icontains='911112222').count(), 1
        )
