"""
Retry de webhook não pode criar um segundo pedido.

Regressão (S2-RACE-004): `_process_inbound_message` sinalizava "já existe"
devolvendo a própria Message — um objeto truthy. O chamador fazia
`if post_process_inbound and message: post_process_inbound_message(...)`, então
reconhecer a duplicata NÃO impedia o pipeline de rodar de novo.

Isso disparava sozinho: qualquer evento que falhasse DEPOIS de criar a Message
(a Message nasce cedo; o bot roda depois) era re-executado por
`retry_failed_webhook_events` a cada 5min, até 3x. Cliente clica "Fechar pedido",
o handler cria pedido + PIX + baixa de estoque, o envio da resposta ao Meta dá
timeout → 5min depois tudo acontece de novo. Até 3 pedidos fantasma que a cozinha
produz de verdade.

O conserto é uma reserva: `pipeline_processed_at` é marcado por UPDATE condicional,
e só quem consegue marcar roda o pipeline. Serve também de lock entre dois workers.
"""
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.whatsapp.models import Message, WebhookEvent, WhatsAppAccount
from apps.whatsapp.services.webhook_service import WebhookService

WAMID = 'wamid.TESTE-RACE-004'


@pytest.fixture
def conta(db):
    return WhatsAppAccount.objects.create(
        phone_number_id='pid-race-004',
        waba_id='waba-race-004',
        phone_number='+5563999990000',
        is_active=True,
    )


@pytest.fixture
def evento(conta):
    return WebhookEvent.objects.create(
        account=conta,
        event_type=WebhookEvent.EventType.MESSAGE,
        payload={
            'message': {'id': WAMID, 'type': 'text', 'text': {'body': 'fechar pedido'},
                        'from': '5563999547790', 'timestamp': '1785000000'},
            'contact': {'wa_id': '5563999547790', 'profile': {'name': 'Cliente'}},
        },
    )


@pytest.mark.django_db
class TestPipelineRodaUmaVezSo:

    def test_reprocessar_o_mesmo_evento_nao_roda_o_pipeline_de_novo(self, evento):
        """O cenário do pedido fantasma: mesmo evento, duas execuções."""
        svc = WebhookService()
        with patch.object(svc, 'post_process_inbound_message') as pipeline:
            svc.process_event(evento, post_process_inbound=True)
            primeira = pipeline.call_count

            evento.processing_status = WebhookEvent.ProcessingStatus.PENDING
            evento.save(update_fields=['processing_status'])
            svc.process_event(evento, post_process_inbound=True)

        assert primeira == 1, 'o pipeline deveria ter rodado na primeira vez'
        assert pipeline.call_count == 1, (
            f'pipeline rodou {pipeline.call_count}x — cada volta extra é um pedido, '
            f'um PIX e uma baixa de estoque duplicados'
        )

    def test_marca_a_mensagem_como_processada(self, evento):
        svc = WebhookService()
        with patch.object(svc, 'post_process_inbound_message'):
            svc.process_event(evento, post_process_inbound=True)
        msg = Message.objects.get(whatsapp_message_id=WAMID)
        assert msg.pipeline_processed_at is not None

    def test_mensagem_ja_marcada_nunca_reprocessa(self, evento, conta):
        """Simula o worker concorrente que chegou primeiro."""
        Message.objects.create(
            account=conta, whatsapp_message_id=WAMID,
            direction=Message.MessageDirection.INBOUND,
            message_type=Message.MessageType.TEXT,
            from_number='5563999547790', to_number='+5563999990000',
            content={'text': 'fechar pedido'}, text_body='fechar pedido',
            pipeline_processed_at=timezone.now(),
        )
        svc = WebhookService()
        with patch.object(svc, 'post_process_inbound_message') as pipeline:
            svc.process_event(evento, post_process_inbound=True)
        assert pipeline.call_count == 0

    def test_sem_post_process_nao_marca(self, evento):
        """Quem não pede pipeline não deve queimar a reserva de quem vai pedir."""
        svc = WebhookService()
        svc.process_event(evento, post_process_inbound=False)
        msg = Message.objects.get(whatsapp_message_id=WAMID)
        assert msg.pipeline_processed_at is None
