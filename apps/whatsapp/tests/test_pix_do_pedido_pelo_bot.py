"""O pedido fechado pelo agente do WhatsApp nunca entregava o PIX.

A ferramenta `finalizar_pedido` (langchain_service) lê `result.get("pix_code")`,
mas `WhatsAppOrderService.create_order_from_cart` devolve o PIX dentro de
`result["pix_data"]` — nos dois caminhos, nunca como `pix_code`. Então:

  - PIX gerado com sucesso: o cliente lia SEMPRE "PIX sendo gerado — use
    consultar_pagamento em instantes." e precisava de mais uma volta para
    receber o código que já existia;
  - PIX que falhou: a mesma frase virava mentira. Não há PIX nenhum, e o
    `consultar_pagamento` seguinte responde "Nenhum PIX pendente".

E quando a cobrança LEVANTA (loja sem credencial do Mercado Pago, MP fora do
ar), `_generate_pix` engolia a exceção sem tocar no pedido: ele ficava
`payment_status='pending'` sem cobrança nenhuma. É a cobrança fantasma que o
checkout do site deixou de fazer em 17/set (`_cobranca_que_explodiu`), viva no
canal do bot.
"""
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.agents.services.resposta_do_pedido import resposta_do_pedido_criado
from apps.stores.models import StoreOrder
from apps.stores.tests.factories import make_product, make_store
from apps.whatsapp.services.order_service import WhatsAppOrderService

CODIGO_PIX = '00020126580014br.gov.bcb.pix0136abc'


class TestTextoDoPedidoCriado:
    """O que o agente responde ao cliente depois de `finalizar_pedido`."""

    def _resultado(self, pix_data):
        return {
            'success': True, 'order_number': 'CE-2609181234',
            'total': 58.9, 'pix_data': pix_data,
        }

    def test_pix_gerado_vai_junto_da_confirmacao(self):
        texto = resposta_do_pedido_criado(self._resultado(
            {'success': True, 'pix_code': CODIGO_PIX},
        ))

        assert CODIGO_PIX in texto
        assert 'CE-2609181234' in texto

    def test_pix_que_falhou_nao_promete_pix_a_caminho(self):
        texto = resposta_do_pedido_criado(self._resultado(
            {'success': False, 'error': 'Credenciais de pagamento nao configuradas'},
        ))

        assert 'sendo gerado' not in texto.lower()
        assert 'consultar_pagamento' not in texto

    def test_pix_que_falhou_diz_que_o_pedido_esta_salvo(self):
        texto = resposta_do_pedido_criado(self._resultado({'success': False}))

        assert 'CE-2609181234' in texto
        assert 'salvo' in texto.lower()

    def test_erro_interno_nao_chega_ao_cliente(self):
        texto = resposta_do_pedido_criado(self._resultado(
            {'success': False, 'error': 'Credenciais de pagamento nao configuradas'},
        ))

        assert 'Credenciais' not in texto


@pytest.mark.django_db
class TestCobrancaQueExplodeNoBot:
    def test_pedido_fica_failed_em_vez_de_pendente_fantasma(self):
        store = make_store()
        produto = make_product(store, price=Decimal('30.00'))
        svc = WhatsAppOrderService(
            store=store, phone_number='5563999990042', customer_name='Cliente Bot',
        )
        with patch(
            'apps.stores.services.checkout_service.CheckoutService.create_payment',
            side_effect=ValueError('Credenciais de pagamento nao configuradas'),
        ):
            r = svc.create_order_from_cart(
                items=[{'product_id': str(produto.id), 'quantity': 1, 'unit_price': 30.0}],
                delivery_address='Q. 110 Sul Alameda 3, 51',
                delivery_method='delivery', payment_method='pix',
                delivery_fee_override=0,
            )

        assert r['success'] is True, r
        pedido = StoreOrder.objects.get(order_number=r['order_number'])
        assert pedido.payment_status == StoreOrder.PaymentStatus.FAILED
