import logging
from typing import Optional, Dict, List, Any
from .messenger_service import MessengerService, MessengerAPIException
from ..models import MessengerProfile, MessengerConversation, MessengerMessage

logger = logging.getLogger(__name__)


class MessengerPlatformService:
    """Serviço para gerenciamento da plataforma Messenger"""
    
    def __init__(self, messenger: MessengerService):
        self.messenger = messenger
    
    # ========== Profile / Configurações ==========
    
    def get_profile(self) -> Dict:
        """Obtém configurações de perfil do Messenger"""
        try:
            result = self.messenger.get('me/messenger_profile', {
                'fields': 'greeting,get_started,persistent_menu,ice_breakers,whitelisted_domains'
            })
            return result.get('data', [{}])[0] if result.get('data') else {}
        except MessengerAPIException as e:
            logger.error(f"Error getting profile: {e}")
            return {}
    
    def set_greeting(self, text: str, locale: str = "default") -> bool:
        """Define mensagem de saudação"""
        try:
            payload = {
                'greeting': [{
                    'locale': locale,
                    'text': text
                }]
            }
            self.messenger.post('me/messenger_profile', payload)
            
            # Atualiza local
            profile, _ = MessengerProfile.objects.get_or_create(
                account=self.messenger.account
            )
            profile.greeting_text = text
            profile.save()
            
            return True
        except MessengerAPIException as e:
            logger.error(f"Error setting greeting: {e}")
            return False
    
    def set_get_started_button(self, payload: str = "GET_STARTED") -> bool:
        """Define botão de início"""
        try:
            request_payload = {
                'get_started': {'payload': payload}
            }
            self.messenger.post('me/messenger_profile', request_payload)
            
            # Atualiza local
            profile, _ = MessengerProfile.objects.get_or_create(
                account=self.messenger.account
            )
            profile.get_started_payload = payload
            profile.save()
            
            return True
        except MessengerAPIException as e:
            logger.error(f"Error setting get started button: {e}")
            return False
    
    def set_persistent_menu(self, menu_items: List[Dict], 
                            locale: str = "default",
                            composer_input_disabled: bool = False) -> bool:
        """Define menu persistente"""
        try:
            payload = {
                'persistent_menu': [{
                    'locale': locale,
                    'composer_input_disabled': composer_input_disabled,
                    'call_to_actions': menu_items
                }]
            }
            self.messenger.post('me/messenger_profile', payload)
            
            # Atualiza local
            profile, _ = MessengerProfile.objects.get_or_create(
                account=self.messenger.account
            )
            profile.persistent_menu = payload['persistent_menu']
            profile.save()
            
            return True
        except MessengerAPIException as e:
            logger.error(f"Error setting persistent menu: {e}")
            return False
    
    def set_ice_breakers(self, ice_breakers: List[Dict]) -> bool:
        """Define quebras de gelo"""
        try:
            payload = {'ice_breakers': ice_breakers}
            self.messenger.post('me/messenger_profile', payload)
            
            # Atualiza local
            profile, _ = MessengerProfile.objects.get_or_create(
                account=self.messenger.account
            )
            profile.ice_breakers = ice_breakers
            profile.save()
            
            return True
        except MessengerAPIException as e:
            logger.error(f"Error setting ice breakers: {e}")
            return False
    
    def whitelist_domains(self, domains: List[str]) -> bool:
        """Adiciona domínios à lista branca"""
        try:
            payload = {'whitelisted_domains': domains}
            self.messenger.post('me/messenger_profile', payload)
            
            # Atualiza local
            profile, _ = MessengerProfile.objects.get_or_create(
                account=self.messenger.account
            )
            profile.whitelisted_domains = domains
            profile.save()
            
            return True
        except MessengerAPIException as e:
            logger.error(f"Error whitelisting domains: {e}")
            return False
    
    def delete_profile_setting(self, fields: List[str]) -> bool:
        """Remove configurações de perfil"""
        try:
            payload = {'fields': fields}
            self.messenger._make_request('DELETE', 'me/messenger_profile', data=payload)
            return True
        except MessengerAPIException as e:
            logger.error(f"Error deleting profile setting: {e}")
            return False
    
    # ========== Conversas ==========
    
    def get_or_create_conversation(self, psid: str, 
                                   participant_name: str = "") -> MessengerConversation:
        """Obtém ou cria conversa"""
        conv, created = MessengerConversation.objects.get_or_create(
            account=self.messenger.account,
            psid=psid,
            defaults={'participant_name': participant_name}
        )
        
        if created and not participant_name:
            # Busca informações do usuário
            try:
                profile = self.messenger.get_user_profile(psid)
                first_name = profile.get('first_name', '')
                last_name = profile.get('last_name', '')
                conv.participant_name = f"{first_name} {last_name}".strip()
                conv.participant_profile_pic = profile.get('profile_pic', '')
                conv.save()
            except Exception as e:
                logger.error(f"Error fetching user profile: {e}")
        
        return conv
    
    def get_conversation(self, conversation_id: str) -> Optional[Dict]:
        """Obtém detalhes da conversa"""
        try:
            conv = MessengerConversation.objects.get(
                account=self.messenger.account,
                id=conversation_id
            )
            return {
                'id': str(conv.id),
                'psid': conv.psid,
                'participant_name': conv.participant_name,
                'participant_profile_pic': conv.participant_profile_pic,
                'unread_count': conv.unread_count,
                'last_message_at': conv.last_message_at.isoformat() if conv.last_message_at else None,
                'created_at': conv.created_at.isoformat()
            }
        except MessengerConversation.DoesNotExist:
            return None
    
    def list_conversations(self, limit: int = 50, unread_only: bool = False) -> List[Dict]:
        """Lista conversas"""
        queryset = MessengerConversation.objects.filter(
            account=self.messenger.account,
            is_active=True
        )
        
        if unread_only:
            queryset = queryset.filter(unread_count__gt=0)
        
        conversations = queryset.order_by('-last_message_at', '-created_at')[:limit]
        
        return [
            {
                'id': str(conv.id),
                'psid': conv.psid,
                'participant_name': conv.participant_name,
                'unread_count': conv.unread_count,
                'last_message_at': conv.last_message_at.isoformat() if conv.last_message_at else None
            }
            for conv in conversations
        ]
    
    def mark_conversation_read(self, conversation_id: str) -> bool:
        """Marca conversa como lida"""
        try:
            conv = MessengerConversation.objects.get(
                account=self.messenger.account,
                id=conversation_id
            )
            
            conv.unread_count = 0
            conv.save()
            
            conv.messages.filter(is_from_page=False, is_read=False).update(
                is_read=True, read_at=__import__('django.utils.timezone').utils.timezone.now()
            )
            
            return True
        except MessengerConversation.DoesNotExist:
            return False
    
    # ========== Mensagens ==========
    
    def send_text_message(self, psid: str, text: str,
                          quick_replies: List[Dict] = None) -> Dict:
        """Envia mensagem de texto"""
        message = {'text': text}
        if quick_replies:
            message['quick_replies'] = quick_replies
        
        return self.messenger.send_message(psid, message)
    
    def send_image(self, psid: str, image_url: str) -> Dict:
        """Envia imagem"""
        message = {
            'attachment': {
                'type': 'image',
                'payload': {'url': image_url}
            }
        }
        return self.messenger.send_message(psid, message)
    
    def send_video(self, psid: str, video_url: str) -> Dict:
        """Envia vídeo"""
        message = {
            'attachment': {
                'type': 'video',
                'payload': {'url': video_url}
            }
        }
        return self.messenger.send_message(psid, message)
    
    def send_audio(self, psid: str, audio_url: str) -> Dict:
        """Envia áudio"""
        message = {
            'attachment': {
                'type': 'audio',
                'payload': {'url': audio_url}
            }
        }
        return self.messenger.send_message(psid, message)
    
    def send_file(self, psid: str, file_url: str) -> Dict:
        """Envia arquivo"""
        message = {
            'attachment': {
                'type': 'file',
                'payload': {'url': file_url}
            }
        }
        return self.messenger.send_message(psid, message)
    
    def send_template(self, psid: str, template_payload: Dict) -> Dict:
        """Envia template genérico"""
        message = {
            'attachment': {
                'type': 'template',
                'payload': template_payload
            }
        }
        return self.messenger.send_message(psid, message)
    
    def send_generic_template(self, psid: str, elements: List[Dict]) -> Dict:
        """Envia template genérico com cards"""
        template = {
            'template_type': 'generic',
            'elements': elements
        }
        return self.send_template(psid, template)
    
    def send_button_template(self, psid: str, text: str, 
                             buttons: List[Dict]) -> Dict:
        """Envia template de botões"""
        template = {
            'template_type': 'button',
            'text': text,
            'buttons': buttons
        }
        return self.send_template(psid, template)
    
    def send_list_template(self, psid: str, elements: List[Dict],
                           top_element_style: str = "compact",
                           buttons: List[Dict] = None) -> Dict:
        """Envia template de lista"""
        template = {
            'template_type': 'list',
            'top_element_style': top_element_style,
            'elements': elements
        }
        if buttons:
            template['buttons'] = buttons
        
        return self.send_template(psid, template)
    
    def get_messages(self, conversation_id: str, limit: int = 50) -> List[Dict]:
        """Obtém mensagens da conversa"""
        messages = MessengerMessage.objects.filter(
            conversation__account=self.messenger.account,
            conversation__id=conversation_id
        ).order_by('-created_at')[:limit]
        
        return [
            {
                'id': str(msg.id),
                'type': msg.message_type,
                'content': msg.content,
                'attachment_url': msg.attachment_url,
                'is_from_page': msg.is_from_page,
                'is_read': msg.is_read,
                'created_at': msg.created_at.isoformat()
            }
            for msg in reversed(messages)
        ]
    
    # ========== Webhooks ==========
    
    def verify_webhook(self, verify_token: str, 
                       challenge: str, mode: str) -> Optional[str]:
        """Verifica webhook do Messenger"""
        from django.conf import settings
        
        if mode == 'subscribe' and verify_token == getattr(settings, 'MESSENGER_VERIFY_TOKEN', ''):
            return challenge
        return None