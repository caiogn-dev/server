"""O convite de avaliação pós-entrega tem que virar mensagem no inbox.

Caso real (07/ago, Cê Saladas, pedido CE-2608071926): a notificação "pedido
entregue" das 12:42 aparece no painel (outbound, status 'read'). O convite de
avaliação disparado 30 min depois logou "Feedback request sent for order ..."
e não deixou rastro nenhum — nem linha na tabela de mensagens, nem nada no
inbox. Do lado do dono, o sistema simplesmente não enviou.

Causa: `request_feedback` chamava `WhatsAppAPIService` direto. Essa camada só
fala HTTP com a Meta — quem cria o registro `Message`, vincula à conversa e
marca falha é o `MessageService`. E o telefone ia cru (`63992618115`), sem o
`normalize_phone_number` que todo o resto do envio aplica.

Contrato travado aqui:
  1. O convite sai pelo MessageService (persistido, aparece no inbox).
  2. O telefone é normalizado para E.164 antes de sair.
  3. Falha no envio não vira log de sucesso.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import AutoMessage, CompanyProfile
from apps.stores.models import Store, StoreOrder
from apps.whatsapp.models import WhatsAppAccount
from apps.whatsapp.tasks.automation_tasks import request_feedback

User = get_user_model()

TELEFONE_CRU = '63992618115'
TELEFONE_E164 = '5563992618115'


class RequestFeedbackPersistenciaTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-fbp', email='fbp@loja.com', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Loja FBP', slug='loja-fbp', owner=self.owner,
        )
        self.account = WhatsAppAccount.objects.create(
            name='ContaFBP', phone_number_id='PHFBP', waba_id='WFBP',
        )
        self.store.whatsapp_account = self.account
        self.store.save(update_fields=['whatsapp_account'])

        self.profile = CompanyProfile.objects.get(store=self.store)
        self.profile.account = self.account
        CompanyProfile.objects.filter(account=self.account).exclude(pk=self.profile.pk).delete()
        self.profile.save()

        # update_or_create: o signal de criação da loja já semeia os templates
        # padrão, e um segundo 'feedback_request' faria o get() da task estourar
        # com MultipleObjectsReturned.
        AutoMessage.objects.update_or_create(
            company=self.profile,
            event_type='feedback_request',
            defaults={
                'message_text': 'Oi {customer_name}, como foi o pedido {order_number}?',
                'is_active': True,
            },
        )

        self.order = StoreOrder.objects.create(
            store=self.store,
            customer_name='Cliente FBP',
            customer_phone=TELEFONE_CRU,
            status=StoreOrder.OrderStatus.DELIVERED,
            subtotal=50, delivery_fee=0, total=50,
        )

    def test_convite_sai_pelo_message_service_e_fica_persistido(self):
        with patch('apps.whatsapp.services.MessageService.send_interactive_buttons') as envio:
            request_feedback(str(self.order.id))

        assert envio.called, 'convite não passou pelo MessageService — não seria gravado no inbox'
        kwargs = envio.call_args.kwargs
        assert kwargs['to'] == TELEFONE_E164, (
            f"telefone saiu como {kwargs['to']!r}; a Meta espera E.164"
        )
        assert len(kwargs['buttons']) == 3, 'os três botões de estrela têm que ir junto'
        assert str(self.order.id) in kwargs['buttons'][0]['id']

    def test_falha_no_envio_nao_derruba_a_task(self):
        """A task é best-effort: erro da Meta vira log, não estouro no worker."""
        with patch(
            'apps.whatsapp.services.MessageService.send_interactive_buttons',
            side_effect=Exception('(#131047) fora da janela de 24h'),
        ):
            request_feedback(str(self.order.id))  # não pode levantar

    def test_pedido_nao_entregue_nao_recebe_convite(self):
        self.order.status = StoreOrder.OrderStatus.PREPARING
        self.order.save(update_fields=['status'])

        with patch('apps.whatsapp.services.MessageService.send_interactive_buttons') as envio:
            request_feedback(str(self.order.id))

        assert not envio.called
