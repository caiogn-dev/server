"""O passo de observação não engole quem avisa que pagou.

31/08, conversa real da Dênia com a Cê Saladas. Ela fechou o CE-2608318490 no
cartão, pagou R$ 35,99 no Checkout Pro e voltou pelo botão do Mercado Pago, que
abre o WhatsApp com o texto pronto da página de sucesso. O bot respondeu:

    ✅ _Anotado: Olá! Gostaria de confirmar meu pedido #ac83efdc-…_
    💳 *Como prefere pagar?*

Ela insistiu ("Já foi pago", "Foi pago com cartão") e recebeu um **segundo link
de cobrança** — risco de cobrar duas vezes quem já tinha pagado.

Mesma família do caso Yeda (13/ago): `_handle_notes_input` só sabia distinguir
"palavra de pular" de "observação". Pedido de produto virou a terceira saída;
aviso de pagamento é a quarta, e a mais cara — acontece no minuto em que o
dinheiro entra.

Contrato: no estado de observação, texto que avisa pagamento NÃO vira nota, NÃO
repete a pergunta de pagamento e NUNCA oferece uma segunda cobrança sem antes
olhar o pedido. Observação de verdade continua virando nota.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import CompanyProfile
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreOrder, StoreProduct
from apps.whatsapp.intents.handlers.interactive import InteractiveReplyHandler
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()
PHONE = '556384122444'


class ObservacaoRespeitaPagamentoTest(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='dona-ce-pg', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-saladas-pg', owner=owner,
        )
        self.account = WhatsAppAccount.objects.create(
            name='CePg', phone_number_id='PHPG', waba_id='WPG',
        )
        self.store.whatsapp_account = self.account
        self.store.save(update_fields=['whatsapp_account'])
        self.profile = CompanyProfile.objects.get(store=self.store)
        self.profile.account = self.account
        CompanyProfile.objects.filter(account=self.account).exclude(pk=self.profile.pk).delete()
        self.profile.save()
        self.conversation = Conversation.objects.create(account=self.account, phone_number=PHONE)
        StoreProduct.objects.create(
            store=self.store, name='Almôndega Premium', slug='almondega-premium',
            price=Decimal('35.99'), is_active=True,
        )

    def _pedido(self, payment_status):
        return StoreOrder.objects.create(
            store=self.store, customer_name='DENIA OLIVEIRA',
            customer_email='d@t.com', customer_phone=PHONE,
            subtotal=Decimal('35.99'), total=Decimal('35.99'),
            payment_method='credit_card', payment_status=payment_status,
        )

    def _nota(self, texto):
        handler = InteractiveReplyHandler(self.account, self.conversation, self.profile)
        return self._texto(handler._handle_notes_input(texto))

    @staticmethod
    def _texto(resultado):
        if resultado.use_interactive:
            return (resultado.interactive_data or {}).get('body') or ''
        return resultado.response_text or ''

    # --- o caso da Dênia ------------------------------------------------

    def test_texto_de_volta_do_mercado_pago_nao_vira_observacao(self):
        pedido = self._pedido(StoreOrder.PaymentStatus.PAID)
        texto = self._nota(f'Olá! Gostaria de confirmar meu pedido #{pedido.id}.')

        assert 'Anotado' not in texto, texto
        assert 'Como prefere pagar' not in texto, texto

    def test_pedido_pago_recebe_confirmacao_com_o_numero_do_pedido(self):
        pedido = self._pedido(StoreOrder.PaymentStatus.PAID)

        texto = self._nota('Já foi pago')

        assert 'confirmado' in texto.lower(), texto
        assert pedido.order_number in texto, texto

    def test_pedido_pendente_nao_ganha_um_segundo_link_de_cobranca(self):
        # Foi o que aconteceu: "Foi pago com cartão" → outro link do Mercado
        # Pago. Demorar para confirmar é ruim; cobrar duas vezes é pior.
        pedido = self._pedido(StoreOrder.PaymentStatus.PENDING)

        texto = self._nota('Foi pago com cartão')

        assert pedido.order_number in texto, texto
        assert 'mercadopago' not in texto.lower(), texto
        assert 'Como prefere pagar' not in texto, texto
        assert 'não precisa pagar de novo' in texto, texto

    def test_sem_pedido_nenhum_o_bot_nao_inventa(self):
        texto = self._nota('já paguei')

        assert 'Anotado' not in texto, texto
        assert 'comprovante' in texto.lower(), texto

    # --- o que NÃO pode regredir ---------------------------------------

    def test_observacao_de_verdade_continua_virando_nota(self):
        self._pedido(StoreOrder.PaymentStatus.PENDING)
        texto = self._nota('sem cebola')
        assert 'Anotado' in texto, texto

    def test_pedido_de_produto_continua_nao_virando_nota(self):
        self._pedido(StoreOrder.PaymentStatus.PENDING)
        texto = self._nota('Quero almôndega')
        assert 'Anotado' not in texto, texto
