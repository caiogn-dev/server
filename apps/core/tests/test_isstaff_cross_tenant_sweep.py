"""Regressão de segurança (sweep): is_staff NÃO pode ver dados de outro tenant.

Vários viewsets/helpers concediam acesso cross-tenant a `is_staff` (não só
`is_superuser`) — mesma família de intent_views/dashboard. is_staff = acesso ao
/admin, NÃO dono de dados de tenant. Só is_superuser vê tudo.

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
        from apps.users.views import _accessible_unified_users
        self.assertNotIn(self.uu.id, [u.id for u in _accessible_unified_users(self.attacker)])
        self.assertIn(self.uu.id, [u.id for u in _accessible_unified_users(self.superuser)])

    def test_conversations_helper(self):
        from apps.conversations.api.views import _accessible_conversations
        self.assertNotIn(self.conv.id, [c.id for c in _accessible_conversations(self.attacker)])
        self.assertIn(self.conv.id, [c.id for c in _accessible_conversations(self.superuser)])

    def test_campaign_queryset(self):
        from apps.campaigns.api import CampaignViewSet
        self.assertNotIn(self.campaign.id, [c.id for c in _qs(CampaignViewSet, self.attacker)])
        self.assertIn(self.campaign.id, [c.id for c in _qs(CampaignViewSet, self.superuser)])

    def test_contactlist_queryset(self):
        from apps.campaigns.api import ContactListViewSet
        self.assertNotIn(self.contacts.id, [c.id for c in _qs(ContactListViewSet, self.attacker)])
        self.assertIn(self.contacts.id, [c.id for c in _qs(ContactListViewSet, self.superuser)])

    def test_messenger_account_queryset(self):
        from apps.messaging.api.views import MessengerAccountViewSet
        self.assertNotIn(self.messenger.id, [m.id for m in _qs(MessengerAccountViewSet, self.attacker)])
        self.assertIn(self.messenger.id, [m.id for m in _qs(MessengerAccountViewSet, self.superuser)])
