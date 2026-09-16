"""Pedido cancelado avisa o cliente UMA vez.

14/set/2026: "❌ Pedido Cancelado" saiu duas vezes, no mesmo segundo, para o
mesmo número — 9 casos em 14 dias. `cancel_order` salvava o pedido como
'cancelled' (o post_save despacha `notify_order_status_change`, idempotente por
pedido+status) E, com `notify_customer=True`, mandava de novo por
`_send_status_notification`. Duas portas para a mesma mensagem; a trava de
repetição só existia numa delas.

O `update_status` já tinha aprendido isso ("Do NOT call automation_service
here — that would send the message twice"). O cancelamento, não.
"""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from apps.stores.models import Store, StoreOrder
from apps.stores.services.order_service import OrderService

User = get_user_model()


@pytest.fixture
def pedido(db):
    dono = User.objects.create_user(username='dono_cancel_uma_vez', password='x')
    loja = Store.objects.create(owner=dono, name='Loja Aviso', slug='loja-aviso-uma-vez')
    return StoreOrder.objects.create(
        store=loja, total=Decimal('50.00'), subtotal=Decimal('50.00'),
        status='confirmed', payment_status='pending', payment_method='pix',
        customer_name='Wanny', customer_phone='5563992338269',
    )


@pytest.mark.django_db
def test_cancelar_com_aviso_dispara_uma_notificacao_so(pedido, django_capture_on_commit_callbacks):
    with patch('apps.whatsapp.tasks.automation_tasks.notify_order_status_change.delay') as tarefa, \
         patch.object(OrderService, '_send_status_notification') as envio_direto, \
         django_capture_on_commit_callbacks(execute=True):
        OrderService().cancel_order(pedido, reason='cliente desistiu', restore_stock=False, notify_customer=True)

    envio_direto.assert_not_called()
    chamadas_de_cancelado = [c for c in tarefa.call_args_list if c.args[1:] == ('cancelled',)]
    assert len(chamadas_de_cancelado) == 1
