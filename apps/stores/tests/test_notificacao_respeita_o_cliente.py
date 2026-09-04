"""Quem desligou o aviso no WhatsApp não recebe aviso no WhatsApp.

O interruptor "Notificações por WhatsApp" existe no perfil do cliente desde
sempre e NUNCA foi lido por ninguém — zero ocorrências fora do formulário. O
cliente desligava, a tela mostrava desligado (quando salvava, o que também não
acontecia), e as mensagens continuavam chegando.

Persistir a preferência sem honrá-la só faria o botão mentir de forma mais
convincente. Este é o outro lado: o aviso de status do pedido é o único canal
real de notificação ao cliente neste sistema, e passa a consultar a escolha
dele antes de enviar.

DUAS COISAS QUE NÃO MUDAM:

1. O SILÊNCIO POR PEDIDO continua valendo (`metadata.suppress_notifications`,
   usado na venda de balcão). São decisões diferentes — uma é da loja sobre
   AQUELE pedido, a outra é do cliente sobre TODOS os dele.

2. QUEM NÃO TEM CONTA CONTINUA RECEBENDO. O checkout é guest-first: a maioria
   dos pedidos não tem usuário. Sem preferência gravada, o padrão é avisar —
   ninguém pediu silêncio, e deixar de avisar sobre um pedido pago seria pior
   que a mensagem a mais.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.models import UserProfile
from apps.stores.models import Store, StoreOrder
from apps.whatsapp.tasks.automation_tasks import _notifications_suppressed

User = get_user_model()


class NotificacaoRespeitaOClienteTest(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dona-notif', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-notif', owner=dono,
            store_type='food', status='active',
        )

    def _cliente(self, **preferences):
        user = User.objects.create_user(
            username=f'cliente-{len(preferences)}-{id(preferences)}', password='x',
        )
        UserProfile.objects.update_or_create(
            user=user, defaults={'phone': '5563999900022', 'preferences': preferences},
        )
        return user

    def _pedido(self, customer=None, **extra):
        pedido = StoreOrder.objects.create(
            store=self.store, customer=customer,
            customer_name='Ana', customer_phone='5563999900022',
            subtotal=Decimal('50'), total=Decimal('50'),
            status='confirmed', payment_status='paid', **extra,
        )
        # Recarrega como a task do Celery faz: ela recebe só o id e busca o
        # pedido no banco. Sem isto o `User` em memória devolve um `profile`
        # que o Django cacheou ANTES da preferência ser gravada, e o teste
        # mediria o cache do próprio teste em vez do comportamento real.
        return StoreOrder.objects.get(pk=pedido.pk)

    def _avisou(self, order) -> bool:
        """A peneira REAL, consultada pelos dois caminhos de envio."""
        return not _notifications_suppressed(order)

    # ── a escolha do cliente ────────────────────────────────────────────

    def test_quem_desligou_nao_recebe(self):
        pedido = self._pedido(customer=self._cliente(notifications_whatsapp=False))

        self.assertFalse(self._avisou(pedido))

    def test_quem_deixou_ligado_recebe(self):
        pedido = self._pedido(customer=self._cliente(notifications_whatsapp=True))

        self.assertTrue(self._avisou(pedido))

    def test_sem_preferencia_gravada_recebe(self):
        """O padrão é avisar: ninguém pediu silêncio."""
        pedido = self._pedido(customer=self._cliente())

        self.assertTrue(self._avisou(pedido))

    def test_pedido_sem_conta_recebe(self):
        """Guest-first: a maioria dos pedidos não tem usuário."""
        self.assertTrue(self._avisou(self._pedido()))

    # ── o que já existia continua valendo ───────────────────────────────

    def test_o_silencio_por_pedido_continua_mandando(self):
        """Venda de balcão: a loja cala AQUELE pedido, não o cliente."""
        pedido = self._pedido(
            customer=self._cliente(notifications_whatsapp=True),
            metadata={'suppress_notifications': True},
        )

        self.assertFalse(self._avisou(pedido))
