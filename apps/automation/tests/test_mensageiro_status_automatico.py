"""Aviso de status e convite de avaliação saem marcados como automáticos.

Já passavam pelo MessageService (ficavam gravados), mas sem a marca: cada
"saiu para entrega" atualizava `last_agent_message_at` e tirava da Fila
humana um cliente que estava esperando uma pessoa.
"""
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

from apps.automation.models import AutoMessage, CompanyProfile
from apps.stores.models import Store, StoreOrder
from apps.whatsapp.tasks import automation_tasks

TEXTO = 'apps.whatsapp.services.message_service.MessageService.send_text_message'
BOTOES = 'apps.whatsapp.services.message_service.MessageService.send_interactive_buttons'


class _Conta:
    id = 'conta-fake'


@pytest.fixture(autouse=True)
def _limpo():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def pedido(db):
    dono = get_user_model().objects.create_user(username='dono-status-auto', password='x')
    loja = Store.objects.create(owner=dono, name='Loja Status', slug='loja-status-automatico')
    CompanyProfile.objects.get_or_create(store=loja)
    return StoreOrder.objects.create(
        store=loja, total=Decimal('30'), subtotal=Decimal('30'),
        status='delivered', payment_status='paid', payment_method='pix',
        customer_name='Leo', customer_phone='63999990901',
    )


def _template(pedido, event_type):
    AutoMessage.objects.create(
        company=pedido.store.automation_profile, event_type=event_type, name=event_type,
        message_text='Oi {customer_name}', is_active=True,
    )


@pytest.mark.django_db
class TestStatusAutomatico:

    def test_aviso_de_status_com_template(self, pedido):
        _template(pedido, 'order_delivered')
        with patch.object(automation_tasks, '_get_account_for_profile', return_value=_Conta()), \
                patch(TEXTO) as envio:
            automation_tasks.notify_order_status_change.apply(args=[str(pedido.id), 'delivered'])

        meta = envio.call_args.kwargs['metadata']
        assert meta['automatico'] is True
        assert meta['evento'] == 'order_delivered'

    def test_convite_de_avaliacao(self, pedido):
        _template(pedido, 'feedback_request')
        with patch.object(automation_tasks, '_get_account_for_profile', return_value=_Conta()), \
                patch(BOTOES) as envio:
            automation_tasks.request_feedback.apply(args=[str(pedido.id)])

        meta = envio.call_args.kwargs['metadata']
        assert meta['automatico'] is True
        assert meta['evento'] == 'feedback_request'


def test_aviso_sem_template_tambem_marca():
    """O caminho de reserva (sem template) mora no modelo do pedido."""
    fonte = Path('apps/stores/models/order.py').read_text()
    trecho = fonte[fonte.index("'source': 'store_order_notification'"):][:600]
    assert "'automatico': True" in trecho


def test_nenhuma_tarefa_automatica_envia_direto_pela_meta():
    """Toda mensagem automática passa pelo canal (grava + marca).

    `WhatsAppAPIService(...)` direto numa tarefa = mensagem que o cliente
    recebe e o painel nunca mostra — era assim até 19/09.
    """
    fonte = Path('apps/whatsapp/tasks/automation_tasks.py').read_text()
    assert 'WhatsAppAPIService(' not in fonte
