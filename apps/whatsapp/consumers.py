"""
WhatsApp WebSocket consumers for real-time message updates.
"""
import logging
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from apps.core.base_consumer import FirstMessageAuthMixin, ThrottledWebSocketConsumer

logger = logging.getLogger(__name__)
User = get_user_model()


class WhatsAppConsumer(FirstMessageAuthMixin, ThrottledWebSocketConsumer):
    """
    WebSocket consumer for WhatsApp real-time updates.

    Clients connect to: ws/whatsapp/{account_id}/

    Events sent to clients:
    - whatsapp_message_received: New inbound message
    - whatsapp_message_sent: Outbound message confirmation
    - whatsapp_status_updated: Message status change (sent, delivered, read)
    - whatsapp_typing: Typing indicator
    """

    async def _setup_params(self):
        self.account_id = self.scope['url_route']['kwargs'].get('account_id')
        self.account_group = None
        self.conversation_groups = set()

    async def _post_auth_connect(self):
        has_access = await self.verify_account_access(self.account_id)
        if not has_access:
            logger.warning("WhatsApp WS: User %s denied access to account %s", self.user.id, self.account_id)
            await self.close(code=4003)
            return

        self.account_group = f"whatsapp_{self.account_id}"
        await self.channel_layer.group_add(self.account_group, self.channel_name)
        await self.channel_layer.group_add(f"user_{self.user.id}_whatsapp", self.channel_name)

        logger.info("WhatsApp WS: User %s connected to account %s", self.user.id, self.account_id)
        await self.send_json({
            'type': 'connection_established',
            'account_id': self.account_id,
            'message': 'Connected to WhatsApp real-time service',
        })

    async def disconnect(self, close_code):
        if self.account_group:
            await self.channel_layer.group_discard(self.account_group, self.channel_name)
        if self.user:
            await self.channel_layer.group_discard(f"user_{self.user.id}_whatsapp", self.channel_name)
        for group in self.conversation_groups:
            await self.channel_layer.group_discard(group, self.channel_name)
        logger.info("WhatsApp WS: Disconnected from account %s", self.account_id)

    async def handle_message(self, content):
        message_type = content.get('type')

        if message_type == 'ping':
            await self.send_json({'type': 'pong'})

        elif message_type == 'subscribe_conversation':
            conversation_id = content.get('conversation_id')
            if conversation_id:
                group_name = f"whatsapp_conv_{conversation_id}"
                await self.channel_layer.group_add(group_name, self.channel_name)
                self.conversation_groups.add(group_name)
                await self.send_json({'type': 'subscribed', 'conversation_id': conversation_id})

        elif message_type == 'unsubscribe_conversation':
            conversation_id = content.get('conversation_id')
            if conversation_id:
                group_name = f"whatsapp_conv_{conversation_id}"
                await self.channel_layer.group_discard(group_name, self.channel_name)
                self.conversation_groups.discard(group_name)
                await self.send_json({'type': 'unsubscribed', 'conversation_id': conversation_id})

        elif message_type == 'typing':
            conversation_id = content.get('conversation_id')
            is_typing = content.get('is_typing', False)
            if conversation_id:
                await self.channel_layer.group_send(
                    f"whatsapp_conv_{conversation_id}",
                    {
                        'type': 'whatsapp_typing',
                        'user_id': self.user.id,
                        'conversation_id': conversation_id,
                        'is_typing': is_typing,
                    }
                )

        elif message_type == 'mark_read':
            message_ids = content.get('message_ids', [])
            if message_ids:
                await self.send_json({'type': 'read_receipt_sent', 'message_ids': message_ids})

    # ==================== Event Handlers ====================

    async def whatsapp_message_received(self, event):
        await self.send_json({
            'type': 'message_received',
            'message': event['message'],
            'conversation_id': event.get('conversation_id'),
            'contact': event.get('contact'),
        })

    async def whatsapp_message_sent(self, event):
        await self.send_json({
            'type': 'message_sent',
            'message': event['message'],
            'conversation_id': event.get('conversation_id'),
        })

    async def whatsapp_status_updated(self, event):
        await self.send_json({
            'type': 'status_updated',
            'message_id': event['message_id'],
            'whatsapp_message_id': event.get('whatsapp_message_id'),
            'status': event['status'],
            'timestamp': event.get('timestamp'),
        })

    async def whatsapp_typing(self, event):
        if event.get('user_id') != self.user.id:
            await self.send_json({
                'type': 'typing',
                'conversation_id': event['conversation_id'],
                'is_typing': event['is_typing'],
            })

    async def whatsapp_conversation_updated(self, event):
        await self.send_json({
            'type': 'conversation_updated',
            'conversation': event['conversation'],
        })

    async def whatsapp_error(self, event):
        await self.send_json({
            'type': 'error',
            'error_code': event.get('error_code'),
            'error_message': event.get('error_message'),
            'message_id': event.get('message_id'),
        })

    @database_sync_to_async
    def verify_account_access(self, account_id: str) -> bool:
        from .models import WhatsAppAccount
        try:
            account = WhatsAppAccount.objects.get(id=account_id)
            return account.owner_id == self.user.id or self.user.is_staff or self.user.is_superuser
        except WhatsAppAccount.DoesNotExist:
            return False


