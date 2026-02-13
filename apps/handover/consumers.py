"""
WebSocket Consumer para Handover Protocol

Adicionar ao arquivo de consumers do app conversations ou criar um novo.
"""

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async


class HandoverConsumer(AsyncWebsocketConsumer):
    """
    Consumer para notificações de handover em tempo real.
    """
    
    async def connect(self):
        """Conecta o cliente aos grupos necessários."""
        self.user = self.scope["user"]
        
        # Verificar autenticação
        if not self.user or self.user.is_anonymous:
            await self.close()
            return
        
        # Grupo para o usuário (recebe atualizações de conversas atribuídas)
        self.user_group = f"user_{self.user.id}"
        await self.channel_layer.group_add(
            self.user_group,
            self.channel_name
        )
        
        # Grupo para operadores da loja (se usuário é operador)
        store_ids = await self.get_user_store_ids()
        self.store_groups = []
        for store_id in store_ids:
            group_name = f"store_{store_id}_operators"
            self.store_groups.append(group_name)
            await self.channel_layer.group_add(
                group_name,
                self.channel_name
            )
        
        await self.accept()
        
        # Enviar confirmação de conexão
        await self.send(text_data=json.dumps({
            'type': 'connected',
            'message': 'Conectado ao handover realtime'
        }))
    
    async def disconnect(self, close_code):
        """Remove o cliente dos grupos."""
        if hasattr(self, 'user_group'):
            await self.channel_layer.group_discard(
                self.user_group,
                self.channel_name
            )
        
        for group in getattr(self, 'store_groups', []):
            await self.channel_layer.group_discard(
                group,
                self.channel_name
            )
    
    async def receive(self, text_data):
        """Processa mensagens recebidas do cliente."""
        data = json.loads(text_data)
        message_type = data.get('type')
        
        if message_type == 'subscribe_conversation':
            # Cliente quer receber updates de uma conversa específica
            conversation_id = data.get('conversation_id')
            if conversation_id:
                await self.channel_layer.group_add(
                    f"conversation_{conversation_id}",
                    self.channel_name
                )
                await self.send(text_data=json.dumps({
                    'type': 'subscribed',
                    'conversation_id': conversation_id
                }))
        
        elif message_type == 'unsubscribe_conversation':
            conversation_id = data.get('conversation_id')
            if conversation_id:
                await self.channel_layer.group_discard(
                    f"conversation_{conversation_id}",
                    self.channel_name
                )
    
    async def handover_updated(self, event):
        """Envia atualização de handover para o cliente."""
        await self.send(text_data=json.dumps({
            'type': 'handover.updated',
            'conversation_id': event['conversation_id'],
            'handover_status': event['handover_status'],
            'assigned_to': event.get('assigned_to'),
            'assigned_to_name': event.get('assigned_to_name'),
            'timestamp': event.get('timestamp'),
        }))
    
    async def handover_requested(self, event):
        """Notifica nova solicitação de handover."""
        await self.send(text_data=json.dumps({
            'type': 'handover.requested',
            'request_id': event['request_id'],
            'conversation_id': event['conversation_id'],
            'requested_by': event.get('requested_by'),
            'reason': event.get('reason'),
            'priority': event.get('priority'),
        }))
    
    @database_sync_to_async
    def get_user_store_ids(self):
        """Retorna IDs das lojas que o usuário é membro."""
        # Ajustar conforme seu modelo de Store
        try:
            from apps.stores.models import Store
            return list(Store.objects.filter(
                members=self.user
            ).values_list('id', flat=True))
        except:
            return []


# Função para enviar notificações de handover
def send_handover_notification(conversation_id, handover_status, assigned_to=None):
    """
    Envia notificação de handover via WebSocket.
    
    Uso:
        send_handover_notification(
            conversation_id='uuid',
            handover_status='human',
            assigned_to=user_instance
        )
    """
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    
    channel_layer = get_channel_layer()
    
    message = {
        'type': 'handover_updated',
        'conversation_id': str(conversation_id),
        'handover_status': handover_status,
        'assigned_to': str(assigned_to.id) if assigned_to else None,
        'assigned_to_name': assigned_to.get_full_name() if assigned_to else None,
    }
    
    # Enviar para o grupo da conversa
    async_to_sync(channel_layer.group_send)(
        f"conversation_{conversation_id}",
        message
    )
