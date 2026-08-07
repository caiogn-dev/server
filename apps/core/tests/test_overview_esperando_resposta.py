"""O card "conversas em aberto" precisa contar quem está esperando resposta.

Sintoma em produção (07/ago): a home do painel anunciava "208 conversas em
aberto — cliente esperando resposta no WhatsApp". Não havia 208 clientes
esperando: `status` de Conversation nasce 'open' e NADA nunca fecha, então o
número era simplesmente o total histórico de conversas da loja (211 no banco,
todas 'open'). Um alerta que aparece sempre e nunca muda não é alerta — o dono
aprende a ignorar a home inteira.

Contrato: `conversations.waiting_reply` conta conversa cuja última mensagem é
do CLIENTE (ninguém respondeu depois) e que teve movimento nas últimas 48h.
Conversa antiga e já respondida não entra.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.automation.models import CompanyProfile
from apps.conversations.models import Conversation
from apps.stores.models import Store
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()


class OverviewEsperandoRespostaTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-ov', email='ov@loja.com', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Loja OV', slug='loja-ov', owner=self.owner,
        )
        self.account = WhatsAppAccount.objects.create(
            name='ContaOV', phone_number_id='PHOV', waba_id='WOV',
        )
        profile = CompanyProfile.objects.get(store=self.store)
        profile.account = self.account
        CompanyProfile.objects.filter(account=self.account).exclude(pk=profile.pk).delete()
        profile.save()

        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {Token.objects.get_or_create(user=self.owner)[0].key}'
        )

        agora = timezone.now()
        # 1) cliente falou por último, hoje → ESPERANDO
        self._conversa('5563900000001', cliente=agora - timedelta(hours=2), agente=agora - timedelta(hours=3))
        # 2) cliente falou e ninguém nunca respondeu → ESPERANDO
        self._conversa('5563900000002', cliente=agora - timedelta(hours=1), agente=None)
        # 3) a loja respondeu por último → não espera nada
        self._conversa('5563900000003', cliente=agora - timedelta(hours=5), agente=agora - timedelta(hours=4))
        # 4) cliente falou por último, mas há 10 dias → passou do prazo útil
        self._conversa('5563900000004', cliente=agora - timedelta(days=10), agente=None)
        # 5) conversa sem nenhuma mensagem de cliente
        self._conversa('5563900000005', cliente=None, agente=None)

    def _conversa(self, phone, cliente, agente):
        return Conversation.objects.create(
            account=self.account,
            phone_number=phone,
            wa_id=phone,
            status='open',
            last_customer_message_at=cliente,
            last_agent_message_at=agente,
            last_message_at=cliente or agente,
        )

    def test_waiting_reply_conta_so_quem_espera(self):
        resp = self.client.get('/api/v1/core/dashboard/overview/', {'store': self.store.slug})
        assert resp.status_code == 200, resp.content

        conversas = resp.json()['conversations']
        assert conversas['waiting_reply'] == 2, (
            f"esperado 2 esperando resposta, veio {conversas['waiting_reply']} "
            f"(as 5 conversas continuam com status 'open')"
        )

    def test_total_open_continua_disponivel(self):
        """O número antigo não some — só deixa de ser o que o card mostra."""
        conversas = self.client.get(
            '/api/v1/core/dashboard/overview/', {'store': self.store.slug}
        ).json()['conversations']
        assert conversas['by_status'].get('open') == 5


class OverviewConversasNaoVazamEntreLojasTest(TestCase):
    """As conversas da home eram contadas por CONTA, não por LOJA.

    Segundo sintoma do mesmo card (07/ago): a Cê Saladas mostrava 208. O banco
    tinha 126 conversas na conta dela, 78 na da Pastita e 4 na conta global —
    126+78+4 = 208. Os pedidos já eram filtrados por `stores_qs`; as conversas
    ficaram em `account_id__in=account_ids`, que é tudo a que o USUÁRIO tem
    acesso, não a loja que ele está olhando.

    Para quem tem uma loja só isso é invisível. Para quem tem duas, a home de
    cada uma mostra o movimento das duas — e some a razão de existir do
    seletor de loja.
    """

    def setUp(self):
        self.owner = User.objects.create_user(username='dono-2', email='d2@x.com', password='x')
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {Token.objects.get_or_create(user=self.owner)[0].key}'
        )
        agora = timezone.now()

        self.loja_a, self.conta_a = self._loja('loja-a', 'PHA', 'WA')
        self.loja_b, self.conta_b = self._loja('loja-b', 'PHB', 'WB')

        # A: 2 esperando. B: 3 esperando.
        for i in range(2):
            self._conversa(self.conta_a, f'55639100000{i}', agora - timedelta(hours=1))
        for i in range(3):
            self._conversa(self.conta_b, f'55639200000{i}', agora - timedelta(hours=1))

    def _loja(self, slug, phone_id, waba):
        store = Store.objects.create(
            billing_exempt=True, name=slug, slug=slug, owner=self.owner,
        )
        account = WhatsAppAccount.objects.create(
            name=slug, phone_number_id=phone_id, waba_id=waba,
        )
        profile = CompanyProfile.objects.get(store=store)
        profile.account = account
        CompanyProfile.objects.filter(account=account).exclude(pk=profile.pk).delete()
        profile.save()
        return store, account

    def _conversa(self, account, phone, quando):
        return Conversation.objects.create(
            account=account, phone_number=phone, wa_id=phone, status='open',
            last_customer_message_at=quando, last_agent_message_at=None,
            last_message_at=quando,
        )

    def test_cada_loja_conta_so_o_que_e_dela(self):
        a = self.client.get(
            '/api/v1/core/dashboard/overview/', {'store': self.loja_a.slug}
        ).json()['conversations']
        b = self.client.get(
            '/api/v1/core/dashboard/overview/', {'store': self.loja_b.slug}
        ).json()['conversations']

        assert a['waiting_reply'] == 2, f"loja-a devia ver só as 2 dela, viu {a['waiting_reply']}"
        assert b['waiting_reply'] == 3, f"loja-b devia ver só as 3 dela, viu {b['waiting_reply']}"

    def test_total_por_status_tambem_respeita_a_loja(self):
        a = self.client.get(
            '/api/v1/core/dashboard/overview/', {'store': self.loja_a.slug}
        ).json()['conversations']
        assert a['by_status'].get('open') == 2

    def test_sem_loja_selecionada_soma_tudo_a_que_o_dono_tem_acesso(self):
        # Sem `store` na query o painel mostra a visão consolidada do dono —
        # aí somar as duas está certo, e é o comportamento que já existia.
        todas = self.client.get('/api/v1/core/dashboard/overview/').json()['conversations']
        assert todas['waiting_reply'] == 5
