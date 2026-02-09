import logging
from typing import Optional, Dict, List, Any
from datetime import datetime
from .instagram_api import InstagramAPI, InstagramAPIException
from ..models import InstagramConversation, InstagramMessage

logger = logging.getLogger(__name__)


class InstagramDirectService:
    """Serviço avançado para Instagram Direct (Mensagens)"""
    
    def __init__(self, api: InstagramAPI):
        self.api = api
    
    # ========== Conversas ==========
    
    def list_conversations(self, limit: int = 50, unread_only: bool = False) -> List[Dict]:
        """Lista conversas do Instagram Direct"""
        queryset = InstagramConversation.objects.filter(
            account=self.api.account,
            is_active=True
        )
        
        if unread_only:
            queryset = queryset.filter(unread_count__gt=0)
        
        conversations = queryset.order_by('-last_message_at', '-created_at')[:limit]
        
        return [
            {
                'id': str(conv.id),
                'participant': {
                    'id': conv.participant_id,
                    'username': conv.participant_username,
                    'name': conv.participant_name,
                    'profile_pic': conv.participant_profile_pic
                },
                'unread_count': conv.unread_count,
                'last_message_at': conv.last_message_at.isoformat() if conv.last_message_at else None,
                'created_at': conv.created_at.isoformat()
            }
            for conv in conversations
        ]
    
    def get_conversation(self, conversation_id: str) -> Optional[Dict]:
        """Obtém detalhes de uma conversa"""
        try:
            conv = InstagramConversation.objects.get(
                account=self.api.account,
                id=conversation_id
            )
            
            return {
                'id': str(conv.id),
                'participant': {
                    'id': conv.participant_id,
                    'username': conv.participant_username,
                    'name': conv.participant_name,
                    'profile_pic': conv.participant_profile_pic
                },
                'unread_count': conv.unread_count,
                'last_message_at': conv.last_message_at.isoformat() if conv.last_message_at else None,
                'created_at': conv.created_at.isoformat()
            }
            
        except InstagramConversation.DoesNotExist:
            return None
    
    def get_or_create_conversation(self, participant_id: str, 
                                   participant_username: str = "",
                                   participant_name: str = "",
                                   participant_profile_pic: str = "") -> InstagramConversation:
        """Obtém ou cria uma conversa"""
        conv, created = InstagramConversation.objects.get_or_create(
            account=self.api.account,
            participant_id=participant_id,
            defaults={
                'participant_username': participant_username,
                'participant_name': participant_name,
                'participant_profile_pic': participant_profile_pic
            }
        )
        
        return conv
    
    def archive_conversation(self, conversation_id: str) -> bool:
        """Arquiva uma conversa"""
        try:
            conv = InstagramConversation.objects.get(
                account=self.api.account,
                id=conversation_id
            )
            conv.is_active = False
            conv.save()
            return True
        except InstagramConversation.DoesNotExist:
            return False
    
    def mark_as_read(self, conversation_id: str) -> bool:
        """Marca conversa como lida"""
        try:
            conv = InstagramConversation.objects.get(
                account=self.api.account,
                id=conversation_id
            )
            conv.unread_count = 0
            conv.save()
            
            # Marca mensagens como lidas
            conv.messages.filter(is_from_business=False, is_read=False).update(
                is_read=True, read_at=datetime.now()
            )
            
            return True
        except InstagramConversation.DoesNotExist:
            return False
    
    # ========== Mensagens ==========
    
    def get_messages(self, conversation_id: str, limit: int = 50, before: datetime = None) -> List[Dict]:
        """Obtém mensagens de uma conversa"""
        queryset = InstagramMessage.objects.filter(
            conversation__account=self.api.account,
            conversation__id=conversation_id,
            is_unsent=False
        )
        
        if before:
            queryset = queryset.filter(created_at__lt=before)
        
        messages = queryset.order_by('-created_at')[:limit]
        
        return [
            {
                'id': str(msg.id),
                'type': msg.message_type,
                'content': msg.content,
                'media_url': msg.media_url,
                'is_from_business': msg.is_from_business,
                'is_read': msg.is_read,
                'reaction': msg.reaction_type,
                'reply_to': str(msg.reply_to_message.id) if msg.reply_to_message else None,
                'sent_at': msg.sent_at.isoformat() if msg.sent_at else None,
                'created_at': msg.created_at.isoformat()
            }
            for msg in reversed(messages)  # Ordem cronológica
        ]
    
    def send_message(self, conversation_id: str, message_type: str, 
                     content: str = None, media_url: str = None,
                     reply_to_id: str = None) -> InstagramMessage:
        """Envia uma mensagem"""
        try:
            conv = InstagramConversation.objects.get(
                account=self.api.account,
                id=conversation_id
            )
            
            reply_to = None
            if reply_to_id:
                reply_to = InstagramMessage.objects.get(
                    conversation=conv,
                    id=reply_to_id
                )
            
            message = InstagramMessage.objects.create(
                conversation=conv,
                message_type=message_type,
                content=content or "",
                media_url=media_url,
                reply_to_message=reply_to,
                is_from_business=True,
                is_read=True,
                sent_at=datetime.now()
            )
            
            # Atualiza conversa
            conv.last_message_at = datetime.now()
            conv.save()
            
            # TODO: Integrar com API real do Instagram para envio
            
            return message
            
        except InstagramConversation.DoesNotExist:
            raise InstagramAPIException("Conversa não encontrada")
        except InstagramMessage.DoesNotExist:
            raise InstagramAPIException("Mensagem de resposta não encontrada")
    
    def send_text_message(self, conversation_id: str, text: str, reply_to_id: str = None) -> InstagramMessage:
        """Envia mensagem de texto"""
        return self.send_message(conversation_id, 'TEXT', content=text, reply_to_id=reply_to_id)
    
    def send_image_message(self, conversation_id: str, image_url: str, caption: str = "") -> InstagramMessage:
        """Envia mensagem de imagem"""
        return self.send_message(conversation_id, 'IMAGE', content=caption, media_url=image_url)
    
    def send_video_message(self, conversation_id: str, video_url: str, caption: str = "") -> InstagramMessage:
        """Envia mensagem de vídeo"""
        return self.send_message(conversation_id, 'VIDEO', content=caption, media_url=video_url)
    
    def send_voice_message(self, conversation_id: str, audio_url: str) -> InstagramMessage:
        """Envia mensagem de voz"""
        return self.send_message(conversation_id, 'AUDIO', media_url=audio_url)
    
    def receive_message(self, conversation: InstagramConversation, 
                        instagram_message_id: str,
                        message_type: str,
                        content: str = None,
                        media_url: str = None,
                        sent_at: datetime = None) -> InstagramMessage:
        """Recebe mensagem via webhook"""
        message = InstagramMessage.objects.create(
            conversation=conversation,
            instagram_message_id=instagram_message_id,
            message_type=message_type,
            content=content or "",
            media_url=media_url,
            is_from_business=False,
            is_read=False,
            sent_at=sent_at or datetime.now()
        )
        
        # Atualiza conversa
        conversation.last_message_at = datetime.now()
        conversation.unread_count += 1
        conversation.save()
        
        return message
    
    # ========== Reações ==========
    
    def add_reaction(self, message_id: str, reaction: str) -> bool:
        """Adiciona reação a uma mensagem"""
        try:
            message = InstagramMessage.objects.get(
                conversation__account=self.api.account,
                id=message_id
            )
            message.reaction_type = reaction
            message.save()
            return True
        except InstagramMessage.DoesNotExist:
            return False
    
    def remove_reaction(self, message_id: str) -> bool:
        """Remove reação de uma mensagem"""
        try:
            message = InstagramMessage.objects.get(
                conversation__account=self.api.account,
                id=message_id
            )
            message.reaction_type = None
            message.save()
            return True
        except InstagramMessage.DoesNotExist:
            return False
    
    # ========== Respostas ==========
    
    def reply_to_message(self, conversation_id: str, original_message_id: str, 
                         text: str) -> InstagramMessage:
        """Responde a uma mensagem específica"""
        return self.send_message(
            conversation_id, 
            'TEXT', 
            content=text, 
            reply_to_id=original_message_id
        )
    
    # ========== Unsend/Deleção ==========
    
    def unsend_message(self, message_id: str) -> bool:
        """Remove uma mensagem (unsend)"""
        try:
            message = InstagramMessage.objects.get(
                conversation__account=self.api.account,
                id=message_id,
                is_from_business=True  # Só pode remover mensagens enviadas
            )
            message.is_unsent = True
            message.unsent_at = datetime.now()
            message.save()
            return True
        except InstagramMessage.DoesNotExist:
            return False
    
    def delete_message(self, message_id: str) -> bool:
        """Deleta mensagem permanentemente"""
        try:
            message = InstagramMessage.objects.get(
                conversation__account=self.api.account,
                id=message_id
            )
            message.delete()
            return True
        except InstagramMessage.DoesNotExist:
            return False
    
    # ========== Busca ==========
    
    def search_conversations(self, query: str, limit: int = 20) -> List[Dict]:
        """Busca conversas por nome/username do participante"""
        conversations = InstagramConversation.objects.filter(
            account=self.api.account,
            is_active=True
        ).filter(
            models.Q(participant_username__icontains=query) |
            models.Q(participant_name__icontains=query)
        )[:limit]
        
        return [
            {
                'id': str(conv.id),
                'participant': {
                    'username': conv.participant_username,
                    'name': conv.participant_name
                },
                'unread_count': conv.unread_count
            }
            for conv in conversations
        ]
    
    def search_messages(self, conversation_id: str, query: str, limit: int = 20) -> List[Dict]:
        """Busca mensagens por conteúdo"""
        messages = InstagramMessage.objects.filter(
            conversation__account=self.api.account,
            conversation__id=conversation_id,
            is_unsent=False
        ).filter(
            content__icontains=query
        ).order_by('-created_at')[:limit]
        
        return [
            {
                'id': str(msg.id),
                'content': msg.content,
                'is_from_business': msg.is_from_business,
                'created_at': msg.created_at.isoformat()
            }
            for msg in messages
        ]


# Import para busca
from django.db import models