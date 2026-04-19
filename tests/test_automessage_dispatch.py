"""
Testes de regressão: despacho de notificações WhatsApp em mudança de status.

Cobertura:
1. update_status() NÃO chama _trigger_status_whatsapp_notification() diretamente
2. post_save signal enfileira notify_order_status_change via transaction.on_commit
3. notify_order_status_change usa template AutoMessage quando disponível
4. notify_order_status_change usa fallback direto quando não há template configurado

Executar:
    python manage.py test tests.test_automessage_dispatch --keepdb -v 2
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock, call

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.stores.models import Store, StoreOrder
from apps.automation.models import CompanyProfile, AutoMessage

User = get_user_model()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_user(username):
    return User.objects.create_user(
        username=username,
        email=f'{username}@example.com',
        password='testpass',
    )


def _make_store(owner, slug='automsg-test'):
    return Store.objects.create(
        owner=owner,
        name='AutoMsg Test Store',
        slug=slug,
        is_active=True,
        status='active',
        default_delivery_fee=Decimal('5.00'),
    )


def _make_order(store, status='received'):
    return StoreOrder.objects.create(
        store=store,
        order_number=f'TEST-{store.slug[:4].upper()}-001',
        customer_name='Cliente Teste',
        customer_phone='+5563999990002',
        status=status,
        subtotal=Decimal('50.00'),
        total=Decimal('50.00'),
        delivery_method='pickup',
        payment_method='cash',
    )


# ─── Testes: update_status não dispara WhatsApp diretamente ──────────────────

class UpdateStatusNoDirectWhatsAppTest(TestCase):
    """
    Garante que update_status() não chama _trigger_status_whatsapp_notification()
    diretamente — o único caminho é via signal → Celery.

    Regressão: antes do fix, update_status() chamava ambos o método direto E
    o signal, duplicando envios em lojas com AutoMessage configurado.
    """

    def setUp(self):
        owner = _make_user('ust_owner')
        self.store = _make_store(owner, 'ust-store')
        self.order = _make_order(self.store)

    def test_update_status_does_not_call_direct_whatsapp_method(self):
        """Método direto não é chamado durante update_status."""
        with patch.object(
            self.order, '_trigger_status_whatsapp_notification'
        ) as mock_direct, \
             patch('apps.automation.signals.transaction') as mock_txn:
            mock_txn.on_commit = lambda fn: None  # skip actual Celery dispatch
            self.order.update_status('confirmed', notify=True)

        mock_direct.assert_not_called()

    def test_update_status_notify_false_skips_all_notifications(self):
        """notify=False não dispara webhooks, email, nem WhatsApp."""
        with patch.object(self.order, 'send_status_webhook') as mock_wh, \
             patch.object(self.order, '_trigger_status_email_automation') as mock_email, \
             patch.object(self.order, '_trigger_status_whatsapp_notification') as mock_wa:
            self.order.update_status('confirmed', notify=False)

        mock_wh.assert_not_called()
        mock_email.assert_not_called()
        mock_wa.assert_not_called()


# ─── Testes: signal despacha Celery task ─────────────────────────────────────

class SignalDispatchesCeleryTaskTest(TestCase):
    """
    Verifica que o signal post_save de StoreOrder enfileira
    notify_order_status_change via transaction.on_commit.
    """

    def setUp(self):
        owner = _make_user('sig_owner')
        self.store = _make_store(owner, 'sig-store')

    def test_status_change_queues_celery_task(self):
        """Salvar com status diferente enfileira notify_order_status_change."""
        order = _make_order(self.store, status='received')

        with patch(
            'apps.whatsapp.tasks.automation_tasks.notify_order_status_change'
        ) as mock_task:
            order.status = 'confirmed'
            order.save(update_fields=['status'])

        mock_task.delay.assert_called_once_with(str(order.id), 'confirmed')

    def test_non_status_save_does_not_queue_notification(self):
        """Salvar campos que não sejam status não deve disparar notificação."""
        order = _make_order(self.store)

        with patch(
            'apps.whatsapp.tasks.automation_tasks.notify_order_status_change'
        ) as mock_task:
            order.customer_notes = 'Sem cebola'
            order.save(update_fields=['customer_notes'])

        mock_task.delay.assert_not_called()


# ─── Testes: notify_order_status_change task ─────────────────────────────────

_PATCH_WA_SERVICE = 'apps.whatsapp.tasks.automation_tasks.WhatsAppAPIService'
_PATCH_GET_PROFILE = 'apps.whatsapp.tasks.automation_tasks._get_store_profile'
_PATCH_GET_ACCOUNT = 'apps.whatsapp.tasks.automation_tasks._get_account_for_profile'


class NotifyOrderStatusChangeTest(TestCase):
    """
    Testa o fluxo interno da task notify_order_status_change:
    - usa AutoMessage template quando disponível
    - usa fallback direto quando template não existe
    - fallback é _trigger_status_whatsapp_notification (não uma segunda task)
    """

    def setUp(self):
        owner = _make_user('nosc_owner')
        self.store = _make_store(owner, 'nosc-store')
        self.order = _make_order(self.store, status='confirmed')

        # CompanyProfile é necessário para o task funcionar
        self.profile, _ = CompanyProfile.objects.get_or_create(
            store=self.store,
            defaults={'company_name': 'Test Company'},
        )

    def _run_task(self, status='confirmed'):
        from apps.whatsapp.tasks.automation_tasks import notify_order_status_change
        notify_order_status_change(str(self.order.id), status)

    def test_uses_automessage_template_when_exists(self):
        """Quando existe AutoMessage ativo, usa render_message + send_text_message."""
        template = AutoMessage.objects.create(
            company=self.profile,
            event_type='order_confirmed',
            message_template='Olá {customer_name}, pedido {order_number} confirmado!',
            is_active=True,
        )
        mock_account = MagicMock()
        mock_service = MagicMock()

        with patch(_PATCH_GET_PROFILE, return_value=self.profile), \
             patch(_PATCH_GET_ACCOUNT, return_value=mock_account), \
             patch(_PATCH_WA_SERVICE, return_value=mock_service), \
             patch.object(self.order, '_trigger_status_whatsapp_notification') as mock_direct:
            self._run_task('confirmed')

        mock_service.send_text_message.assert_called_once()
        mock_direct.assert_not_called()

    def test_uses_direct_fallback_when_no_template(self):
        """Sem AutoMessage configurado, chama _trigger_status_whatsapp_notification."""
        # Garante que não existe template
        AutoMessage.objects.filter(company=self.profile, event_type='order_confirmed').delete()

        with patch(_PATCH_GET_PROFILE, return_value=self.profile), \
             patch(_PATCH_GET_ACCOUNT, return_value=MagicMock()), \
             patch.object(
                 StoreOrder,
                 '_trigger_status_whatsapp_notification',
             ) as mock_direct:
            self._run_task('confirmed')

        mock_direct.assert_called_once_with('confirmed')

    def test_no_company_profile_skips_silently(self):
        """Sem CompanyProfile, a task retorna sem erro e sem enviar mensagem."""
        with patch(_PATCH_GET_PROFILE, return_value=None), \
             patch(_PATCH_WA_SERVICE) as mock_svc:
            self._run_task('confirmed')

        mock_svc.assert_not_called()

    def test_unmapped_status_skips_silently(self):
        """Status sem mapeamento de evento não gera erro."""
        with patch(_PATCH_GET_PROFILE, return_value=self.profile), \
             patch(_PATCH_WA_SERVICE) as mock_svc:
            self._run_task('unknown_status')

        mock_svc.assert_not_called()
