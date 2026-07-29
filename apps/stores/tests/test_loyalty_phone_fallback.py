"""Status autenticado de fidelidade resolve por TELEFONE quando a conta
própria do usuário está vazia.

Fragmentação de identidade real em prod: o pedido credita no usuário que o
checkout resolveu (ex.: zz_teste_billing), mas o OTP loga cliente_<phone> —
outra conta, zerada. O telefone (verificado por OTP) é o elo entre as duas.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.models import UserProfile
from apps.stores.models import Store, StoreOrder, StoreOrderItem
from apps.stores.services.loyalty_service import LoyaltyService

User = get_user_model()

PHONE = '63999547790'


class LoyaltyPhoneFallbackTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='owner-pf', email='opf@t.com', password='x')
        self.store = Store.objects.create(
            name='Loja PF', slug='loja-pf', owner=owner, status='active',
            metadata={'loyalty_enabled': True},
        )
        # Usuário que o checkout usou como customer (tem os carimbos)
        self.order_user = User.objects.create_user(username='zz-order-user', password='x')
        order = StoreOrder.objects.create(
            store=self.store, customer=self.order_user, subtotal=30, total=30,
            status='delivered', customer_phone=PHONE,
        )
        StoreOrderItem.objects.create(
            order=order, product_name='Rondelli', unit_price=30, quantity=1, subtotal=30,
        )
        LoyaltyService.credit_order(order)
        # Usuário criado pelo OTP (conta de fidelidade vazia), mesmo telefone
        self.otp_user = User.objects.create_user(username=f'cliente_55{PHONE}', password='x')
        profile, _ = UserProfile.objects.get_or_create(user=self.otp_user)
        profile.phone = f'55{PHONE}'
        profile.save(update_fields=['phone'])

    def _get_status(self, user):
        from apps.stores.api.views.loyalty_views import resolve_loyalty_status_for_user
        return resolve_loyalty_status_for_user(self.store, user)

    def test_usuario_otp_ve_carimbos_da_conta_do_pedido_pelo_telefone(self):
        status = self._get_status(self.otp_user)
        self.assertEqual(status['qualified_salads'], 1)
        self.assertEqual(status['progress'], 1)

    def test_usuario_com_conta_propria_nao_usa_fallback(self):
        status = self._get_status(self.order_user)
        self.assertEqual(status['qualified_salads'], 1)

    def test_usuario_sem_telefone_e_sem_carimbos_fica_zerado(self):
        lonely = User.objects.create_user(username='sem-telefone', password='x')
        status = self._get_status(lonely)
        self.assertEqual(status['qualified_salads'], 0)

    def test_fallback_extrai_telefone_do_username_quando_profile_nao_tem(self):
        no_profile = User.objects.create_user(username=f'cliente_{PHONE}', password='x')
        status = self._get_status(no_profile)
        self.assertEqual(status['qualified_salads'], 1)
