"""Regressão de segurança: IDOR no subscribe_conversation do WhatsAppConsumer.

A conexão já valida acesso à conta, mas subscribe_conversation juntava o
cliente ao grupo de QUALQUER conversa pelo UUID — inclusive de outra conta/
tenant. Agora só assina conversas da conta conectada.
"""
import asyncio

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from django.urls import re_path
from asgiref.sync import sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator

from apps.conversations.models import Conversation
from apps.whatsapp.models import WhatsAppAccount
from apps.whatsapp.consumers import WhatsAppConsumer

User = get_user_model()


def _auth_app(user):
    router = URLRouter([
        re_path(r'ws/whatsapp/(?P<account_id>[^/]+)/$', WhatsAppConsumer.as_asgi()),
    ])

    class _Inject:
        async def __call__(self, scope, receive, send):
            scope['user'] = user
            return await router(scope, receive, send)

    return _Inject()


@override_settings(CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}})
class WhatsAppConsumerSubscribeIDORTest(TransactionTestCase):

    async def _setup(self):
        self.owner = await sync_to_async(User.objects.create_user)(
            username='wsc-owner', email='wsco@t.com', password='x')
        self.account_a = await sync_to_async(WhatsAppAccount.objects.create)(
            name='A', phone_number_id='pn-A', waba_id='wa-A',
            phone_number='+5511666661', display_phone_number='+5511666661',
            access_token_encrypted='x', webhook_verify_token='x', owner=self.owner)
        self.account_b = await sync_to_async(WhatsAppAccount.objects.create)(
            name='B', phone_number_id='pn-B', waba_id='wa-B',
            phone_number='+5511666662', display_phone_number='+5511666662',
            access_token_encrypted='x', webhook_verify_token='x', owner=self.owner)
        self.conv_a = await sync_to_async(Conversation.objects.create)(
            account=self.account_a, phone_number='+5511999990003', contact_name='A',
            wa_id='wa-ca', profile_picture_url='', agent_session_id='')
        self.conv_b = await sync_to_async(Conversation.objects.create)(
            account=self.account_b, phone_number='+5511999990004', contact_name='B',
            wa_id='wa-cb', profile_picture_url='', agent_session_id='')

    async def _connect(self, account_id):
        comm = WebsocketCommunicator(_auth_app(self.owner), f'ws/whatsapp/{account_id}/')
        connected, _ = await comm.connect()
        self.assertTrue(connected)
        await comm.receive_json_from(timeout=5)  # connection_established
        return comm

    def test_cannot_subscribe_to_conversation_of_other_account(self):
        async def run():
            await self._setup()
            comm = await self._connect(str(self.account_a.id))
            await comm.send_json_to({
                'type': 'subscribe_conversation',
                'conversation_id': str(self.conv_b.id),  # conta B, conexão é A
            })
            resp = await comm.receive_json_from(timeout=5)
            self.assertEqual(resp.get('type'), 'error', resp)
            await comm.disconnect()
        asyncio.run(run())

    def test_can_subscribe_to_conversation_of_connected_account(self):
        async def run():
            await self._setup()
            comm = await self._connect(str(self.account_a.id))
            await comm.send_json_to({
                'type': 'subscribe_conversation',
                'conversation_id': str(self.conv_a.id),
            })
            resp = await comm.receive_json_from(timeout=5)
            self.assertEqual(resp.get('type'), 'subscribed', resp)
            await comm.disconnect()
        asyncio.run(run())
