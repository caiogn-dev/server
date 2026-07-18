"""Regressão: WS de pedidos do painel nunca conectava (403 no handshake).

O client do dash (src/services/websocket.ts) usa first-message auth
({"type":"auth","token":...} após o open) — padrão da plataforma
(FirstMessageAuthMixin, usado pelo WhatsApp) que mantém o token fora de URL/logs.
Mas o OrderConsumer só aceitava ?token= na query e fechava 4001 no handshake,
então o tempo real do painel de pedidos NUNCA funcionou (visível 18/jul após o
toast de queda de conexão ser adicionado).

Também cobre o gate de tenant que faltava: qualquer usuário autenticado podia
assinar os pedidos de QUALQUER loja (IDOR de leitura).
"""
import asyncio

from django.test import TransactionTestCase, override_settings
from django.contrib.auth import get_user_model
from django.urls import re_path
from rest_framework.authtoken.models import Token
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from channels.layers import get_channel_layer
from asgiref.sync import sync_to_async

from apps.stores.models import Store
from apps.stores.consumers import StoreOrdersConsumer
from apps.stores.services.realtime_service import store_orders_group

User = get_user_model()

application = URLRouter([
    re_path(r'ws/stores/(?P<store_slug>[\w-]+)/orders/$', StoreOrdersConsumer.as_asgi()),
])

IN_MEMORY_LAYER = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYER)
class FirstMessageAuthWSTest(TransactionTestCase):
    async def _fixtures(self):
        owner = await sync_to_async(User.objects.create_user)(
            username='dono-ws', email='dono-ws@example.com', password='x')
        token = await sync_to_async(Token.objects.create)(user=owner)
        store = await sync_to_async(Store.objects.create)(
            name='Loja WS', slug='loja-ws', owner=owner)
        return owner, token, store

    async def test_first_message_auth_conecta_e_recebe_broadcast(self):
        _, token, store = await self._fixtures()
        comm = WebsocketCommunicator(application, f'/ws/stores/{store.slug}/orders/')
        connected, _ = await comm.connect()
        assert connected, 'handshake deve aceitar sem token na URL'
        await comm.send_json_to({'type': 'auth', 'token': token.key})
        ack = await comm.receive_json_from(timeout=3)
        assert ack['type'] == 'connection_established', ack
        layer = get_channel_layer()
        await layer.group_send(store_orders_group(store.slug), {
            'type': 'order.created', 'order_id': 'abc', 'status': 'pending', 'total': '10.00',
        })
        msg = await comm.receive_json_from(timeout=3)
        assert msg['type'] == 'order.created', msg
        await comm.disconnect()

    async def test_query_token_legado_continua_funcionando(self):
        _, token, store = await self._fixtures()
        comm = WebsocketCommunicator(
            application, f'/ws/stores/{store.slug}/orders/?token={token.key}')
        connected, _ = await comm.connect()
        assert connected
        ack = await comm.receive_json_from(timeout=3)
        assert ack['type'] == 'connection_established', ack
        layer = get_channel_layer()
        await layer.group_send(store_orders_group(store.slug), {
            'type': 'order.updated', 'order_id': 'abc', 'status': 'paid',
        })
        msg = await comm.receive_json_from(timeout=3)
        assert msg['type'] == 'order.updated', msg
        await comm.disconnect()

    async def test_token_invalido_na_primeira_mensagem_fecha_4001(self):
        _, _, store = await self._fixtures()
        comm = WebsocketCommunicator(application, f'/ws/stores/{store.slug}/orders/')
        connected, _ = await comm.connect()
        assert connected
        await comm.send_json_to({'type': 'auth', 'token': 'token-invalido'})
        out = await comm.receive_output(timeout=3)
        assert out['type'] == 'websocket.close', out
        assert out.get('code') == 4001, out

    async def test_usuario_sem_acesso_a_loja_fecha_4003(self):
        _, _, store = await self._fixtures()
        intruso = await sync_to_async(User.objects.create_user)(
            username='intruso-ws', email='intruso-ws@example.com', password='x')
        token = await sync_to_async(Token.objects.create)(user=intruso)
        comm = WebsocketCommunicator(application, f'/ws/stores/{store.slug}/orders/')
        connected, _ = await comm.connect()
        assert connected
        await comm.send_json_to({'type': 'auth', 'token': token.key})
        out = await comm.receive_output(timeout=3)
        assert out['type'] == 'websocket.close', out
        assert out.get('code') == 4003, out


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYER)
class RealtimeClientContractTest(TransactionTestCase):
    """Contrato do RealtimeConnection do painel: ACK connection_established +
    aceitar UUID da loja no lugar do slug (client global manda store.id)."""

    async def _fixtures(self):
        owner = await sync_to_async(User.objects.create_user)(
            username='dono-rc', email='dono-rc@example.com', password='x')
        token = await sync_to_async(Token.objects.create)(user=owner)
        store = await sync_to_async(Store.objects.create)(
            name='Loja RC', slug='loja-rc', owner=owner)
        return owner, token, store

    async def test_ack_connection_established_apos_auth(self):
        _, token, store = await self._fixtures()
        comm = WebsocketCommunicator(application, f'/ws/stores/{store.slug}/orders/')
        await comm.connect()
        await comm.send_json_to({'type': 'auth', 'token': token.key})
        msg = await comm.receive_json_from(timeout=3)
        assert msg['type'] == 'connection_established', msg
        await comm.disconnect()

    async def test_uuid_da_loja_resolve_e_recebe_broadcast_do_grupo_por_slug(self):
        _, token, store = await self._fixtures()
        comm = WebsocketCommunicator(application, f'/ws/stores/{store.id}/orders/')
        connected, _ = await comm.connect()
        assert connected
        await comm.send_json_to({'type': 'auth', 'token': token.key})
        msg = await comm.receive_json_from(timeout=3)
        assert msg['type'] == 'connection_established', msg
        layer = get_channel_layer()
        # broadcaster de produção usa SEMPRE o grupo por slug
        await layer.group_send(store_orders_group(store.slug), {
            'type': 'order.created', 'order_id': 'xyz', 'status': 'pending', 'total': '5.00',
        })
        msg = await comm.receive_json_from(timeout=3)
        assert msg['type'] == 'order.created', msg
        await comm.disconnect()
