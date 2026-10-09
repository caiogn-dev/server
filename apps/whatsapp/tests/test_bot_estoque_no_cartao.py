"""Item esgotado no checkout não pode virar "seu pedido já está pago".

CASO REAL (09/10, Cê Saladas, Juliana): montou Filé de Frango + Suco de
Laranja pelo catálogo, informou endereço, tocou em *Cartão*. Os dois produtos
estavam com estoque 0 no painel — o pedido não nasceu ("⚠️ itens
indisponíveis"). Logo depois chegou "🧾 Pedido recebido! Gerando seu link…".
No toque seguinte em *Cartão* o bot respondeu "Seu pedido #CE-2610014115 já
está pago ✅" — um pedido DELA, de 01/10, entregue havia 8 dias.

Não foi a LLM: é fluxo determinístico.
1. A tarefa de finalização limpava os itens pendentes sempre que a resposta
   não começava com "❌ Erro ao criar pedido" — o aviso de estoque começa com
   "⚠️", então o carrinho foi apagado num pedido que NÃO existia.
2. Com o carrinho vazio, `_handle_payment_choice` procurava "o último pedido
   deste telefone" sem limite de tempo e, achando um pago, afirmava que o
   pedido atual estava pago.
3. A tarefa rodou em 0,8 s e o aviso de falha saiu ANTES do "Pedido recebido".

Regras:
- Pedido que não nasceu não apaga o carrinho (o sucesso já limpa em
  `_fechar_checkout`).
- "Já está pago" só fala de pedido recente (mesma janela de 6 h do PIX).
- O aviso de estoque diz QUAIS itens acabaram.
- O "processando" chega antes do resultado.
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.utils import timezone

from apps.stores.models import StoreOrder
from apps.whatsapp.tests.test_bot_pix_depois_do_cartao import _Base

ERRO_ESTOQUE = (
    "Erros de estoque: [{'item_id': 'a', 'product_name': 'Suco de Laranja 300ml', "
    "'error': 'Produto fora de estoque'}, {'item_id': 'b', 'product_name': "
    "'Especial Filé de Frango', 'error': 'Produto fora de estoque'}]"
)


class _Estoque(_Base):
    def _carrinho(self):
        sm = self._handler()._get_session_manager()
        sm.save_pending_order_items([{'product_id': str(self.produto.id), 'quantity': 1, 'price': 44.99}])
        sm.set_waiting_for_notes(True)
        return sm

    def _rodar_tarefa(self, retorno):
        from apps.whatsapp.tasks.checkout_tasks import finalize_whatsapp_order_task
        with patch('apps.whatsapp.services.create_order_from_whatsapp', return_value=retorno), \
                patch('apps.whatsapp.tasks.checkout_tasks._send_handler_result') as enviar:
            finalize_whatsapp_order_task.apply(kwargs=dict(
                account_id=str(self.account.id),
                conversation_id=str(self.conversation.id),
                profile_id=str(self.profile.id),
                payment_method='card',
            ))
        return enviar.call_args.args[2]


class EstoqueNaoApagaCarrinhoTest(_Estoque):
    def test_pedido_recusado_por_estoque_mantem_os_itens(self):
        self._carrinho()
        self._rodar_tarefa({'success': False, 'error': ERRO_ESTOQUE})
        itens = self._handler()._get_session_manager().get_pending_order_items()
        self.assertEqual(len(itens or []), 1)

    def test_aviso_diz_quais_itens_acabaram(self):
        self._carrinho()
        resultado = self._rodar_tarefa({'success': False, 'error': ERRO_ESTOQUE})
        self.assertIn('Suco de Laranja 300ml', resultado.response_text)
        self.assertIn('Especial Filé de Frango', resultado.response_text)


class PedidoAntigoNaoEhOAtualTest(_Estoque):
    def test_cartao_sem_itens_nao_diz_que_pedido_de_dias_atras_esta_pago(self):
        antigo = self._pedido_no_cartao(payment_status='paid', status='delivered')
        StoreOrder.objects.filter(pk=antigo.pk).update(created_at=timezone.now() - timedelta(days=8))

        texto = self._clicar('pay_card').response_text or ''

        self.assertNotIn(antigo.order_number, texto)
        self.assertNotIn('já está pago', texto)

    def test_pedido_pago_agora_continua_protegido(self):
        recente = self._pedido_no_cartao(payment_status='paid')
        texto = self._clicar('pay_card').response_text or ''
        self.assertIn(recente.order_number, texto)
        self.assertIn('já está pago', texto)


class AvisoChegaDepoisDoProcessandoTest(_Estoque):
    def test_tarefa_e_agendada_com_atraso(self):
        self._carrinho()
        with patch('apps.whatsapp.intents.handlers.interactive.InteractiveReplyHandler._store_is_open',
                      return_value=True), \
                patch('apps.whatsapp.tasks.checkout_tasks.finalize_whatsapp_order_task.apply_async') as agendar:
            self._clicar('pay_card')
        agendar.assert_called_once()
        self.assertGreaterEqual(agendar.call_args.kwargs.get('countdown', 0), 2)
        self.assertEqual(agendar.call_args.kwargs['kwargs']['payment_method'], 'card')
