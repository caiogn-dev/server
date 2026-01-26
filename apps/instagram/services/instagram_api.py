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
GRAPH_API_BASE_URL = f'https://graph.facebook.com/{GRAPH_API_VERSION}'


class InstagramAPIService:
    """Service for interacting with Instagram Graph API."""
    
    def __init__(self, account=None):
        self.account = account
        self.access_token = account.access_token if account else None
        self.instagram_account_id = account.instagram_account_id if account else None
    
    def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """Make a request to the Graph API."""
        url = f"{GRAPH_API_BASE_URL}/{endpoint}"
        
        if params is None:
            params = {}
        
        params['access_token'] = self.access_token
        
        try:
            response = requests.request(
                method=method,
                url=url,
                params=params if method == 'GET' else None,
                json=json_data if method == 'POST' else None,
                timeout=timeout
            )
            
            data = response.json()
            
            if 'error' in data:
                error = data['error']
                logger.error(
                    f"Instagram API Error: {error.get('message')}",
                    extra={
                        'error_code': error.get('code'),
                        'error_subcode': error.get('error_subcode'),
                        'endpoint': endpoint
                    }
                )
                raise InstagramAPIError(
                    message=error.get('message'),
                    code=error.get('code'),
                    subcode=error.get('error_subcode')
                )
            
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Instagram API Request failed: {str(e)}")
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
        """Get list of conversations for this Instagram account."""
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
        endpoint = f"{self.instagram_account_id}/messages"
        
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
        
        return self._make_request('POST', endpoint, json_data=payload)
    
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
        endpoint = f"{self.instagram_account_id}/messages"
        
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
        
        return self._make_request('POST', endpoint, json_data=payload)
    
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
        endpoint = f"{self.instagram_account_id}/messages"
        
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
        
        return self._make_request('POST', endpoint, json_data=payload)
    
    def get_conversation(self, user_id: str) -> Dict[str, Any]:
        """Get conversation with a specific user."""
        endpoint = f"{self.instagram_account_id}/conversations"
        
        return self._make_request('GET', endpoint, params={
            'user_id': user_id,
            'fields': 'messages{id,message,from,to,created_time}'
        })
    
    def get_conversations(self, limit: int = 25) -> Dict[str, Any]:
        """Get all conversations."""
        endpoint = f"{self.instagram_account_id}/conversations"
        
        return self._make_request('GET', endpoint, params={
            'fields': 'participants,messages.limit(1){id,message,from,created_time}',
            'limit': limit
        })
    
    def mark_seen(self, recipient_id: str) -> Dict[str, Any]:
        """Mark messages as seen (send read receipt)."""
        endpoint = f"{self.instagram_account_id}/messages"
        
        payload = {
            'recipient': {'id': recipient_id},
            'sender_action': 'mark_seen'
        }
        
        return self._make_request('POST', endpoint, json_data=payload)
    
    def send_typing_indicator(self, recipient_id: str, typing_on: bool = True) -> Dict[str, Any]:
        """Send typing indicator."""
        endpoint = f"{self.instagram_account_id}/messages"
        
        payload = {
            'recipient': {'id': recipient_id},
            'sender_action': 'typing_on' if typing_on else 'typing_off'
        }
        
        return self._make_request('POST', endpoint, json_data=payload)
    
    # ==================== Ice Breakers ====================
    
    def set_ice_breakers(self, ice_breakers: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Set ice breakers (conversation starters).
        
        Args:
            ice_breakers: List of ice breakers [{'question': '...', 'payload': '...'}]
        """
        endpoint = f"{self.instagram_account_id}/messenger_profile"
        
        payload = {
            'ice_breakers': [
                {
                    'question': ib['question'],
                    'payload': ib['payload']
                }
                for ib in ice_breakers[:4]  # Max 4 ice breakers
            ]
        }
        
        return self._make_request('POST', endpoint, json_data=payload)
    
    def get_ice_breakers(self) -> Dict[str, Any]:
        """Get current ice breakers."""
        endpoint = f"{self.instagram_account_id}/messenger_profile"
        
        return self._make_request('GET', endpoint, params={
            'fields': 'ice_breakers'
        })
    
    def delete_ice_breakers(self) -> Dict[str, Any]:
        """Delete all ice breakers."""
        endpoint = f"{self.instagram_account_id}/messenger_profile"
        
        return self._make_request('DELETE', endpoint, params={
            'fields': 'ice_breakers'
        })
    
    # ==================== Persistent Menu ====================
    
    def set_persistent_menu(self, menu_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Set persistent menu.
        
        Args:
            menu_items: List of menu items
        """
        endpoint = f"{self.instagram_account_id}/messenger_profile"
        
        payload = {
            'persistent_menu': [
                {
                    'locale': 'default',
                    'call_to_actions': menu_items[:3]  # Max 3 top-level items
                }
            ]
        }
        
        return self._make_request('POST', endpoint, json_data=payload)
    
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
