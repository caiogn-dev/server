"""Regressão de segurança: IDOR cross-tenant no Handover Protocol.

Antes do fix, `HandoverViewSet.get_conversation` fazia
`get_object_or_404(Conversation, pk=pk)` sem nenhum escopo de tenant — qualquer
usuário autenticado podia ler o status e TRANSFERIR (bot/human) o handover de
QUALQUER conversa só sabendo o UUID. A classe `IsStoreMember` existia mas nunca
era usada. Estes testes provam que um usuário sem acesso à conta recebe 404.
"""
import asyncio

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from django.urls import re_path
from rest_framework.test import APITestCase
from asgiref.sync import sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator

from apps.conversations.models import Conversation
from apps.whatsapp.models import WhatsAppAccount
from apps.handover.consumers import HandoverConsumer

User = get_user_model()


def _auth_app(user):
    """ASGI app que injeta um usuário autenticado no scope (como o middleware)."""
    router = URLRouter([re_path(r'ws/handover/$', HandoverConsumer.as_asgi())])

    class _Inject:
        async def __call__(self, scope, receive, send):
            scope['user'] = user
            return await router(scope, receive, send)

    return _Inject()


class HandoverCrossTenantIDORTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', email='o@t.com', password='x')
        self.attacker = User.objects.create_user(username='attacker', email='a@t.com', password='x')

        self.account = WhatsAppAccount.objects.create(
            name='acc-owner', phone_number_id='pn-1', waba_id='wa-1',
            phone_number='+5511000001', display_phone_number='+5511000001',
            access_token_encrypted='x', webhook_verify_token='x',
            owner=self.owner,
        )
        self.conversation = Conversation.objects.create(
            account=self.account, phone_number='+5511999990001', contact_name='Cliente',
            wa_id='wa-c1', profile_picture_url='', agent_session_id='',
        )
        self.base = f'/api/v1/handover/conversations/{self.conversation.id}/handover'

    def test_owner_can_read_status(self):
        self.client.force_authenticate(self.owner)
        resp = self.client.get(f'{self.base}/status/')
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_attacker_cannot_read_status(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.get(f'{self.base}/status/')
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_attacker_cannot_transfer_to_human(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.post(f'{self.base}/human/', {}, format='json')
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_attacker_cannot_transfer_to_bot(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.post(f'{self.base}/bot/', {}, format='json')
        self.assertEqual(resp.status_code, 404, resp.content)


@override_settings(CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}})
class HandoverConsumerSubscribeIDORTest(TransactionTestCase):
    """O subscribe_conversation do WS de handover juntava o cliente ao grupo
    de QUALQUER conversa pelo UUID — vazando updates de handover cross-tenant.
    """

    async def _setup(self):
        self.owner = await sync_to_async(User.objects.create_user)(
            username='ws-h-owner', email='who@t.com', password='x')
        self.attacker = await sync_to_async(User.objects.create_user)(
            username='ws-h-att', email='wha@t.com', password='x')
        self.account = await sync_to_async(WhatsAppAccount.objects.create)(
            name='wsh-acc', phone_number_id='pn-wsh', waba_id='wa-wsh',
            phone_number='+5511555551', display_phone_number='+5511555551',
            access_token_encrypted='x', webhook_verify_token='x', owner=self.owner)
        self.conversation = await sync_to_async(Conversation.objects.create)(
            account=self.account, phone_number='+5511999990002', contact_name='C',
            wa_id='wa-h1', profile_picture_url='', agent_session_id='')

    async def _connect(self, user):
        comm = WebsocketCommunicator(_auth_app(user), 'ws/handover/')
        connected, _ = await comm.connect()
        self.assertTrue(connected)
        await comm.receive_json_from(timeout=5)  # mensagem 'connected'
        return comm

    def test_attacker_cannot_subscribe_to_foreign_conversation(self):
        async def run():
            await self._setup()
            comm = await self._connect(self.attacker)
            await comm.send_json_to({
                'type': 'subscribe_conversation',
                'conversation_id': str(self.conversation.id),
            })
            resp = await comm.receive_json_from(timeout=5)
            self.assertEqual(resp.get('type'), 'error', resp)
            await comm.disconnect()
        asyncio.run(run())

    def test_owner_can_subscribe_to_own_conversation(self):
        async def run():
            await self._setup()
            comm = await self._connect(self.owner)
            await comm.send_json_to({
                'type': 'subscribe_conversation',
                'conversation_id': str(self.conversation.id),
            })
            resp = await comm.receive_json_from(timeout=5)
            self.assertEqual(resp.get('type'), 'subscribed', resp)
            await comm.disconnect()
        asyncio.run(run())
