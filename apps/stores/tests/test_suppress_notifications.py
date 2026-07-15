"""Silenciar notificações automáticas de WhatsApp por pedido.

Caso de uso: pedido de balcão criado no painel — o lojista não quer que o
cliente receba as mensagens automáticas de status. Contrato:

- `metadata['suppress_notifications'] = True` no pedido → a task
  `notify_order_status_change` e a `request_feedback` retornam sem enviar
  nada (nem template AutoMessage, nem fallback do model).
- PATCH /orders/{id}/ aceita `suppress_notifications` (bool) e grava a flag
  em metadata SEM apagar as outras chaves.
- POST /orders/ (criação pelo painel) aceita `suppress_notifications` e o
  pedido já nasce silenciado (a mensagem de "recebido" também é pulada).
"""
from unittest import mock

from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase
from django.test import TestCase

from apps.stores.models import Store, StoreOrder, StoreProduct

User = get_user_model()


def _make_store(n):
    owner = User.objects.create_user(
        username=f'owner-sup-{n}', email=f'owner-sup-{n}@x.com', password='x'
    )
    store = Store.objects.create(
        name=f'Loja Sup {n}', slug=f'loja-sup-{n}', owner=owner, status='active'
    )
    return owner, store


def _make_order(store, **extra):
    return StoreOrder.objects.create(
        store=store,
        customer_name='Cliente Balcão',
        customer_phone='5563999990000',
        customer_email='c@c.com',
        subtotal=10,
        total=10,
        **extra,
    )


class SuppressNotificationTaskTest(TestCase):
    """A task de notificação respeita metadata.suppress_notifications."""

    def setUp(self):
        self.owner, self.store = _make_store('task')
        # CompanyProfile é auto-criado com AutoMessages seed; vincular uma
        # conta WhatsApp para exercitar o caminho real de envio por template.
        from apps.whatsapp.models import WhatsAppAccount
        from apps.automation.models import CompanyProfile
        self.account = WhatsAppAccount.objects.create(
            name='Conta Loja', phone_number_id='SUP1', waba_id='WSUP',
        )
        # o post_save da conta auto-cria um CompanyProfile próprio; remover
        # para poder vincular a conta ao profile da loja (OneToOne)
        CompanyProfile.objects.filter(account=self.account).delete()
        profile = self.store.automation_profile
        profile.account = self.account
        profile.save(update_fields=['account'])

    def test_status_task_skips_when_suppressed(self):
        order = _make_order(self.store, metadata={'suppress_notifications': True})
        from apps.whatsapp.tasks.automation_tasks import notify_order_status_change
        with mock.patch.object(
            StoreOrder, '_trigger_status_whatsapp_notification'
        ) as fallback, mock.patch(
            'apps.whatsapp.services.message_service.MessageService'
        ) as svc:
            notify_order_status_change(str(order.id), 'preparing')
        fallback.assert_not_called()
        svc.return_value.send_text_message.assert_not_called()

    def test_status_task_still_sends_when_not_suppressed(self):
        order = _make_order(self.store)
        from apps.whatsapp.tasks.automation_tasks import notify_order_status_change
        with mock.patch(
            'apps.whatsapp.services.message_service.MessageService'
        ) as svc:
            notify_order_status_change(str(order.id), 'preparing')
        svc.return_value.send_text_message.assert_called_once()
        kwargs = svc.return_value.send_text_message.call_args.kwargs
        self.assertEqual(kwargs.get('to'), order.customer_phone)

    def test_feedback_task_skips_when_suppressed(self):
        order = _make_order(
            self.store,
            status='delivered',
            metadata={'suppress_notifications': True},
        )
        from apps.whatsapp.tasks.automation_tasks import request_feedback
        with mock.patch(
            'apps.whatsapp.services.whatsapp_api_service.WhatsAppAPIService'
        ) as api_svc:
            request_feedback(str(order.id))
        api_svc.assert_not_called()


class SuppressNotificationPatchTest(APITestCase):
    """PATCH do pedido liga/desliga a flag preservando o metadata existente."""

    def setUp(self):
        self.owner, self.store = _make_store('patch')
        token = Token.objects.create(user=self.owner)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        self.order = _make_order(
            self.store, metadata={'manual_payment': {'source': 'dashboard'}}
        )
        self.url = f'/api/v1/stores/{self.store.slug}/orders/{self.order.id}/'

    def test_patch_sets_flag_and_preserves_metadata(self):
        resp = self.client.patch(
            self.url, {'suppress_notifications': True}, format='json'
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.order.refresh_from_db()
        self.assertIs(self.order.metadata.get('suppress_notifications'), True)
        # não pode clobberar o resto do metadata
        self.assertEqual(
            self.order.metadata.get('manual_payment'), {'source': 'dashboard'}
        )
        # resposta expõe a flag pro dash renderizar o toggle
        self.assertIs(
            resp.data['metadata'].get('suppress_notifications'), True
        )

    def test_patch_unsets_flag(self):
        self.order.metadata['suppress_notifications'] = True
        self.order.save(update_fields=['metadata'])
        resp = self.client.patch(
            self.url, {'suppress_notifications': False}, format='json'
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.order.refresh_from_db()
        self.assertIs(self.order.metadata.get('suppress_notifications'), False)

    def test_patch_without_flag_leaves_metadata_untouched(self):
        resp = self.client.patch(
            self.url, {'internal_notes': 'obs'}, format='json'
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.order.refresh_from_db()
        self.assertNotIn('suppress_notifications', self.order.metadata)


class SuppressNotificationCreateTest(APITestCase):
    """Criação pelo painel aceita suppress_notifications."""

    def setUp(self):
        self.owner, self.store = _make_store('create')
        token = Token.objects.create(user=self.owner)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        self.product = StoreProduct.objects.create(
            store=self.store,
            name='Marmita',
            slug='marmita-sup',
            price=10,
            track_stock=False,
            stock_quantity=0,
        )
        self.url = f'/api/v1/stores/{self.store.slug}/orders/'

    def _payload(self, **extra):
        return {
            'customer_name': 'Cliente Balcão',
            'customer_phone': '5563999990000',
            'items': [{'product_id': str(self.product.id), 'quantity': 1}],
            'delivery_method': 'pickup',
            'payment_method': 'cash',
            **extra,
        }

    def test_create_with_suppress_flag(self):
        resp = self.client.post(
            self.url, self._payload(suppress_notifications=True), format='json'
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        order = StoreOrder.objects.get(id=resp.data['id'])
        self.assertIs(order.metadata.get('suppress_notifications'), True)

    def test_create_without_flag_defaults_to_not_suppressed(self):
        resp = self.client.post(self.url, self._payload(), format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        order = StoreOrder.objects.get(id=resp.data['id'])
        self.assertNotIn('suppress_notifications', order.metadata)
