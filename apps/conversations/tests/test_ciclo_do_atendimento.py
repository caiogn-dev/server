"""O ciclo do atendimento: quem atende agora — o bot ou uma pessoa — e até quando.

Diagnóstico de 19/09/2026 (produção):
  - 331 das 599 conversas ativas estavam em modo humano. Em 30 dias, 153
    viraram humanas e só 5 voltaram: uma resposta pelo celular emudecia o bot
    com aquele cliente PARA SEMPRE. Não havia caminho de volta automático.
  - "Resolver" só trocava um rótulo: o bot seguia mudo. E mensagem nova do
    cliente reabria conversa ENCERRADA, mas não RESOLVIDA.
  - O motivo da passagem saía sempre "Synced from conversation mode switch":
    ninguém sabia se foi o dono no celular, o painel ou a IA falhando.

DECISÃO DO DONO (19/09): o modo humano vale até o fim do dia; no dia
seguinte o bot volta. Resolver = o atendimento acabou, o bot volta.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model

from apps.conversations.models import Conversation
from apps.conversations.services.atendimento_humano import (
    assumir_atendimento,
    devolver_ao_bot_se_venceu,
)
from apps.whatsapp.models import WhatsAppAccount

BRT = ZoneInfo('America/Sao_Paulo')
HOJE_15H = datetime(2026, 9, 19, 15, 0, tzinfo=BRT)
HOJE_9H = datetime(2026, 9, 19, 9, 0, tzinfo=BRT)
ONTEM_16H = datetime(2026, 9, 18, 16, 0, tzinfo=BRT)


@pytest.fixture
def conta(db):
    dono = get_user_model().objects.create_user(username='dono-ciclo', password='x')
    return WhatsAppAccount.objects.create(
        name='Conta Ciclo', phone_number_id='pn-ciclo', waba_id='wa-ciclo',
        phone_number='+5563900000001', display_phone_number='+5563900000001',
        access_token_encrypted='x', webhook_verify_token='x', owner=dono,
    )


@pytest.fixture
def conversa(conta):
    return Conversation.objects.create(
        account=conta, phone_number='5563999990001', contact_name='Cliente',
    )


def _humana_desde(conversa, quando, atendente_respondeu=None):
    assumir_atendimento(conversa, origem='eco_do_app_business')
    from apps.handover.models import ConversationHandover
    ConversationHandover.objects.filter(conversation=conversa).update(last_transfer_at=quando)
    Conversation.objects.filter(pk=conversa.pk).update(last_agent_message_at=atendente_respondeu)
    conversa.refresh_from_db()


@pytest.mark.django_db
class TestMotivoDaPassagem:
    def test_resposta_pelo_celular_fica_registrada_como_motivo(self, conversa):
        assumir_atendimento(conversa, origem='eco_do_app_business')
        conversa.refresh_from_db()
        assert 'celular' in conversa.handover.transfer_reason.lower()

    def test_falha_da_ia_fica_registrada_como_motivo(self, conversa):
        assumir_atendimento(conversa, origem='falha_da_ia')
        conversa.refresh_from_db()
        assert 'ia' in conversa.handover.transfer_reason.lower()


@pytest.mark.django_db
class TestDiaSeguinteOBotVolta:
    def test_humano_de_ontem_volta_ao_bot(self, conversa):
        _humana_desde(conversa, ONTEM_16H, atendente_respondeu=ONTEM_16H)

        assert devolver_ao_bot_se_venceu(conversa, agora=HOJE_9H) is True
        conversa.refresh_from_db()
        assert conversa.mode == Conversation.ConversationMode.AUTO

    def test_humano_de_hoje_continua_humano(self, conversa):
        _humana_desde(conversa, HOJE_9H)

        assert devolver_ao_bot_se_venceu(conversa, agora=HOJE_15H) is False
        conversa.refresh_from_db()
        assert conversa.mode == Conversation.ConversationMode.HUMAN

    def test_atendente_que_respondeu_hoje_segura_o_humano(self, conversa):
        """Passou para humano ontem, mas o atendente falou hoje: atendimento vivo."""
        _humana_desde(conversa, ONTEM_16H, atendente_respondeu=HOJE_9H)

        assert devolver_ao_bot_se_venceu(conversa, agora=HOJE_15H) is False

    def test_a_volta_fica_registrada_com_motivo(self, conversa):
        _humana_desde(conversa, ONTEM_16H, atendente_respondeu=ONTEM_16H)
        devolver_ao_bot_se_venceu(conversa, agora=HOJE_9H)
        conversa.refresh_from_db()
        assert 'dia' in conversa.handover.transfer_reason.lower()

    def test_conversa_do_bot_nao_e_tocada(self, conversa):
        assert devolver_ao_bot_se_venceu(conversa, agora=HOJE_9H) is False


@pytest.mark.django_db
class TestResolverEReabrir:
    def test_resolver_devolve_ao_bot(self, conversa):
        from apps.conversations.services import ConversationService
        assumir_atendimento(conversa, origem='painel')

        ConversationService().resolve_conversation(str(conversa.id))

        conversa.refresh_from_db()
        assert conversa.status == Conversation.ConversationStatus.RESOLVED
        assert conversa.mode == Conversation.ConversationMode.AUTO

    def test_mensagem_nova_reabre_conversa_resolvida(self, conta, conversa):
        from apps.conversations.services import ConversationService
        ConversationService().resolve_conversation(str(conversa.id))

        ConversationService().get_or_create_conversation(conta, conversa.phone_number)

        conversa.refresh_from_db()
        assert conversa.status == Conversation.ConversationStatus.OPEN


class _MensagemFalsa:
    def __init__(self, conversation):
        self.id = 'msg-ciclo'
        self.conversation = conversation


@pytest.mark.django_db
class TestMensagemDoClienteNoDiaSeguinte:
    """A regra só vale se for aplicada onde a mensagem chega."""

    def test_humano_de_ontem_nao_cala_o_bot_hoje(self, conversa):
        from apps.whatsapp.services.webhook_service import WebhookService
        _humana_desde(conversa, ONTEM_16H - timedelta(days=1),
                      atendente_respondeu=ONTEM_16H - timedelta(days=1))

        suprime = WebhookService()._should_suppress_for_human_mode(
            _MensagemFalsa(conversa), None, None,
        )

        assert suprime is False
        conversa.refresh_from_db()
        assert conversa.mode == Conversation.ConversationMode.AUTO

    def test_humano_de_hoje_continua_calando_o_bot(self, conversa):
        from django.utils import timezone
        from apps.whatsapp.services.webhook_service import WebhookService
        _humana_desde(conversa, timezone.now(), atendente_respondeu=timezone.now())

        suprime = WebhookService()._should_suppress_for_human_mode(
            _MensagemFalsa(conversa), None, None,
        )

        assert suprime is True


@pytest.mark.django_db
def test_humana_sem_registro_de_quando_nao_e_solta(conversa):
    """Na dúvida, não solta: o bot falando por cima de um atendente é pior."""
    Conversation.objects.filter(pk=conversa.pk).update(mode=Conversation.ConversationMode.HUMAN)
    conversa.refresh_from_db()

    assert devolver_ao_bot_se_venceu(conversa, agora=HOJE_9H) is False


@pytest.mark.django_db
def test_resposta_pelo_celular_conta_como_atendente_respondeu(conta, conversa):
    """A fila humana precisa saber que o dono respondeu pelo celular.

    O eco atualizava só `last_message_at`: respondido pelo celular, o cliente
    continuaria parecendo "esperando" na fila para sempre.
    """
    from apps.whatsapp.services.webhook_service import WebhookService
    WebhookService()._handle_message_echo(conta, {
        'id': 'wamid.eco-ciclo-1', 'to': conversa.phone_number,
        'from': conta.phone_number, 'type': 'text',
        'text': {'body': 'Oi! Já separei seu pedido.'},
    })

    conversa.refresh_from_db()
    assert conversa.last_agent_message_at is not None
