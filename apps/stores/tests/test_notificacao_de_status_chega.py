"""
A notificação de status precisa CHEGAR, não só ser "enviada".

Relato do dono (29/ago): "nem a mensagem de cancelamento foi enviada".

Levantamento: entre 2.446 mensagens com metadata no banco, existem
`unified_handler`, `whatsapp_inbox_page`, `feedback_request`, `unified_llm`,
`ai_agent` e outras — e NENHUMA de notificação de status. Nunca saiu uma.
Não é só o cancelamento: confirmado, em preparo, saiu para entrega e entregue
também nunca chegaram a ninguém.

O log, porém, dizia "Status notification sent for order ...: cancelled",
às 15:09:58 do mesmo dia. O sistema achava que tinha enviado.

Duas falhas na mesma chamada de `notify_order_status_change`:

1. `to=order.customer_phone` mandava o telefone CRU. No banco ele está como
   "63999451408", sem o 55 — a API do WhatsApp precisa do país. O outro
   caminho de notificação (`OrderService._send_status_notification`) usa
   `normalize_phone_number` e manda "5563999451408"; a campanha que funcionou
   no mesmo dia foi para "556392433905". O contrato sempre foi com o 55.

2. O `logger.info("... sent ...")` vinha depois da chamada, sem olhar o
   retorno. Um log que afirma sucesso sem verificar é pior do que log nenhum:
   esconde a falha e faz procurar no lugar errado.
"""
from unittest import mock

import pytest

from apps.core.models import User
from apps.stores.models import Store, StoreOrder


pytestmark = pytest.mark.django_db


@pytest.fixture
def pedido(db):
    dono = User.objects.create_user(
        username='dono-notif', email='dono-notif@example.com', password='x'
    )
    loja = Store.objects.create(name='Notif', slug='loja-notif', owner=dono)
    return StoreOrder.objects.create(
        store=loja,
        order_number='CE-TESTE-0001',
        customer_name='Cliente',
        # Como está no banco de produção: sem o código do país.
        customer_phone='63999451408',
        status='pending',
        subtotal=50,
        total=50,
    )


class _ContaFalsa:
    """A loja de teste não tem conta de WhatsApp; o que importa aqui é o
    NÚMERO que sai, não de qual conta sai."""
    id = 'conta-de-teste'
    phone_number_id = '000'


def _disparar(pedido, status='cancelled'):
    """Roda a task capturando o que foi para o WhatsApp."""
    from apps.whatsapp.tasks import automation_tasks

    with mock.patch.object(
        automation_tasks, '_get_account_for_profile', return_value=_ContaFalsa()
    ), mock.patch(
        'apps.whatsapp.services.message_service.MessageService.send_text_message'
    ) as enviar:
        enviar.return_value = {'messages': [{'id': 'wamid.teste'}]}
        automation_tasks.notify_order_status_change(str(pedido.id), status)
    return enviar


class TestONumeroQueVaiParaOWhatsApp:
    def test_sai_com_o_codigo_do_pais(self, pedido):
        enviar = _disparar(pedido)
        assert enviar.called, 'a task não chegou a enviar nada'
        destino = enviar.call_args.kwargs.get('to') or enviar.call_args.args[1]
        assert destino.startswith('55'), (
            f'foi para {destino!r}: sem o 55 a mensagem não chega a ninguém'
        )

    def test_nao_duplica_o_55_de_quem_ja_tem(self, pedido):
        pedido.customer_phone = '5563999451408'
        pedido.save(update_fields=['customer_phone'])
        enviar = _disparar(pedido)
        assert enviar.called, 'a task não chegou a enviar nada'
        destino = enviar.call_args.kwargs.get('to') or enviar.call_args.args[1]
        assert not destino.startswith('5555'), f'ficou {destino!r}'

    def test_telefone_vazio_nao_vira_envio_para_o_vazio(self, pedido):
        pedido.customer_phone = ''
        pedido.save(update_fields=['customer_phone'])
        enviar = _disparar(pedido)
        assert not enviar.called, 'sem telefone não há para quem mandar'
