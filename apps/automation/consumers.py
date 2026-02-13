"""
WebSocket consumers for automation real-time updates.
"""
import json
import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

logger = logging.getLogger(__name__)
User = get_user_model()


class AutomationConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket consumer for automation real-time updates."""
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.user = None
        self.company_groups = set()
        
        # Authenticate from query string
        token = self.scope.get('query_string', b'').decode()
        if token.startswith('token='):
            token = token.split('=')[1]
            self.user = await self.get_user_from_token(token)
        
        if self.user:
            # Join general automation group
            await self.channel_layer.group_add("automation", self.channel_name)
            
            # Join user-specific group
            await self.channel_layer.group_add(f"user_{self.user.id}_automation", self.channel_name)
            
            await self.accept()
            await self.send_json({
                'type': 'connection_established',
                'message': 'Connected to automation service'
            })
        else:
            await self.close()
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        await self.channel_layer.group_discard("automation", self.channel_name)
        if self.user:
            await self.channel_layer.group_discard(f"user_{self.user.id}_automation", self.channel_name)
        for group in self.company_groups:
            await self.channel_layer.group_discard(group, self.channel_name)
    
    async def receive_json(self, content):
        """Handle incoming messages."""
        message_type = content.get('type')
        
        if message_type == 'ping':
            await self.send_json({'type': 'pong'})
        
        elif message_type == 'subscribe_company':
            company_id = content.get('company_id')
            if company_id:
                group_name = f"company_{company_id}_automation"
                await self.channel_layer.group_add(group_name, self.channel_name)
                self.company_groups.add(group_name)
                await self.send_json({
                    'type': 'subscribed',
                    'company_id': company_id
                })
        
        elif message_type == 'unsubscribe_company':
            company_id = content.get('company_id')
            if company_id:
                group_name = f"company_{company_id}_automation"
                await self.channel_layer.group_discard(group_name, self.channel_name)
                self.company_groups.discard(group_name)
                await self.send_json({
                    'type': 'unsubscribed',
                    'company_id': company_id
                })
    
    # Event handlers for different automation events
    
    async def session_created(self, event):
        """Send session created notification."""
        await self.send_json({
            'type': 'session_created',
            'session': event['session']
        })
    
    async def session_updated(self, event):
        """Send session updated notification."""
        await self.send_json({
            'type': 'session_updated',
            'session': event['session']
        })
    
    async def message_sent(self, event):
        """Send auto message sent notification."""
        await self.send_json({
            'type': 'message_sent',
            'message': event['message']
        })
    
    async def webhook_received(self, event):
        """Send webhook received notification."""
        await self.send_json({
            'type': 'webhook_received',
            'webhook': event['webhook']
        })
    
    async def automation_error(self, event):
        """Send automation error notification."""
        await self.send_json({
            'type': 'automation_error',
            'error': event['error']
        })
    
    async def stats_update(self, event):
        """Send stats update notification."""
        await self.send_json({
            'type': 'stats_update',
            'stats': event['stats']
        })
    
    async def scheduled_message_sent(self, event):
        """Send scheduled message sent notification."""
        await self.send_json({
            'type': 'scheduled_message_sent',
            'message': event['message']
        })
    
    async def report_generated(self, event):
        """Send report generated notification."""
        await self.send_json({
            'type': 'report_generated',
            'report': event['report']
        })
    
    @database_sync_to_async
    def get_user_from_token(self, token_key):
        """Get user from auth token."""
        try:
            token = Token.objects.select_related('user').get(key=token_key)
            return token.user
        except Token.DoesNotExist:
            return None


# Utility functions to send WebSocket events
def send_automation_event(event_type: str, data: dict, company_id: str = None):
    """
    Send automation event to WebSocket clients.
    
    Args:
        event_type: Type of event (session_created, session_updated, etc.)
        data: Event data
        company_id: Optional company ID to send to specific company group
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    
    channel_layer = get_channel_layer()
    if not channel_layer:
        logger.warning("Channel layer not available")
        return
    
    # Determine target group
    if company_id:
        group_name = f"company_{company_id}_automation"
    else:
        group_name = "automation"
    
    # Send event
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            'type': event_type,
            **data
        }
    )


def notify_session_created(session_data: dict, company_id: str):
    """Notify about new session creation."""
    send_automation_event('session_created', {'session': session_data}, company_id)


def notify_session_updated(session_data: dict, company_id: str):
    """Notify about session update."""
    send_automation_event('session_updated', {'session': session_data}, company_id)


def notify_message_sent(message_data: dict, company_id: str):
    """Notify about auto message sent."""
    send_automation_event('message_sent', {'message': message_data}, company_id)


def notify_webhook_received(webhook_data: dict, company_id: str):
    """Notify about webhook received."""
    send_automation_event('webhook_received', {'webhook': webhook_data}, company_id)


def notify_automation_error(error_data: dict, company_id: str):
    """Notify about automation error."""
    send_automation_event('automation_error', {'error': error_data}, company_id)


def notify_stats_update(stats_data: dict, company_id: str = None):
    """Notify about stats update."""
    send_automation_event('stats_update', {'stats': stats_data}, company_id)


def notify_scheduled_message_sent(message_data: dict, company_id: str):
    """Notify about scheduled message sent."""
    send_automation_event('scheduled_message_sent', {'message': message_data}, company_id)


def notify_report_generated(report_data: dict, company_id: str = None):
    """Notify about report generated."""
    send_automation_event('report_generated', {'report': report_data}, company_id)
