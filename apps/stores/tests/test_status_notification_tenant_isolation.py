"""Notificação de status NÃO pode sair pelo número de outra loja.

Incidente 14/jul: o fallback de notificação de status usava a conta WhatsApp
default global (env DEFAULT_WHATSAPP_ACCOUNT_* — o número da Cê Saladas)
quando a loja do pedido não tinha conta vinculada. Mensagem da loja X saindo
pelo número da loja Y é vazamento cross-tenant.

Contrato: pedido COM loja usa somente a conta da própria loja; sem conta
vinculada → não envia (log), nunca o default global. Default global fica
reservado a pedidos sem loja (legado).
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store, StoreOrder
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()


class StatusNotificationTenantIsolationTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='dono2', email='dono2@loja.com', password='x'
        )
        self.store = Store.objects.create(
            name='Loja Sem Conta', slug='loja-sem-conta', owner=self.owner,
        )
        self.other_account = WhatsAppAccount.objects.create(
            name='Outra Loja', phone_number_id='OTHER1', waba_id='WOTHER',
        )

    def _order(self, store):
        return StoreOrder.objects.create(
            store=store,
            customer_name='Cliente',
            customer_phone='5563999990000',
            customer_email='c@c.com',
            subtotal=10, total=10,
        )

    def test_store_without_account_never_uses_global_default(self):
        order = self._order(self.store)
        with mock.patch(
            'apps.stores.models.order.get_default_whatsapp_account',
            return_value=self.other_account,
        ) as get_default, mock.patch(
            'apps.whatsapp.services.MessageService'
        ) as svc:
            order._trigger_status_whatsapp_notification(StoreOrder.OrderStatus.OUT_FOR_DELIVERY)

        get_default.assert_not_called()
        svc.return_value.send_text_message.assert_not_called()

    def test_store_with_linked_account_sends_via_own_number(self):
        own_account = WhatsAppAccount.objects.create(
            name='Loja Própria', phone_number_id='OWN1', waba_id='WOWN',
        )
        self.store.whatsapp_account = own_account
        self.store.save(update_fields=['whatsapp_account'])
        order = self._order(self.store)

        with mock.patch('apps.whatsapp.services.MessageService') as svc:
            order._trigger_status_whatsapp_notification(StoreOrder.OrderStatus.OUT_FOR_DELIVERY)

        svc.return_value.send_text_message.assert_called_once()
        kwargs = svc.return_value.send_text_message.call_args.kwargs
        self.assertEqual(kwargs.get('account_id'), str(own_account.id))
