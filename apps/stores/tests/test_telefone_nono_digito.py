"""Mesmo telefone com e sem o nono dígito é a MESMA pessoa.

O `wa_id` do WhatsApp para celular brasileiro vem sem o nono dígito
(`556392618115`), mas o formulário do site, o painel e o PDV gravam com ele
(`5563992618115`). O sistema tratava como duas pessoas:

- o cliente ganhava uma conversa fantasma, sem histórico e sem nome, para onde
  iam as notificações do pedido (06/ago: Leani e Marilene, duplicadas);
- a busca de pedido por telefone no bot nunca casava, e o bot respondia
  "Não encontrei pedidos recentes" um minuto depois de confirmar o pedido
  CE-2608062713.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.conversations.models import Conversation
from apps.core.utils import phone_variants
from apps.stores.models import Store, StoreOrder
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()

COM_NOVE = '5563992618115'
SEM_NOVE = '556392618115'


class PhoneVariantsTests(TestCase):
    def test_formas_do_mesmo_numero_geram_o_mesmo_conjunto(self):
        self.assertEqual(
            set(phone_variants(COM_NOVE)),
            set(phone_variants(SEM_NOVE)),
        )

    def test_conjunto_cobre_as_duas_formas(self):
        variantes = set(phone_variants(SEM_NOVE))
        self.assertIn(COM_NOVE, variantes)
        self.assertIn(SEM_NOVE, variantes)

    def test_numero_de_outra_pessoa_nao_entra(self):
        self.assertNotIn('5563992618116', set(phone_variants(COM_NOVE)))


class ConversaNaoDuplicaTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='dono-nono', password='x', email='dono-nono@real.com',
        )
        self.account = WhatsAppAccount.objects.create(
            name='Conta Nono', phone_number_id='111', waba_id='222',
            access_token='t', phone_number='5563000000000',
        )

    def test_notificacao_reusa_a_conversa_do_whatsapp(self):
        """Conversa nasce pelo webhook (sem o 9); notificação chega com o 9."""
        from apps.whatsapp.services.message_service import MessageService

        original = Conversation.objects.create(
            account=self.account, phone_number=SEM_NOVE, contact_name='Leani',
        )

        obtida = MessageService()._get_or_create_conversation(self.account, COM_NOVE)

        self.assertEqual(obtida.pk, original.pk)
        self.assertEqual(
            Conversation.objects.filter(account=self.account).count(), 1,
            'criou conversa fantasma para a mesma pessoa',
        )

    def test_repositorio_tambem_reusa(self):
        from apps.conversations.repositories.conversation_repository import (
            ConversationRepository,
        )

        original = Conversation.objects.create(
            account=self.account, phone_number=SEM_NOVE, contact_name='Marilene',
        )

        obtida, criada = ConversationRepository().get_or_create(
            account=self.account, phone_number=COM_NOVE,
        )

        self.assertFalse(criada)
        self.assertEqual(obtida.pk, original.pk)


class BuscaPedidoPorTelefoneTests(TestCase):
    def test_pedido_gravado_com_nove_e_achado_pela_conversa_sem_nove(self):
        owner = User.objects.create_user(
            username='dono-busca', password='x', email='dono-busca@real.com',
        )
        store = Store.objects.create(
            name='Loja Busca', slug='loja-busca', owner=owner, status='active',
        )
        pedido = StoreOrder.objects.create(
            store=store, customer_name='Leani',
            customer_phone='63992618115',  # como o site grava
            customer_email='leani@real.com',
            subtotal=Decimal('36.99'), total=Decimal('36.99'),
            status=StoreOrder.OrderStatus.CONFIRMED,
            payment_status=StoreOrder.PaymentStatus.PAID,
        )

        # como a conversa do WhatsApp conhece o número
        achado = StoreOrder.objects.filter(
            store=store, customer_phone__in=phone_variants(SEM_NOVE),
        ).first()

        self.assertIsNotNone(
            achado, 'pedido do site invisível para a busca vinda do WhatsApp',
        )
        self.assertEqual(achado.pk, pedido.pk)
