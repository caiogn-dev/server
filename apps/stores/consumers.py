"""WebSocket consumers for store real-time updates."""
import json
import asyncio
import logging
from datetime import datetime
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.core.websocket_auth import validate_websocket_token
from apps.core.websocket_listeners import generate_listener_id
from apps.core.websocket_heartbeat import create_heartbeat_message
from apps.stores.services.realtime_service import store_orders_group

logger = logging.getLogger(__name__)
User = get_user_model()


class OrderConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for store order real-time updates.

    Implements:
    - Auth validation BEFORE accept (rejects 4001 if invalid)
    - Heartbeat ping every 30s (prevents proxy timeout)
    - Listener deduplication (one listener per user+store)
    """

    AUTH_TIMEOUT = 30

    async def connect(self):
        """Aceita a conexão e autentica por query token (legado) OU first-message.

        O client do painel (websocket.ts) manda {"type":"auth","token":...} logo
        após o open — padrão da plataforma (token fora de URL/logs). O ?token=
        na query segue aceito para clients legados.
        """
        self.store_slug = self.scope['url_route']['kwargs'].get('store_slug')
        if not self.store_slug:
            await self.close(code=4000)  # Invalid route
            return

        self._authenticated = False
        self._auth_task = None

        query_params = {}
        if self.scope.get('query_string'):
            query_string = self.scope['query_string'].decode()
            for param in query_string.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    query_params[key] = value

        token_key = query_params.get('token')
        if token_key:
            # Modo legado: valida token E gate de tenant antes do accept —
            # assim não há query de DB entre accept e group_add (evita perder
            # broadcasts disparados logo após o handshake).
            self.user = await self._validate_token(token_key)
            if not self.user:
                await self.close(code=4001)  # Invalid token
                return
            if not await self._user_can_access_store():
                await self.close(code=4003)  # Sem acesso à loja (tenant gate)
                return
            await self.accept()
            await self._join_and_start()
            return

        # First-message auth: aceita e aguarda {"type":"auth"} por AUTH_TIMEOUT s.
        await self.accept()
        self._auth_task = asyncio.create_task(self._auth_timeout())

    async def _auth_timeout(self):
        await asyncio.sleep(self.AUTH_TIMEOUT)
        if not self._authenticated:
            logger.warning('WS orders: auth timeout (4001) store=%s', self.store_slug)
            try:
                await self.close(code=4001)
            except RuntimeError:
                pass

    async def _finish_setup(self):
        """Pós-auth first-message: gate de tenant, join no grupo e heartbeat."""
        # Gate de tenant: token válido NÃO basta — sem isso qualquer usuário
        # autenticado assinava os pedidos de qualquer loja (IDOR de leitura).
        if not await self._user_can_access_store():
            logger.warning(
                'WS orders: acesso negado (4003)',
                extra={'user_id': self.user.id, 'store_slug': self.store_slug},
            )
            await self.close(code=4003)
            return

        await self._join_and_start()

    async def _join_and_start(self):
        """Join no grupo de broadcasts + heartbeat (auth e gate já validados)."""
        self._authenticated = True
        if self._auth_task:
            self._auth_task.cancel()

        # Generate dedup listener ID and join group
        self.listener_id = generate_listener_id(self.user.id, self.store_slug)
        # Mesmo grupo que o broadcaster usa (store_orders_group) — antes era
        # `store_{slug}` e divergia de `store_{slug}_orders`, então os eventos
        # de pedido não chegavam ao painel pelo WebSocket.
        self.group_name = store_orders_group(self.store_slug)
        await self.channel_layer.group_add(self.group_name, self.channel_name)

        # Start heartbeat task
        self.heartbeat_task = asyncio.create_task(self._send_heartbeat())

        # ACK esperado pelo RealtimeConnection do painel: sem ele o client
        # considera o transporte morto e rotaciona (WS→SSE→polling) em loop.
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'store_slug': self.store_slug,
        }))

        logger.info(
            f'WebSocket connected',
            extra={
                'user_id': self.user.id,
                'store_slug': self.store_slug,
                'listener_id': self.listener_id,
            }
        )

    async def disconnect(self, close_code):
        """Handle disconnection - cleanup listeners."""
        # Cancel heartbeat and pending auth timeout
        if hasattr(self, 'heartbeat_task'):
            self.heartbeat_task.cancel()
        if getattr(self, '_auth_task', None):
            self._auth_task.cancel()

        # Leave group (dedup listener gone)
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

        logger.info(
            f'WebSocket disconnected',
            extra={
                'user_id': self.user.id if hasattr(self, 'user') else None,
                'store_slug': self.store_slug if hasattr(self, 'store_slug') else None,
                'close_code': close_code,
            }
        )

    async def receive(self, text_data=None, bytes_data=None):
        """Handle incoming messages from client."""
        if not text_data:
            return

        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if not self._authenticated:
                if message_type == 'auth':
                    user = await self._validate_token(data.get('token') or '')
                    if user:
                        self.user = user
                        await self._finish_setup()
                        return
                await self.close(code=4001)
                return

            if message_type == 'pong':
                # Client responding to heartbeat
                pass
        except json.JSONDecodeError:
            logger.warning('Invalid JSON received')

    async def order_created(self, event):
        """Handle order.created message from group broadcast."""
        await self.send(text_data=json.dumps({
            'type': 'order.created',
            'order_id': event.get('order_id'),
            'status': event.get('status'),
            'total': event.get('total'),
            'timestamp': datetime.now().isoformat(),
        }))

    async def order_updated(self, event):
        """Handle order.updated message from group broadcast."""
        await self.send(text_data=json.dumps({
            'type': 'order.updated',
            'order_id': event.get('order_id'),
            'status': event.get('status'),
            'updated_at': event.get('updated_at', datetime.now().isoformat()),
            'timestamp': datetime.now().isoformat(),
        }))

    async def order_payment_received(self, event):
        """Handle order.payment_received message from group broadcast."""
        await self.send(text_data=json.dumps({
            'type': 'order.payment_received',
            'order_id': event.get('order_id'),
            'amount': event.get('amount'),
            'payment_method': event.get('payment_method'),
            'timestamp': datetime.now().isoformat(),
        }))

    async def ping(self, event):
        """Handle ping message (heartbeat)."""
        await self.send(text_data=json.dumps({
            'type': 'ping',
            'timestamp': event.get('timestamp', datetime.now().isoformat()),
        }))

    async def _send_heartbeat(self):
        """Send heartbeat ping every 30 seconds to keep connection alive."""
        try:
            while True:
                await asyncio.sleep(30)
                heartbeat = create_heartbeat_message()
                await self.send(text_data=json.dumps(heartbeat))
                logger.debug(
                    'Heartbeat sent',
                    extra={
                        'user_id': self.user.id,
                        'store_slug': self.store_slug,
                    }
                )
        except asyncio.CancelledError:
            logger.debug('Heartbeat task cancelled')
            pass

    @database_sync_to_async
    def _validate_token(self, token_key: str):
        """Validate token synchronously (runs in thread pool)."""
        return validate_websocket_token(token_key)

    @database_sync_to_async
    def _user_can_access_store(self):
        """Tenant gate: dono/staff da loja (is_staff NÃO bypassa; só superuser).

        Aceita slug OU UUID na URL (o client global do painel manda store.id).
        Normaliza self.store_slug para o slug real — o broadcaster de produção
        usa SEMPRE o grupo por slug, então o join precisa bater com ele.
        """
        from apps.core.permissions import user_can_access_store
        from apps.stores.models import Store

        store = Store.objects.filter(slug=self.store_slug).first()
        if not store:
            try:
                store = Store.objects.filter(id=self.store_slug).first()
            except (ValueError, ValidationError):
                store = None
        if not store:
            return False
        self.store_slug = store.slug

        if getattr(self.user, 'is_superuser', False):
            return True
        return user_can_access_store(self.user, store)


# Aliases for backward compatibility with routing
StoreOrdersConsumer = OrderConsumer
CustomerOrderConsumer = OrderConsumer
