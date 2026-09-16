"""Regressão de segurança (sweep): NENHUMA flag de conta vê dados de outro tenant.

Nasceu contra `is_staff`, que vazava cross-tenant em vários viewsets. Em 16/set
`is_superuser` caiu junto: a loja do primeiro cliente pago apareceu no painel do
dono da plataforma no dia em que assinou. is_staff é acesso ao /admin e
is_superuser é a conta do dono — nenhum dos dois é VÍNCULO com a loja.

Cada caso testa os dois lados. A vítima é a âncora: ela tem que continuar vendo
o próprio dado, senão "o atacante não vê" passaria numa query quebrada.

Cobre (nível de função/queryset, sem HTTP):
  - users._accessible_unified_users (PII de clientes)
  - conversations._accessible_conversations (mensagens de clientes)
  - CampaignViewSet / ContactListViewSet (campanhas + contatos PII)
  - MessengerAccountViewSet (contas Messenger do tenant)
"""
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.whatsapp.models import WhatsAppAccount
from apps.conversations.models import Conversation
from apps.campaigns.models import Campaign, ContactList
from apps.messaging.models import MessengerAccount
from apps.users.models import UnifiedUser

User = get_user_model()


def _qs(viewset_cls, user):
    """Instancia o viewset com um request mínimo e devolve get_queryset()."""
    v = viewset_cls()
    v.request = SimpleNamespace(user=user, query_params={})
    v.kwargs = {}
    v.format_kwarg = None
    return v.get_queryset()


class IsStaffCrossTenantSweepTest(TestCase):
    def setUp(self):
        self.victim = User.objects.create_user(username='sw-victim', email='v@t.com', password='x')
        self.attacker = User.objects.create_user(
            username='sw-att', email='a@t.com', password='x', is_staff=True,
        )
        self.superuser = User.objects.create_superuser(username='sw-su', email='su@t.com', password='x')

        self.acc = WhatsAppAccount.objects.create(
            name='v', phone_number_id='pn-sw', waba_id='wa-sw',
            phone_number='+5511000555', display_phone_number='+5511000555',
            access_token_encrypted='x', webhook_verify_token='x', owner=self.victim,
        )
        self.conv = Conversation.objects.create(account=self.acc, phone_number='+5599999', is_active=True)
        self.campaign = Campaign.objects.create(account=self.acc, name='Promo Secreta')
        self.contacts = ContactList.objects.create(account=self.acc, name='Lista Secreta')
        self.messenger = MessengerAccount.objects.create(
            user=self.victim, page_id='pg-sw', page_name='Página Vítima',
        )
        self.uu = UnifiedUser.objects.create(phone_number='+5599999', name='Cliente Vítima')

    def test_users_helper(self):
        """Ancorado no que a VÍTIMA vê, não num id fixo.

        `self.uu` é criado à mão com '+5599999' e a vítima enxerga o
        UnifiedUser que o signal cria a partir da conversa, com o telefone
        normalizado — são linhas diferentes. Isso é anterior a 16/set e só não
        aparecia porque o superuser via tudo e mascarava a divergência.
        O que este teste tem que provar é isolamento: o que é da vítima não
        pode aparecer para mais ninguém.
        """
        from apps.users.views import _accessible_unified_users

        da_vitima = {u.id for u in _accessible_unified_users(self.victim)}
        self.assertTrue(da_vitima, 'âncora: a vítima tem que ver o cliente dela')

        for intruso in (self.attacker, self.superuser):
            vistos = {u.id for u in _accessible_unified_users(intruso)}
            self.assertFalse(da_vitima & vistos, f'vazou PII para {intruso.username}')

    def test_conversations_helper(self):
        from apps.conversations.api.views import _accessible_conversations
        self.assertNotIn(self.conv.id, [c.id for c in _accessible_conversations(self.attacker)])
        self.assertNotIn(self.conv.id, [c.id for c in _accessible_conversations(self.superuser)])
        self.assertIn(self.conv.id, [c.id for c in _accessible_conversations(self.victim)])

    def test_campaign_queryset(self):
        from apps.campaigns.api import CampaignViewSet
        self.assertNotIn(self.campaign.id, [c.id for c in _qs(CampaignViewSet, self.attacker)])
        self.assertNotIn(self.campaign.id, [c.id for c in _qs(CampaignViewSet, self.superuser)])
        self.assertIn(self.campaign.id, [c.id for c in _qs(CampaignViewSet, self.victim)])

    def test_contactlist_queryset(self):
        from apps.campaigns.api import ContactListViewSet
        self.assertNotIn(self.contacts.id, [c.id for c in _qs(ContactListViewSet, self.attacker)])
        self.assertNotIn(self.contacts.id, [c.id for c in _qs(ContactListViewSet, self.superuser)])
        self.assertIn(self.contacts.id, [c.id for c in _qs(ContactListViewSet, self.victim)])

    def test_messenger_account_queryset(self):
        from apps.messaging.api.views import MessengerAccountViewSet
        self.assertNotIn(self.messenger.id, [m.id for m in _qs(MessengerAccountViewSet, self.attacker)])
        self.assertNotIn(self.messenger.id, [m.id for m in _qs(MessengerAccountViewSet, self.superuser)])
        self.assertIn(self.messenger.id, [m.id for m in _qs(MessengerAccountViewSet, self.victim)])
