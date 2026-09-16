"""Conta de superuser não enxerga conversa, log nem conta WhatsApp alheia.

Mesma raiz do vazamento de 16/set em apps/stores: `is_superuser` valendo como
vínculo. Aqui o dado é pior — conversa de WhatsApp carrega PII do cliente final
(telefone e texto da mensagem) de uma loja que não é minha.

Todo caso é ancorado no registro próprio: se o queryset viesse vazio para
qualquer usuário, o assert de exclusão passaria sem provar nada.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.conversations.models import Conversation
from apps.core.permissions import accessible_whatsapp_account_ids
from apps.handover.models import HandoverLog, HandoverRequest
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()


class _Req:
    def __init__(self, user):
        self.user = user


class EscopoSuperuserWhatsAppTest(TestCase):
    def setUp(self):
        self.plataforma = User.objects.create_superuser(
            username='dono_plataforma3', email='dono3@plataforma.com', password='x'
        )
        self.minha_conta = WhatsAppAccount.objects.create(
            name='Minha Conta', phone_number_id='PN_MINHA', waba_id='WABA_MINHA',
            owner=self.plataforma,
        )
        self.cliente = User.objects.create_user(
            username='cliente3', email='cliente3@loja.com', password='x'
        )
        self.conta_alheia = WhatsAppAccount.objects.create(
            name='Conta Alheia', phone_number_id='PN_ALHEIA', waba_id='WABA_ALHEIA',
            owner=self.cliente,
        )
        self.minha_conversa = Conversation.objects.create(
            account=self.minha_conta, phone_number='5563900000001'
        )
        self.conversa_alheia = Conversation.objects.create(
            account=self.conta_alheia, phone_number='5563900000002'
        )

    def _queryset(self, viewset_class):
        view = viewset_class()
        view.request = _Req(self.plataforma)
        return view.get_queryset()

    def test_contas_acessiveis_excluem_conta_sem_vinculo(self):
        ids = {str(i) for i in accessible_whatsapp_account_ids(self.plataforma)}
        self.assertIn(str(self.minha_conta.id), ids, 'âncora: a própria tem que estar')
        self.assertNotIn(str(self.conta_alheia.id), ids)

    def test_solicitacoes_de_handover_excluem_conta_alheia(self):
        from apps.handover.views import HandoverRequestViewSet

        minha = HandoverRequest.objects.create(conversation=self.minha_conversa)
        alheia = HandoverRequest.objects.create(conversation=self.conversa_alheia)

        ids = set(self._queryset(HandoverRequestViewSet).values_list('id', flat=True))
        self.assertIn(minha.id, ids, 'âncora: a própria tem que aparecer')
        self.assertNotIn(alheia.id, ids)

    def test_logs_de_handover_excluem_conta_alheia(self):
        from apps.handover.views import HandoverLogViewSet

        minha = HandoverLog.objects.create(conversation=self.minha_conversa, from_status='bot', to_status='human')
        alheia = HandoverLog.objects.create(conversation=self.conversa_alheia, from_status='bot', to_status='human')

        ids = set(self._queryset(HandoverLogViewSet).values_list('id', flat=True))
        self.assertIn(minha.id, ids, 'âncora: a própria tem que aparecer')
        self.assertNotIn(alheia.id, ids)

    def test_perfis_de_intent_excluem_conta_alheia(self):
        """Intent logs carregam phone_number e message_text do cliente final."""
        from apps.whatsapp.api.intent_views import _accessible_companies

        ids = {c.account_id for c in _accessible_companies(self.plataforma)}
        self.assertNotIn(self.conta_alheia.id, ids)

    def test_gate_de_marketing_recusa_loja_alheia(self):
        from apps.marketing.api.views import _user_can_use_store
        from apps.stores.models import Store

        minha = Store.objects.create(
            name='Loja Mkt', slug='loja-mkt', owner=self.plataforma, status='active'
        )
        alheia = Store.objects.create(
            name='Loja Mkt Alheia', slug='loja-mkt-alheia', owner=self.cliente,
            status='active',
        )
        self.assertTrue(_user_can_use_store(self.plataforma, minha.id))
        self.assertFalse(_user_can_use_store(self.plataforma, alheia.id))

    def test_dashboard_nao_conta_loja_alheia(self):
        """apps/core/dashboard_views é a tela de números do painel."""
        from apps.core.dashboard_views import _accessible_accounts, _accessible_stores
        from apps.stores.models import Store

        minha = Store.objects.create(
            name='Loja Dash', slug='loja-dash', owner=self.plataforma, status='active'
        )
        alheia = Store.objects.create(
            name='Loja Dash Alheia', slug='loja-dash-alheia', owner=self.cliente,
            status='active',
        )
        lojas = set(_accessible_stores(self.plataforma).values_list('id', flat=True))
        self.assertIn(minha.id, lojas, 'âncora: a própria tem que aparecer')
        self.assertNotIn(alheia.id, lojas)

        contas = set(_accessible_accounts(self.plataforma).values_list('id', flat=True))
        self.assertNotIn(self.conta_alheia.id, contas)

    def test_painel_django_nao_lista_loja_alheia(self):
        from apps.panel.views import _get_accessible_stores
        from apps.stores.models import Store

        minha = Store.objects.create(
            name='Loja Painel', slug='loja-painel', owner=self.plataforma, status='active'
        )
        alheia = Store.objects.create(
            name='Loja Painel Alheia', slug='loja-painel-alheia', owner=self.cliente,
            status='active',
        )
        ids = set(_get_accessible_stores(self.plataforma).values_list('id', flat=True))
        self.assertIn(minha.id, ids, 'âncora: a própria tem que aparecer')
        self.assertNotIn(alheia.id, ids)

    def test_gate_de_campanhas_recusa_conta_alheia(self):
        from apps.campaigns.api.views import _user_can_use_account

        self.assertTrue(_user_can_use_account(self.plataforma, self.minha_conta.id))
        self.assertFalse(_user_can_use_account(self.plataforma, self.conta_alheia.id))
