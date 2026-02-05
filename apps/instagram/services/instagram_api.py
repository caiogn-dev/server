"""
Instagram API Service - Handles all Meta Graph API interactions for Instagram.
"""
import logging
import requests
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = 'v21.0'
FACEBOOK_GRAPH_URL = f'https://graph.facebook.com/{GRAPH_API_VERSION}'
INSTAGRAM_GRAPH_URL = f'https://graph.instagram.com/{GRAPH_API_VERSION}'


class InstagramAPIService:
    """Service for interacting with Instagram Graph API."""
    
    def __init__(self, account=None):
        self.account = account
        self.access_token = account.access_token if account else None
        self.instagram_account_id = account.instagram_account_id if account else None
        
        # Detect token type and set appropriate base URL
        # IGAA tokens use graph.instagram.com, EAAF tokens use graph.facebook.com
        if self.access_token and self.access_token.startswith('IGAA'):
            self.base_url = INSTAGRAM_GRAPH_URL
        else:
            self.base_url = FACEBOOK_GRAPH_URL
    
    def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        timeout: int = 30,
        use_facebook_api: bool = False
    ) -> Dict[str, Any]:
        """Make a request to the Graph API."""
        # Some endpoints only work on Facebook Graph API
        base = FACEBOOK_GRAPH_URL if use_facebook_api else self.base_url
        url = f"{base}/{endpoint}"
        
        if params is None:
            params = {}
        
        params['access_token'] = self.access_token
        
        try:
            logger.info(f"Instagram API Request: {method} {url}", extra={
                'endpoint': endpoint,
                'method': method,
                'has_json_data': bool(json_data),
                'json_data': json_data if json_data else None,
                'params': {k: v for k, v in params.items() if k != 'access_token'} if params else None,
                'full_url': url
            })
            
            response = requests.request(
                method=method,
                url=url,
                params=params if method == 'GET' else None,
                json=json_data if method == 'POST' else None,
                timeout=timeout
            )
            
            logger.info(f"Instagram API Response: {response.status_code}", extra={
                'status_code': response.status_code,
                'response_text': response.text[:1000],
                'headers': dict(response.headers)
            })
            
            data = response.json()
            
            if 'error' in data:
                error = data['error']
                error_code = error.get('code')
                error_subcode = error.get('error_subcode')
                error_message = error.get('message', 'An unknown error has occurred.')
                
                # Traduzir mensagens de erro comuns
                if error_code == 10 and error_subcode == 2534022:
                    error_message = "Não é possível enviar mensagem. A janela de 24 horas expirou. O usuário precisa enviar uma nova mensagem primeiro."
                elif error_code == 100:
                    error_message = f"Parâmetro inválido: {error_message}"
                elif error_code == 1:
                    # Error code 1 - Unknown error, provide more context
                    error_details = [
                        "Erro desconhecido da API do Instagram.",
                        f"Mensagem original: {error_message}",
                        "Possíveis causas:",
                        "- Recipient ID inválido ou não existe",
                        "- Conta do Instagram não configurada corretamente",
                        "- Permissões insuficientes no app",
                        "- Token expirado ou inválido"
                    ]
                    error_message = " ".join(error_details)
                
                logger.error(
                    f"Instagram API Error: {error_message}",
                    extra={
                        'error_code': error_code,
                        'error_subcode': error_subcode,
                        'error_type': error.get('type'),
                        'fbtrace_id': error.get('fbtrace_id'),
                        'endpoint': endpoint,
                        'full_error': error
                    }
                )
                raise InstagramAPIError(
                    message=error_message,
                    code=error_code,
                    subcode=error_subcode
                )
            
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Instagram API Request failed: {str(e)}", exc_info=True)
            raise InstagramAPIError(message=str(e))
    
    # ==================== Account Management ====================
    
    def get_account_info(self) -> Dict[str, Any]:
        """Get Instagram account information."""
        return self._make_request(
            'GET',
            self.instagram_account_id,
            params={
                'fields': 'id,username,name,profile_picture_url,followers_count,follows_count,media_count'
            }
        )
    
    def exchange_code_for_token(self, code: str, redirect_uri: str, app_id: str, app_secret: str) -> Dict[str, Any]:
        """Exchange authorization code for access token."""
        url = f"{GRAPH_API_BASE_URL}/oauth/access_token"
        
        response = requests.get(url, params={
            'client_id': app_id,
            'client_secret': app_secret,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri,
            'code': code
        })
        
        data = response.json()
        if 'error' in data:
            raise InstagramAPIError(message=data['error'].get('message'))
        
        return data
    
    def get_long_lived_token(self, short_lived_token: str, app_secret: str) -> Dict[str, Any]:
        """Exchange short-lived token for long-lived token (60 days)."""
        url = f"{GRAPH_API_BASE_URL}/oauth/access_token"
        
        response = requests.get(url, params={
            'grant_type': 'fb_exchange_token',
            'client_id': self.account.app_id if self.account else settings.INSTAGRAM_APP_ID,
            'client_secret': app_secret,
            'fb_exchange_token': short_lived_token
        })
        
        data = response.json()
        if 'error' in data:
            raise InstagramAPIError(message=data['error'].get('message'))
        
        return data
    
    def refresh_long_lived_token(self) -> Dict[str, Any]:
        """Refresh a long-lived token (must be done before expiration)."""
        url = f"{GRAPH_API_BASE_URL}/oauth/access_token"
        
        response = requests.get(url, params={
            'grant_type': 'fb_exchange_token',
            'client_id': self.account.app_id,
            'client_secret': self.account.app_secret,
            'fb_exchange_token': self.access_token
        })
        
        data = response.json()
        if 'error' in data:
            raise InstagramAPIError(message=data['error'].get('message'))
        
        return data
    
    # ==================== Conversations ====================
    
    def get_conversations(self, limit: int = 50) -> Dict[str, Any]:
        """Get list of conversations for this Instagram account.
        
        Uses Facebook Page ID with platform=instagram for Page Access Tokens.
        """
        # For Page Access Tokens, we need to use the Page ID with platform filter
        page_id = self.account.facebook_page_id if self.account else None
        
        if page_id:
            # Use Facebook Graph API with Page ID
            return self._make_request(
                'GET',
                f"{page_id}/conversations",
                params={
                    'platform': 'instagram',
                    'fields': 'id,participants,updated_time,messages{id,from,to,message,created_time}',
                    'limit': limit
                },
                use_facebook_api=True
            )
        else:
            # Fallback to Instagram Graph API (for IGAA tokens)
            return self._make_request(
                'GET',
                f"{self.instagram_account_id}/conversations",
                params={
                    'fields': 'id,participants,updated_time,messages{id,from,to,message,created_time}',
                    'limit': limit
                }
            )
    
    def get_conversation_messages(self, conversation_id: str, limit: int = 50) -> Dict[str, Any]:
        """Get messages from a specific conversation."""
        return self._make_request(
            'GET',
            f"{conversation_id}",
            params={
                'fields': 'id,participants,messages.limit({limit}){id,from,to,message,created_time,attachments}',
            }
        )
    
    # ==================== Messaging ====================
    
    def send_message(
        self, 
        recipient_id: str, 
        message_text: Optional[str] = None,
        attachment_url: Optional[str] = None,
        attachment_type: str = 'image'
    ) -> Dict[str, Any]:
        """
        Send a message to an Instagram user.
        
        Args:
            recipient_id: Instagram-scoped user ID (IGSID)
            message_text: Text message to send
            attachment_url: URL of attachment (image, video, etc)
            attachment_type: Type of attachment (image, video, audio, file)
        
        Returns:
            API response with message_id
        """
        if not recipient_id:
            raise InstagramAPIError("recipient_id is required")
        
        if not message_text and not attachment_url:
            raise InstagramAPIError("Either message_text or attachment_url is required")
        
        # IMPORTANT: For Instagram messaging with Page Access Token:
        # Use the Facebook Page ID as endpoint (/{page-id}/messages)
        # The API will automatically route to Instagram based on the recipient
        # Reference: https://developers.facebook.com/docs/messenger-platform/instagram/features/send-message
        page_id = self.account.facebook_page_id if self.account else None
        if not page_id:
            raise InstagramAPIError("facebook_page_id is required for sending Instagram messages")
        
        endpoint = f"{page_id}/messages"
        
        logger.info(f"Sending Instagram message", extra={
            'recipient_id': recipient_id,
            'has_text': bool(message_text),
            'has_attachment': bool(attachment_url),
            'page_id': page_id,
            'instagram_business_id': self.account.instagram_account_id if self.account else None,
            'endpoint': endpoint
        })
        
        payload = {
            'recipient': {'id': recipient_id}
        }
        
        if message_text:
            payload['message'] = {'text': message_text}
        elif attachment_url:
            payload['message'] = {
                'attachment': {
                    'type': attachment_type,
                    'payload': {'url': attachment_url}
                }
            }
        
        # Use Facebook Graph API with Instagram Business Account ID
        return self._make_request('POST', endpoint, json_data=payload, use_facebook_api=True)
    
    def send_text_message(self, recipient_id: str, text: str) -> Dict[str, Any]:
        """Send a text message."""
        return self.send_message(recipient_id, message_text=text)
    
    def send_image(self, recipient_id: str, image_url: str) -> Dict[str, Any]:
        """Send an image message."""
        return self.send_message(recipient_id, attachment_url=image_url, attachment_type='image')
    
    def send_video(self, recipient_id: str, video_url: str) -> Dict[str, Any]:
        """Send a video message."""
        return self.send_message(recipient_id, attachment_url=video_url, attachment_type='video')
    
    def send_audio(self, recipient_id: str, audio_url: str) -> Dict[str, Any]:
        """Send an audio message."""
        return self.send_message(recipient_id, attachment_url=audio_url, attachment_type='audio')
    
    def send_quick_replies(
        self, 
        recipient_id: str, 
        text: str, 
        quick_replies: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Send a message with quick reply buttons.
        
        Args:
            recipient_id: Instagram-scoped user ID
            text: Message text
            quick_replies: List of quick reply options [{'title': '...', 'payload': '...'}]
        """
        page_id = self.account.facebook_page_id if self.account else None
        if not page_id:
            raise InstagramAPIError("facebook_page_id is required")
        endpoint = f"{page_id}/messages"
        
        payload = {
            'recipient': {'id': recipient_id},
            'message': {
                'text': text,
                'quick_replies': [
                    {
                        'content_type': 'text',
                        'title': qr['title'],
                        'payload': qr['payload']
                    }
                    for qr in quick_replies[:13]  # Max 13 quick replies
                ]
            }
        }
        
        return self._make_request('POST', endpoint, json_data=payload, use_facebook_api=True)
    
    def send_generic_template(
        self, 
        recipient_id: str, 
        elements: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Send a generic template message (carousel).
        
        Args:
            recipient_id: Instagram-scoped user ID
            elements: List of template elements (max 10)
        """
        page_id = self.account.facebook_page_id if self.account else None
        if not page_id:
            raise InstagramAPIError("facebook_page_id is required")
        endpoint = f"{page_id}/messages"
        
        payload = {
            'recipient': {'id': recipient_id},
            'message': {
                'attachment': {
                    'type': 'template',
                    'payload': {
                        'template_type': 'generic',
                        'elements': elements[:10]
                    }
                }
            }
        }
        
        return self._make_request('POST', endpoint, json_data=payload, use_facebook_api=True)
    
    def get_conversation(self, user_id: str) -> Dict[str, Any]:
        """Get conversation with a specific user."""
        # Use Page ID with platform filter for Page Access Tokens
        page_id = self.account.facebook_page_id if self.account else None
        
        if page_id:
            return self._make_request('GET', f"{page_id}/conversations", params={
                'platform': 'instagram',
                'user_id': user_id,
                'fields': 'messages{id,message,from,to,created_time}'
            }, use_facebook_api=True)
        else:
            endpoint = f"{self.instagram_account_id}/conversations"
            return self._make_request('GET', endpoint, params={
                'user_id': user_id,
                'fields': 'messages{id,message,from,to,created_time}'
            })
    
    # NOTE: get_conversations is already defined above (line ~151) with proper Page ID support
    # Removed duplicate definition that was overriding the correct one
    
    def mark_seen(self, recipient_id: str) -> Dict[str, Any]:
        """Mark messages as seen (send read receipt)."""
        page_id = self.account.facebook_page_id if self.account else None
        if not page_id:
            raise InstagramAPIError("facebook_page_id is required")
        endpoint = f"{page_id}/messages"
        
        payload = {
            'recipient': {'id': recipient_id},
            'sender_action': 'mark_seen'
        }
        
        return self._make_request('POST', endpoint, json_data=payload, use_facebook_api=True)
    
    def send_typing_indicator(self, recipient_id: str, typing_on: bool = True) -> Dict[str, Any]:
        """Send typing indicator.
        
        Note: Typing indicators may not be supported for all Instagram accounts.
        The API may return error code 1 if not supported.
        """
        page_id = self.account.facebook_page_id if self.account else None
        if not page_id:
            raise InstagramAPIError("facebook_page_id is required")
        endpoint = f"{page_id}/messages"
        
        payload = {
            'recipient': {'id': recipient_id},
            'sender_action': 'typing_on' if typing_on else 'typing_off'
        }
        
        try:
            return self._make_request('POST', endpoint, json_data=payload, use_facebook_api=True)
        except InstagramAPIError as e:
            # Error code 1 means feature not supported - log but don't raise
            if e.code == 1:
                logger.warning(f"Typing indicator not supported for this account: {e}")
                return {'success': False, 'reason': 'not_supported'}
            raise
    
    # ==================== Ice Breakers ====================
    
    def set_ice_breakers(self, ice_breakers: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Set ice breakers (conversation starters).
        
        Args:
            ice_breakers: List of ice breakers [{'question': '...', 'payload': '...'}]
        """
        page_id = self.account.facebook_page_id if self.account else None
        endpoint_id = page_id if page_id else self.instagram_account_id
        endpoint = f"{endpoint_id}/messenger_profile"
        
        payload = {
            'ice_breakers': [
                {
                    'question': ib['question'],
                    'payload': ib['payload']
                }
                for ib in ice_breakers[:4]  # Max 4 ice breakers
            ]
        }
        
        return self._make_request('POST', endpoint, json_data=payload, use_facebook_api=bool(page_id))
    
    def get_ice_breakers(self) -> Dict[str, Any]:
        """Get current ice breakers."""
        page_id = self.account.facebook_page_id if self.account else None
        endpoint_id = page_id if page_id else self.instagram_account_id
        endpoint = f"{endpoint_id}/messenger_profile"
        
        return self._make_request('GET', endpoint, params={
            'fields': 'ice_breakers'
        }, use_facebook_api=bool(page_id))
    
    def delete_ice_breakers(self) -> Dict[str, Any]:
        """Delete all ice breakers."""
        page_id = self.account.facebook_page_id if self.account else None
        endpoint_id = page_id if page_id else self.instagram_account_id
        endpoint = f"{endpoint_id}/messenger_profile"
        
        return self._make_request('DELETE', endpoint, params={
            'fields': 'ice_breakers'
        }, use_facebook_api=bool(page_id))
    
    # ==================== Persistent Menu ====================
    
    def set_persistent_menu(self, menu_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Set persistent menu.
        
        Args:
            menu_items: List of menu items
        """
        page_id = self.account.facebook_page_id if self.account else None
        endpoint_id = page_id if page_id else self.instagram_account_id
        endpoint = f"{endpoint_id}/messenger_profile"
        
        payload = {
            'persistent_menu': [
                {
                    'locale': 'default',
                    'call_to_actions': menu_items[:3]  # Max 3 top-level items
                }
            ]
        }
        
        return self._make_request('POST', endpoint, json_data=payload, use_facebook_api=bool(page_id))
    
    # ==================== User Info ====================
    
    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """Get Instagram user profile info."""
        return self._make_request('GET', user_id, params={
            'fields': 'name,username,profile_pic,follower_count,is_user_follow_business,is_business_follow_user'
        })


class InstagramAPIError(Exception):
    """Custom exception for Instagram API errors."""
    
    def __init__(self, message: str, code: Optional[int] = None, subcode: Optional[int] = None):
        self.message = message
        self.code = code
        self.subcode = subcode
        super().__init__(self.message)
    
    def __str__(self):
        parts = [self.message]
        if self.code:
            parts.append(f"(code: {self.code})")
        if self.subcode:
            parts.append(f"(subcode: {self.subcode})")
        return ' '.join(parts)
