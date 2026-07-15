"""Flag order_status_notification_enabled (CompanyProfile) deve ser honrada.

Bug 15/jul: o toggle "notificações de status" do painel (CompanyProfileDetail
→ order_status_notification_enabled) era letra morta — a task
notify_order_status_change nunca checava a flag. Contrato:

- flag False → nenhuma mensagem de status sai (nem template, nem fallback)
- flag True  → comportamento normal (envia)
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store, StoreOrder

User = get_user_model()


class OrderNotificationStoreToggleTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner-toggle', email='owner-toggle@x.com', password='x'
        )
        self.store = Store.objects.create(
            name='Loja Toggle', slug='loja-toggle', owner=self.owner, status='active'
        )
        from apps.whatsapp.models import WhatsAppAccount
        from apps.automation.models import CompanyProfile
        self.account = WhatsAppAccount.objects.create(
            name='Conta Toggle', phone_number_id='TGL1', waba_id='WTGL',
        )
        CompanyProfile.objects.filter(account=self.account).delete()
        self.profile = self.store.automation_profile
        self.profile.account = self.account
        self.profile.save(update_fields=['account'])

    def _order(self):
        return StoreOrder.objects.create(
            store=self.store,
            customer_name='Cliente',
            customer_phone='5563999990000',
            customer_email='c@c.com',
            subtotal=10,
            total=10,
        )

    def test_flag_off_skips_status_notification(self):
        self.profile.order_status_notification_enabled = False
        self.profile.save(update_fields=['order_status_notification_enabled'])
        order = self._order()
        from apps.whatsapp.tasks.automation_tasks import notify_order_status_change
        with mock.patch(
            'apps.whatsapp.services.message_service.MessageService'
        ) as svc, mock.patch.object(
            StoreOrder, '_trigger_status_whatsapp_notification'
        ) as fallback:
            notify_order_status_change(str(order.id), 'preparing')
        svc.return_value.send_text_message.assert_not_called()
        fallback.assert_not_called()

    def test_flag_on_sends_status_notification(self):
        self.profile.order_status_notification_enabled = True
        self.profile.save(update_fields=['order_status_notification_enabled'])
        order = self._order()
        from apps.whatsapp.tasks.automation_tasks import notify_order_status_change
        with mock.patch(
            'apps.whatsapp.services.message_service.MessageService'
        ) as svc:
            notify_order_status_change(str(order.id), 'preparing')
        svc.return_value.send_text_message.assert_called_once()
