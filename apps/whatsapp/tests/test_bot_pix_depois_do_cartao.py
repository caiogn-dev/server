"""Cliente que escolheu Cartão e quer pagar por PIX não pode ficar preso.

CASO REAL (06/10, Cê Saladas): Lívia tocou em *Cartão*, o pedido CE-2610061613
nasceu com link do Mercado Pago. Daí em diante tudo que ela escreveu virou
"✅ Anotado: …" ("É puxado", "Cadê o pix") e cada toque em *PIX* respondeu
"❌ Não encontrei itens no seu pedido" — seis vezes, até um atendente mandar a
chave PIX na mão. Mesma coisa com a Ray (CE-2610068835) uma hora antes.

CAUSA (trilha da sessão): `order_finalized` às 14:54:35 SEM `notes_wait_cleared`.
A tarefa de finalização abre a sessão ANTES de criar o pedido (cópia com
`waiting_for_notes=True`); o `_fechar_checkout` desliga a espera, e em seguida
a tarefa chama `clear_pending_order_items()` com a cópia velha e grava o
`cart_data` inteiro por cima — a espera de observação volta.

Regras:
1. Mexer na sessão relê o banco antes: cópia velha não desfaz o fechamento.
2. PIX sem itens, com pedido recente não pago: gera o PIX DESSE pedido.
3. PIX que o Mercado Pago não gerou: manda a chave PIX da loja com o valor.
4. "pix" digitado no passo de observação é escolha de pagamento, não recado.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import CompanyProfile, CustomerSession
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreOrder, StoreProduct
from apps.whatsapp.intents.handlers.interactive import InteractiveReplyHandler
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()

PHONE = '5563992195902'
CHAVE = '55599700000136'


class _Base(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dono-pix', email='d@pix.com', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Teste', slug='ce-teste-pix', owner=dono,
            metadata={'chave_pix': CHAVE, 'chave_pix_titular': 'CAIO G NASCIMENTO'},
        )
        self.account = WhatsAppAccount.objects.create(name='Cê', phone_number_id='PHCE', waba_id='WCE')
        self.store.whatsapp_account = self.account
        self.store.save(update_fields=['whatsapp_account'])
        self.profile = CompanyProfile.objects.get(store=self.store)
        self.profile.account = self.account
        CompanyProfile.objects.filter(account=self.account).exclude(pk=self.profile.pk).delete()
        self.profile.save()
        self.conversation = Conversation.objects.create(account=self.account, phone_number=PHONE)
        self.produto = StoreProduct.objects.create(
            store=self.store, name='Almôndega Premium', slug='almondega', price=44.99, is_active=True,
        )

    def _handler(self):
        return InteractiveReplyHandler(self.account, self.conversation, self.profile)

    def _pedido_no_cartao(self, **extra):
        dados = dict(
            store=self.store, customer_name='Livia', customer_phone=PHONE,
            subtotal=Decimal('44.99'), delivery_fee=Decimal('11.56'), total=Decimal('56.55'),
            payment_method='credit_card', payment_status='pending', status='pending',
            source='whatsapp',
        )
        dados.update(extra)
        return StoreOrder.objects.create(**dados)

    def _clicar(self, reply_id):
        return self._handler().handle({'reply_id': reply_id, 'reply_title': '', 'original_message': ''})


class CopiaVelhaNaoReabreObservacaoTest(_Base):
    def test_limpar_itens_com_copia_velha_nao_volta_a_esperar_observacao(self):
        """A sequência exata da tarefa de finalização."""
        h = self._handler()
        velha = h._get_session_manager()
        velha.save_pending_order_items([{'product_id': str(self.produto.id), 'quantity': 1, 'price': 44.99}])
        velha.set_waiting_for_notes(True)
        velha.get_pending_order_items()            # a tarefa lê a sessão aqui

        h._fechar_checkout()                       # o pedido nasce: espera desligada
        velha.clear_pending_order_items()          # a tarefa limpa com a cópia velha

        self.assertFalse(h._get_session_manager().is_waiting_for_notes())


class PixDepoisDoCartaoTest(_Base):
    def test_pix_sem_itens_gera_o_pix_do_pedido_que_esta_esperando_pagamento(self):
        pedido = self._pedido_no_cartao()
        with patch(
            'apps.whatsapp.services.order_service.WhatsAppOrderService._generate_pix',
            return_value={'success': True, 'pix_code': '00020126PIXNOVO'},
        ):
            resultado = self._clicar('pay_pix')

        self.assertIn('00020126PIXNOVO', resultado.response_text or '')
        pedido.refresh_from_db()
        self.assertEqual(pedido.payment_method, 'pix')

    def test_mercado_pago_falhou_manda_a_chave_da_loja_com_o_valor(self):
        self._pedido_no_cartao()
        with patch(
            'apps.whatsapp.services.order_service.WhatsAppOrderService._generate_pix',
            return_value={'success': False, 'error': 'gateway fora'},
        ):
            resultado = self._clicar('pay_pix')

        texto = resultado.response_text or ''
        self.assertIn(CHAVE, texto)
        self.assertIn('56,55', texto)
        self.assertNotIn('Não encontrei itens', texto)

    def test_pedido_ja_pago_nao_e_cobrado_de_novo(self):
        self._pedido_no_cartao(payment_status='paid')
        with patch('apps.whatsapp.services.order_service.WhatsAppOrderService._generate_pix') as gerar:
            self._clicar('pay_pix')
        gerar.assert_not_called()


class FallbackNoPedidoNovoTest(_Base):
    def test_pix_que_nao_gerou_no_pedido_novo_manda_a_chave(self):
        pedido = self._pedido_no_cartao(payment_method='pix')
        with patch(
            'apps.whatsapp.services.create_order_from_whatsapp',
            return_value={
                'success': True, 'order': pedido, 'payment_method': 'pix',
                'payment_data': {'success': False, 'error': 'gateway fora'},
            },
        ):
            resultado = self._handler()._finalize_order(
                [{'product_id': str(self.produto.id), 'quantity': 1}],
                delivery_method='delivery', payment_method='pix',
            )
        self.assertIn(CHAVE, resultado.response_text or '')
        self.assertIn(pedido.order_number, resultado.response_text or '')


class PixDigitadoNaObservacaoTest(_Base):
    def test_pode_ser_pix_escolhe_pix_em_vez_de_anotar(self):
        h = self._handler()
        sm = h._get_session_manager()
        sm.save_pending_order_items([{'product_id': str(self.produto.id), 'quantity': 1, 'price': 44.99}])
        sm.set_waiting_for_notes(True)

        with patch('apps.whatsapp.tasks.checkout_tasks.finalize_whatsapp_order_task.delay') as delay:
            resultado = h._handle_notes_input('Pode ser pix')

        self.assertNotIn('Anotado', resultado.response_text or str(resultado.interactive_data or ''))
        delay.assert_called_once()
        self.assertEqual(delay.call_args.kwargs['payment_method'], 'pix')


class RegiaoRecusouNoBotTest(_Base):
    """Paraíso/Porto (06/10): se a região recusa (categoria, pagamento na
    entrega), o cliente lê o MOTIVO — não 'não conseguimos finalizar'."""

    def test_motivo_da_regiao_chega_ao_cliente(self):
        with patch(
            'apps.whatsapp.services.create_order_from_whatsapp',
            return_value={'success': False, 'regiao': True,
                          'error': 'Para Paraíso do Tocantins não entregamos: Salada Caesar.'},
        ):
            resultado = self._handler()._finalize_order(
                [{'product_id': str(self.produto.id), 'quantity': 1}],
                delivery_method='delivery', payment_method='pix',
            )
        self.assertIn('Salada Caesar', resultado.response_text or '')
        self.assertNotIn('Não conseguimos finalizar', resultado.response_text or '')
