"""
WebSocket consumers para messaging_v2 - Real-time completo.
"""
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.core.cache import cache


class ConversationConsumer(AsyncWebsocketConsumer):
    """Consumer para conversas em tempo real."""
    
    async def connect(self):
        self.store_slug = self.scope['url_route']['kwargs']['store_slug']
        self.room_group_name = f'conversations_{self.store_slug}'
        self.user = self.scope.get('user')
        
        # Verificar autenticação
        if self.user and self.user.is_authenticated:
            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            await self.accept()
            
            # Enviar confirmação de conexão
            await self.send(text_data=json.dumps({
                'type': 'connection_established',
                'store': self.store_slug,
                'user': self.user.username
            }))
        else:
            await self.close(code=4001)
    
    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        """Receber mensagem do cliente WebSocket."""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'typing':
                # Broadcast typing indicator
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'typing_indicator',
                        'conversation_id': data.get('conversation_id'),
                        'user': self.user.username if self.user else 'unknown'
                    }
                )
            
            elif message_type == 'message_read':
                # Marcar mensagem como lida
                await self.mark_message_read(data.get('message_id'))
                
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON'
            }))
    
    async def conversation_message(self, event):
        """Enviar mensagem para WebSocket."""
        await self.send(text_data=json.dumps({
            'type': 'new_message',
            'message': event['message']
        }))
    
    async def typing_indicator(self, event):
        """Enviar indicador de digitação."""
        await self.send(text_data=json.dumps({
            'type': 'typing',
            'conversation_id': event['conversation_id'],
            'user': event['user']
        }))
    
    async def message_status_update(self, event):
        """Atualização de status de mensagem."""
        await self.send(text_data=json.dumps({
            'type': 'status_update',
            'message_id': event['message_id'],
            'status': event['status']
        }))
    
    @database_sync_to_async
    def mark_message_read(self, message_id):
        """Marcar mensagem como lida no banco."""
        from apps.messaging_v2.models import UnifiedMessage
        try:
            message = UnifiedMessage.objects.get(id=message_id)
            message.status = UnifiedMessage.Status.READ
            message.save(update_fields=['status', 'updated_at'])
            return True
        except UnifiedMessage.DoesNotExist:
            return False


class OrderConsumer(AsyncWebsocketConsumer):
    """Consumer para atualizações de pedidos em tempo real."""
    
    async def connect(self):
        self.store_slug = self.scope['url_route']['kwargs']['store_slug']
        self.room_group_name = f'orders_{self.store_slug}'
        self.user = self.scope.get('user')
        
        if self.user and self.user.is_authenticated:
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            await self.accept()
            
            await self.send(text_data=json.dumps({
                'type': 'connection_established',
                'channel': 'orders',
                'store': self.store_slug
            }))
        else:
            await self.close(code=4001)
    
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def order_update(self, event):
        """Enviar atualização de pedido."""
        await self.send(text_data=json.dumps({
            'type': 'order_update',
            'order': event['order']
        }))
    
    async def new_order(self, event):
        """Novo pedido recebido."""
        await self.send(text_data=json.dumps({
            'type': 'new_order',
            'order': event['order']
        }))


class DashboardConsumer(AsyncWebsocketConsumer):
    """Consumer para métricas do dashboard em tempo real."""
    
    async def connect(self):
        self.store_slug = self.scope['url_route']['kwargs'].get('store_slug')
        self.room_group_name = f'dashboard_{self.store_slug}' if self.store_slug else 'dashboard_global'
        self.user = self.scope.get('user')
        
        if self.user and self.user.is_authenticated:
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            await self.accept()
            
            # Enviar métricas iniciais
            metrics = await self.get_initial_metrics()
            await self.send(text_data=json.dumps({
                'type': 'initial_metrics',
                'data': metrics
            }))
        else:
            await self.close(code=4001)
    
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def metrics_update(self, event):
        """Atualização de métricas."""
        await self.send(text_data=json.dumps({
            'type': 'metrics_update',
            'data': event['data']
        }))
    
    @database_sync_to_async
    def get_initial_metrics(self):
        """Buscar métricas iniciais."""
        from apps.commerce.models import Order
        from apps.messaging_v2.models import Conversation
        
        if self.store_slug:
            from apps.commerce.models import Store
            try:
                store = Store.objects.get(slug=self.store_slug)
                return {
                    'active_conversations': Conversation.objects.filter(
                        store=store, is_open=True
                    ).count(),
                    'pending_orders': Order.objects.filter(
                        store=store, status='pending'
                    ).count(),
                    'today_revenue': 0,  # Calcular do banco
                }
            except Store.DoesNotExist:
                pass
        return {}
