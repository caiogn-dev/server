"""
Duas execuções do beat não podem processar o mesmo evento.

Regressão (S2-RACE-005): o `with transaction.atomic()` fechava logo depois de
materializar a lista, então TODOS os locks de `select_for_update(skip_locked=True)`
caíam antes de qualquer processamento — e os eventos continuavam PENDING no banco.
O beat roda a cada 30s; um lote de 100 eventos leva 50-150s (pipeline do bot +
HTTP ao Meta). A execução seguinte re-selecionava tudo que a anterior ainda não
tinha alcançado: 2 a 5 execuções sobrepostas, cliente recebendo resposta repetida
e 2-5x de chamadas contra o rate limit da WABA.

O `skip_locked` dava falsa sensação de segurança: não havia mais lock para pular.

Conserto: reservar (PENDING→PROCESSING) dentro da MESMA transação do lock. Como
isso cria a possibilidade de evento preso caso o worker morra, a task também
recicla PROCESSING antigos antes de reservar.
"""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.whatsapp.models import WebhookEvent, WhatsAppAccount
from apps.whatsapp.tasks.legacy_tasks import process_pending_webhook_events


@pytest.fixture
def conta(db):
    return WhatsAppAccount.objects.create(
        phone_number_id='pid-race-005',
        waba_id='waba-race-005',
        phone_number='+5563999990005',
        is_active=True,
    )


def _evento(conta, wamid):
    return WebhookEvent.objects.create(
        account=conta,
        event_id=wamid,  # unique no modelo
        event_type=WebhookEvent.EventType.MESSAGE,
        payload={
            'message': {'id': wamid, 'type': 'text', 'text': {'body': 'oi'},
                        'from': '5563999547790', 'timestamp': '1785000000'},
            'contact': {'wa_id': '5563999547790', 'profile': {'name': 'Cliente'}},
        },
    )


@pytest.mark.django_db
class TestReservaDoLote:

    def test_evento_reservado_nao_e_pego_pela_execucao_seguinte(self, conta):
        """O cenário do beat sobreposto."""
        for i in range(3):
            _evento(conta, f'wamid.LOTE-{i}')

        vistos = []

        def registra(event, post_process_inbound=True):
            vistos.append(str(event.id))

        with patch(
            'apps.whatsapp.services.webhook_service.WebhookService.process_event',
            side_effect=registra,
        ):
            process_pending_webhook_events(batch_size=100)
            primeira_leva = list(vistos)
            # segunda execução do beat, com a primeira "ainda em voo"
            process_pending_webhook_events(batch_size=100)

        assert len(primeira_leva) == 3
        assert vistos == primeira_leva, (
            f'a segunda execução repescou {len(vistos) - len(primeira_leva)} evento(s) '
            f'já reservado(s) — é isso que duplica a resposta ao cliente'
        )

    def test_lote_fica_marcado_como_processing(self, conta):
        _evento(conta, 'wamid.MARCA')
        with patch('apps.whatsapp.services.webhook_service.WebhookService.process_event'):
            process_pending_webhook_events(batch_size=10)
        assert not WebhookEvent.objects.filter(
            processing_status=WebhookEvent.ProcessingStatus.PENDING
        ).exists()

    def test_evento_preso_em_processing_e_reciclado(self, conta):
        """Worker morreu no meio: o evento não pode ficar órfão para sempre."""
        ev = _evento(conta, 'wamid.ORFAO')
        WebhookEvent.objects.filter(pk=ev.pk).update(
            processing_status=WebhookEvent.ProcessingStatus.PROCESSING,
            updated_at=timezone.now() - timedelta(minutes=30),
        )
        vistos = []
        with patch(
            'apps.whatsapp.services.webhook_service.WebhookService.process_event',
            side_effect=lambda event, post_process_inbound=True: vistos.append(str(event.id)),
        ):
            process_pending_webhook_events(batch_size=10)
        assert str(ev.id) in vistos, 'evento órfão nunca mais seria processado'

    def test_processing_recente_nao_e_roubado(self, conta):
        """Reciclagem não pode atropelar quem está processando agora."""
        ev = _evento(conta, 'wamid.EM-VOO')
        WebhookEvent.objects.filter(pk=ev.pk).update(
            processing_status=WebhookEvent.ProcessingStatus.PROCESSING,
            updated_at=timezone.now(),
        )
        vistos = []
        with patch(
            'apps.whatsapp.services.webhook_service.WebhookService.process_event',
            side_effect=lambda event, post_process_inbound=True: vistos.append(str(event.id)),
        ):
            process_pending_webhook_events(batch_size=10)
        assert vistos == []
