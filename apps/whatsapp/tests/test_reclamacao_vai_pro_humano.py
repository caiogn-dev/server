"""Reclamação do pedido vai direto para um atendente.

25/09, Cê Saladas: "Boa tarde, Caio! Vieram com cebola, batata palha e frango
desfiado" recebeu "Como posso te ajudar? 👇" duas vezes. Só a mensagem seguinte
transferiu — por sorte: "pes*soa*l" contém "pessoa". O atendente viu 3 min depois.
E "Veio errado meu pedido" virava RASTREAR PEDIDO: a cliente lia o status da
entrega em vez de alguém resolver.

Contrato: reclamação transfere para humano com o motivo "Reclamação" na fila,
responde com empatia (sem menu) e larga o checkout. Pedido com "sem cebola"
continua sendo pedido.
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import CompanyProfile
from apps.automation.services.unified_service import UnifiedService
from apps.conversations.models import Conversation
from apps.stores.models import Store
from apps.whatsapp.intents.detector import IntentType, intent_detector
from apps.whatsapp.intents.reclamacao import eh_reclamacao
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()
PHONE = '5511975373744'

RECLAMACOES = [
    'Boa tarde,  Caio!\nVieram com cebola, batata palha e frango desfiado',
    'Veio errado meu pedido',
    'faltou o molho',
    'a salada veio sem frango',
    'meu pedido veio frio',
    'não veio o suco',
    'o frango veio cru',
    'quero fazer uma reclamação',
    'tinha um cabelo na comida',
    'veio trocado, pedi a queridinha',
]

PEDIDOS = [
    'quero uma queridinha sem cebola',
    'pode vir com molho?',
    'boa tarde',
    'vem com cebola?',
    'cadê meu pedido',
]


@pytest.mark.parametrize('texto', RECLAMACOES)
def test_reclamacao_e_reconhecida(texto):
    assert eh_reclamacao(texto), texto
    assert intent_detector.detect_regex(texto) == IntentType.COMPLAINT


@pytest.mark.parametrize('texto', PEDIDOS)
def test_pedido_nao_e_reclamacao(texto):
    assert not eh_reclamacao(texto), texto


class ReclamacaoTransfereTest(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='dona-reclama', password='x')
        self.store = Store.objects.create(billing_exempt=True, name='Cê Saladas', slug='ce-reclama', owner=owner)
        self.account = WhatsAppAccount.objects.create(name='CeRecl', phone_number_id='PHRECL', waba_id='WRECL')
        self.store.whatsapp_account = self.account
        self.store.save(update_fields=['whatsapp_account'])
        profile = CompanyProfile.objects.get(store=self.store)
        profile.account = self.account
        CompanyProfile.objects.filter(account=self.account).exclude(pk=profile.pk).delete()
        profile.save()
        self.conversation = Conversation.objects.create(account=self.account, phone_number=PHONE)

    def _texto(self, texto, use_llm=False):
        self.conversation.refresh_from_db()
        return UnifiedService(self.account, self.conversation, use_llm=use_llm).process_message(texto)

    def test_reclamacao_real_transfere_com_motivo(self):
        from apps.handover.models import ConversationHandover
        resposta = self._texto(RECLAMACOES[0])

        self.assertNotIn('Como posso te ajudar', resposta.content)
        self.assertIn('atendente', resposta.content.lower())
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.mode, Conversation.ConversationMode.HUMAN)
        self.assertIn('Reclamação', ConversationHandover.objects.get(conversation=self.conversation).transfer_reason)

    def test_veio_errado_nao_vira_rastreio(self):
        resposta = self._texto('Veio errado meu pedido')
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.mode, Conversation.ConversationMode.HUMAN)
        self.assertNotIn('Como posso te ajudar', resposta.content)

    def test_com_ia_ligada_reclamacao_nao_vai_para_a_ia(self):
        self._texto('faltou o molho', use_llm=True)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.mode, Conversation.ConversationMode.HUMAN)


def test_motivo_reclamacao_tem_codigo_proprio_na_fila():
    from apps.conversations.services import operacao_humana as op
    assert op._codigo_pelo_texto('Reclamação do pedido') == 'reclamacao'
    assert op.TEXTOS['reclamacao'] == 'Reclamação do pedido'


def test_reclamacao_fura_a_fila():
    from apps.conversations.services.fila_humana import ordenar_esperando
    fila = [
        {'id': 'antiga', 'esperando_ha_segundos': 900, 'motivo': {'codigo': 'pediu_atendente'}},
        {'id': 'reclamou', 'esperando_ha_segundos': 30, 'motivo': {'codigo': 'reclamacao'}},
        {'id': 'meio', 'esperando_ha_segundos': 300, 'motivo': {'codigo': 'bot_nao_entendeu'}},
    ]
    assert [i['id'] for i in ordenar_esperando(fila)] == ['reclamou', 'antiga', 'meio']
