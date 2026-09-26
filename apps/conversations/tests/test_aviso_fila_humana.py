"""Aviso de cliente esperando atendimento — OPT-IN.

O dono não quer aviso que ninguém pediu (o de impressora foi retirado em
26/09). Este só sai quando a loja liga `Store.metadata['aviso_fila_humana']`,
e uma vez por espera: o cliente que espera 40 minutos não gera 20 avisos.
"""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.conversations.models import Conversation
from apps.stores.models import Store
from apps.whatsapp.models import WhatsAppAccount

NOME_DA_TAREFA = 'apps.conversations.tasks.avisar_fila_humana'


def _cenario(ativo=True, apos=5, esperando_min=12, telefone='5563988887777'):
    from apps.conversations.services import ConversationService

    dono = get_user_model().objects.create_user(username=f'dono-aviso-{esperando_min}-{ativo}', password='x')
    loja = Store.objects.create(
        name='Cê Saladas', slug=f'aviso-{esperando_min}-{ativo}', owner=dono, status='active',
        metadata={'aviso_fila_humana': {'ativo': ativo, 'apos_minutos': apos, 'telefone': telefone}},
    )
    conta = WhatsAppAccount.objects.create(
        name='Conta', phone_number_id=f'pn-aviso-{esperando_min}-{ativo}', waba_id='wa',
        phone_number='+556390000031', display_phone_number='+556390000031',
        access_token_encrypted='x', webhook_verify_token='x', owner=dono,
    )
    loja.whatsapp_account = conta
    loja.save(update_fields=['whatsapp_account'])
    conv = Conversation.objects.create(account=conta, phone_number='5563999990401', contact_name='Joana')
    ConversationService().switch_to_human(str(conv.id), motivo='Respondido pelo painel')
    from apps.whatsapp.models import Message
    Message.objects.create(
        account=conta, conversation=conv, whatsapp_message_id=f'aviso-in-{esperando_min}-{ativo}',
        direction='inbound', message_type='text', from_number=conv.phone_number,
        to_number=conta.phone_number, text_body='Cadê meu pedido?',
    )
    quando = timezone.now() - timedelta(minutes=esperando_min)
    Message.objects.filter(conversation=conv).update(created_at=quando)
    Conversation.objects.filter(pk=conv.pk).update(
        last_customer_message_at=quando, last_agent_message_at=quando - timedelta(hours=1),
    )
    return loja, conv


@pytest.mark.django_db
class TestAvisoFilaHumana:
    def test_desligado_nada_sai(self):
        from apps.conversations.tasks import avisar_fila_humana

        _cenario(ativo=False)
        with patch('apps.automation.mensageiro.canal.enviar_texto') as canal, \
             patch('apps.whatsapp.services.message_service.MessageService.send_text_message') as direto:
            enviados = avisar_fila_humana()

        assert enviados == 0
        canal.assert_not_called()
        direto.assert_not_called()

    def test_sem_config_nada_sai(self):
        from apps.conversations.tasks import avisar_fila_humana

        loja, _ = _cenario()
        loja.metadata = {}
        loja.save(update_fields=['metadata'])
        with patch('apps.automation.mensageiro.canal.enviar_texto') as canal:
            assert avisar_fila_humana() == 0
        canal.assert_not_called()

    def test_ligado_avisa_uma_vez_por_espera(self):
        from apps.conversations.tasks import avisar_fila_humana

        loja, conv = _cenario(ativo=True, apos=5, esperando_min=12)
        with patch('apps.automation.mensageiro.canal.enviar_texto', return_value=object()) as canal:
            assert avisar_fila_humana() == 1
            assert avisar_fila_humana() == 0  # mesma espera: não repete

        canal.assert_called_once()
        conta, telefone, texto = canal.call_args.args[:3]
        assert telefone == '5563988887777'
        assert canal.call_args.kwargs['evento'] == 'fila_humana'
        assert texto == "⏳ Joana está esperando atendimento há 12 min na Cê Saladas. Última mensagem: 'Cadê meu pedido?'"
        conv.refresh_from_db()
        assert conv.context['aviso_fila']['esperando_desde']

    def test_espera_curta_nao_avisa(self):
        from apps.conversations.tasks import avisar_fila_humana

        _cenario(ativo=True, apos=15, esperando_min=12)
        with patch('apps.automation.mensageiro.canal.enviar_texto') as canal:
            assert avisar_fila_humana() == 0
        canal.assert_not_called()

    def test_politica_calou_usa_message_service_direto(self):
        from apps.conversations.tasks import avisar_fila_humana

        _cenario()
        with patch('apps.automation.mensageiro.canal.enviar_texto', return_value=None), \
             patch('apps.whatsapp.services.message_service.MessageService.send_text_message') as direto:
            assert avisar_fila_humana() == 1

        meta = direto.call_args.kwargs['metadata']
        assert meta['automatico'] is True and meta['evento'] == 'fila_humana'


def test_beat_agenda_o_aviso_e_a_tarefa_existe():
    from config.celery import app

    app.loader.import_default_modules()
    agendadas = {e['task']: e for e in app.conf.beat_schedule.values()}
    assert NOME_DA_TAREFA in agendadas
    assert agendadas[NOME_DA_TAREFA]['schedule'] == 120.0
    assert NOME_DA_TAREFA in app.tasks
