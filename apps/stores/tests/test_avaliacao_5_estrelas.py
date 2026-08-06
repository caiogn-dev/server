"""5★ no WhatsApp tem que devolver o link de avaliação do Google.

06/ago: três clientes (Leani, Margô, Marilene) clicaram em ⭐⭐⭐⭐⭐ e NENHUM
recebeu resposta. Dois bloqueios em série:

1. as três conversas estavam em `mode='human'`, e `_should_suppress_for_human_mode`
   só liberava ids transacionais — `rating_*` caía no silêncio total, sem nem
   registrar a nota;
2. a guarda de identidade comparava telefone normalizado, e o `wa_id` do
   WhatsApp vem sem o nono dígito enquanto o pedido do site grava com ele. Dois
   dos três pedidos não casavam: o cliente ouviria "Não encontrei esse pedido
   para avaliar" sobre o próprio pedido.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreOrder, StoreReview
from apps.whatsapp.models import WhatsAppAccount
from apps.whatsapp.services.webhook_service import WebhookService

User = get_user_model()

CONV_SEM_NOVE = '556392618115'    # como o WhatsApp entrega
PEDIDO_COM_NOVE = '63992618115'   # como o site grava


class ModoHumanoNaoBloqueiaFluxoDoBotTests(TestCase):
    """O clique é continuação de um fluxo que o próprio bot iniciou."""

    def setUp(self):
        self.service = WebhookService()
        self.account = WhatsAppAccount.objects.create(
            name='Conta Rating', phone_number_id='777', waba_id='666',
            access_token='t', phone_number='5563000000002',
        )
        self.conversa = Conversation.objects.create(
            account=self.account, phone_number=CONV_SEM_NOVE,
            contact_name='Leani', mode=Conversation.ConversationMode.HUMAN,
        )

    def _suprime(self, reply_id):
        class _Msg:
            pass
        msg = _Msg()
        msg.conversation = self.conversa
        msg.id = 'x'
        return self.service._should_suppress_for_human_mode(
            msg, {'id': reply_id}, None,
        )

    def test_rating_passa_mesmo_em_modo_humano(self):
        self.assertFalse(self._suprime('rating_5_abc'))

    def test_review_done_e_indicacao_tambem_passam(self):
        self.assertFalse(self._suprime('review_done_abc'))
        self.assertFalse(self._suprime('refer_friend_abc'))

    def test_conversa_solta_continua_suprimida(self):
        """Modo humano ainda cala o bot no papo geral — só o fluxo dele passa."""
        self.assertTrue(self._suprime('show_options'))


class LinkDoGoogleEm5EstrelasTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='dono-rating', password='x', email='dono-rating@real.com',
        )
        self.store = Store.objects.create(
            name='Loja Rating', slug='loja-rating', owner=self.owner, status='active',
            metadata={'google_review_url': 'https://g.page/r/TESTE/review'},
        )
        self.account = WhatsAppAccount.objects.create(
            name='Conta Rating2', phone_number_id='555', waba_id='444',
            access_token='t', phone_number='5563000000003',
        )
        self.conversa = Conversation.objects.create(
            account=self.account, phone_number=CONV_SEM_NOVE, contact_name='Leani',
        )
        self.pedido = StoreOrder.objects.create(
            store=self.store, customer_name='Leani',
            customer_phone=PEDIDO_COM_NOVE, customer_email='leani-r@real.com',
            subtotal=Decimal('36.99'), total=Decimal('36.99'),
            status=StoreOrder.OrderStatus.DELIVERED,
            payment_status=StoreOrder.PaymentStatus.PAID,
        )

    def _responder(self):
        from apps.whatsapp.intents.handlers.interactive import InteractiveReplyHandler
        h = InteractiveReplyHandler(self.account, self.conversa, None)
        return h._handle_feedback_rating(f'rating_5_{self.pedido.id}')

    def test_cliente_com_nono_digito_diferente_recebe_o_link(self):
        resultado = self._responder()
        corpo = ' '.join([
            resultado.response_text or '',
            str(resultado.interactive_data or {}),
        ])
        self.assertIn(
            'g.page/r/TESTE/review', corpo,
            'link do Google não foi enviado — guarda de telefone rejeitou o dono do pedido',
        )

    def test_nota_fica_registrada(self):
        self._responder()
        review = StoreReview.objects.filter(order=self.pedido).first()
        self.assertIsNotNone(review, 'a nota 5★ não foi gravada')
        self.assertEqual(review.rating, 5)
