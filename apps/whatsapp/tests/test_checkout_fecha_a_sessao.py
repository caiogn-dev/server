"""O pedido nasceu: o checkout FECHA e os handlers param de escutar.

31/08, Dênia × Cê Saladas. O bot mostrou o resumo e perguntou "Alguma
observação?", marcando a sessão como `waiting_for_notes`. Ela **não digitou** —
tocou no botão *💳 Cartão*. O pedido CE-2608318490 nasceu, o link foi enviado, e
`_finalize_order` **não desmarcou nada**.

A sessão ficou parada no passo de observação para sempre. Daí em diante toda
mensagem dela caiu no handler errado (`fallback.py` roteia por
`is_waiting_for_notes()`), e a conversa virou isto:

    Cliente: Olá! Gostaria de confirmar meu pedido #ac83efdc-…
    Bot:     ✅ _Anotado: …_  💳 Como prefere pagar?
    Cliente: Já foi pago
    Bot:     Hmm, não encontrei nenhum PIX pendente no seu nome…

Não é o handler de observação que está errado — é a HORA em que ele roda.
Enquanto o checkout não fecha, o bot responde a um pedido que já existe como se
ele ainda estivesse sendo montado.

Contrato: pedido criado com sucesso ⇒ `waiting_for_notes` e `waiting_for_address`
desligados, itens pendentes limpos. Pedido que FALHOU não fecha nada — o cliente
precisa poder corrigir e tentar de novo.
"""
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import CompanyProfile
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreOrder, StoreProduct
from apps.whatsapp.intents.handlers.interactive import InteractiveReplyHandler
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()
PHONE = '556384122444'


class CheckoutFechaASessaoTest(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='dona-ce-fs', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-saladas-fs', owner=owner,
        )
        self.account = WhatsAppAccount.objects.create(
            name='CeFs', phone_number_id='PHFS', waba_id='WFS',
        )
        self.store.whatsapp_account = self.account
        self.store.save(update_fields=['whatsapp_account'])
        self.profile = CompanyProfile.objects.get(store=self.store)
        self.profile.account = self.account
        CompanyProfile.objects.filter(account=self.account).exclude(pk=self.profile.pk).delete()
        self.profile.save()
        self.conversation = Conversation.objects.create(account=self.account, phone_number=PHONE)
        self.produto = StoreProduct.objects.create(
            store=self.store, name='Almôndega Premium', slug='almondega-premium-fs',
            price=Decimal('35.99'), is_active=True,
        )
        self.handler = InteractiveReplyHandler(self.account, self.conversation, self.profile)
        # A sessão está exatamente como ficou para a Dênia: esperando observação.
        self.sessao = self.handler._get_session_manager()
        self.sessao.set_waiting_for_notes(True)

    def _pedido(self):
        return StoreOrder.objects.create(
            store=self.store, customer_name='DENIA OLIVEIRA',
            customer_email='d@t.com', customer_phone=PHONE,
            subtotal=Decimal('35.99'), total=Decimal('35.99'),
            payment_method='credit_card',
        )

    def _finalizar(self, sucesso=True, metodo='card'):
        pedido = self._pedido() if sucesso else None
        resultado = (
            {
                'success': True, 'order': pedido, 'payment_method': metodo,
                'payment_data': {'success': True, 'checkout_link': 'https://mp/x', 'pix_code': '000201PIX'},
            }
            if sucesso else
            {'success': False, 'error': 'Erro desconhecido'}
        )
        # `whatsapp_service` é property preguiçosa que decripta o token da
        # conta; injetar o cache evita a rede (e o InvalidToken do token falso).
        self.handler._whatsapp_service = mock.Mock()
        with mock.patch(
            'apps.whatsapp.services.create_order_from_whatsapp', return_value=resultado,
        ):
            saida = self.handler._finalize_order(
                items=[{'product_id': str(self.produto.id), 'quantity': 1}],
                delivery_method='pickup', payment_method=metodo,
            )
        return pedido, saida

    # --- o caso da Dênia -------------------------------------------------

    def test_pedido_criado_desliga_a_espera_de_observacao(self):
        self.assertTrue(self.sessao.is_waiting_for_notes(), 'pré-condição do teste')

        self._finalizar()

        self.assertFalse(
            self.handler._get_session_manager().is_waiting_for_notes(),
            'checkout não fechou — a próxima mensagem do cliente vira observação',
        )

    def test_pedido_criado_desliga_a_espera_de_endereco(self):
        self.sessao.set_waiting_for_address(True)

        self._finalizar()

        self.assertFalse(self.handler._get_session_manager().is_waiting_for_address())

    def test_vale_para_o_pix_tambem(self):
        self._finalizar(metodo='pix')

        self.assertFalse(self.handler._get_session_manager().is_waiting_for_notes())

    def test_itens_pendentes_saem_do_carrinho(self):
        # Sem limpar, o próximo pedido nasce com os itens do anterior colados.
        self.sessao.save_pending_order_items([{'product_id': str(self.produto.id), 'quantity': 1}])

        self._finalizar()

        self.assertEqual(self.handler._get_session_manager().get_pending_order_items(), [])

    # --- o que NÃO pode regredir ----------------------------------------

    def test_pedido_que_falhou_mantem_o_checkout_aberto(self):
        # Se o estoque acabou ou o gateway caiu, o cliente precisa poder
        # corrigir e tentar de novo — fechar aqui o deixaria sem caminho.
        self._finalizar(sucesso=False)

        self.assertTrue(
            self.handler._get_session_manager().is_waiting_for_notes(),
            'checkout fechou mesmo com o pedido falhando',
        )