class WhatsAppDashboardConsumer(FirstMessageAuthMixin, ThrottledWebSocketConsumer):
    """
    WebSocket consumer for WhatsApp dashboard overview.

    Provides aggregated updates across all accounts the user has access to.
    Clients connect to: ws/whatsapp/dashboard/
    """

    async def _setup_params(self):
        self.account_groups = set()

    async def _post_auth_connect(self):
        try:
            account_ids = await self.get_user_account_ids()
            for account_id in account_ids:
                group_name = f"whatsapp_{account_id}"
                await self.channel_layer.group_add(group_name, self.channel_name)
                self.account_groups.add(group_name)
            await self.channel_layer.group_add(f"user_{self.user.id}_whatsapp", self.channel_name)
            await self.send_json({
                'type': 'connection_established',
                'accounts': account_ids,
                'message': 'Connected to WhatsApp dashboard service',
            })
        except Exception as e:
            logger.error("WhatsApp Dashboard WS connect error: %s", e)
            await self.close(code=4000)

    async def disconnect(self, close_code):
        for group in self.account_groups:
            await self.channel_layer.group_discard(group, self.channel_name)
        if self.user:
            await self.channel_layer.group_discard(f"user_{self.user.id}_whatsapp", self.channel_name)

    async def handle_message(self, content):
        message_type = content.get('type')

        if message_type == 'ping':
            await self.send_json({'type': 'pong'})

        elif message_type == 'subscribe_conversation':
            conversation_id = content.get('conversation_id')
            if conversation_id:
                group_name = f"whatsapp_conv_{conversation_id}"
                await self.channel_layer.group_add(group_name, self.channel_name)
                self.account_groups.add(group_name)
                await self.send_json({'type': 'subscribed', 'conversation_id': conversation_id})

        elif message_type == 'unsubscribe_conversation':
            conversation_id = content.get('conversation_id')
            if conversation_id:
                group_name = f"whatsapp_conv_{conversation_id}"
                await self.channel_layer.group_discard(group_name, self.channel_name)
                self.account_groups.discard(group_name)
                await self.send_json({'type': 'unsubscribed', 'conversation_id': conversation_id})

        elif message_type == 'typing':
            conversation_id = content.get('conversation_id')
            is_typing = content.get('is_typing', False)
            if conversation_id:
                await self.channel_layer.group_send(
                    f"whatsapp_conv_{conversation_id}",
                    {
                        'type': 'whatsapp_typing',
                        'user_id': self.user.id,
                        'conversation_id': conversation_id,
                        'is_typing': is_typing,
                    }
                )

    async def whatsapp_message_received(self, event):
        await self.send_json({
            'type': 'message_received',
            'message': event['message'],
            'account_id': event.get('account_id'),
            'conversation_id': event.get('conversation_id'),
        })

    async def whatsapp_status_updated(self, event):
        await self.send_json({
            'type': 'status_updated',
            'message_id': event['message_id'],
            'status': event['status'],
            'account_id': event.get('account_id'),
        })

    async def whatsapp_conversation_updated(self, event):
        await self.send_json({
            'type': 'conversation_updated',
            'conversation': event['conversation'],
            'account_id': event.get('account_id'),
        })

    async def whatsapp_message_sent(self, event):
        await self.send_json({
            'type': 'message_sent',
            'message': event['message'],
            'account_id': event.get('account_id'),
            'conversation_id': event.get('conversation_id'),
        })

    async def whatsapp_typing(self, event):
        if event.get('user_id') != self.user.id:
            await self.send_json({
                'type': 'typing',
                'conversation_id': event['conversation_id'],
                'is_typing': event['is_typing'],
            })

    async def whatsapp_error(self, event):
        await self.send_json({
            'type': 'error',
            'error_code': event.get('error_code'),
            'error_message': event.get('error_message'),
            'message_id': event.get('message_id'),
            'account_id': event.get('account_id'),
        })

    @database_sync_to_async
    def get_user_account_ids(self) -> list:
        from .models import WhatsAppAccount
        if self.user.is_staff:
            return [str(pk) for pk in WhatsAppAccount.objects.values_list('id', flat=True)]
        return [str(pk) for pk in WhatsAppAccount.objects.filter(owner=self.user).values_list('id', flat=True)]
