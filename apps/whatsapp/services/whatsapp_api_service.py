"""
WhatsApp Business API Service.
"""
import logging
import requests
from typing import Dict, Any, Optional, List
from django.conf import settings
from apps.core.exceptions import WhatsAppAPIError
from ..models import WhatsAppAccount

logger = logging.getLogger(__name__)


class WhatsAppAPIService:
    """Service for interacting with WhatsApp Business API."""

    def __init__(self, account: WhatsAppAccount):
        self.account = account
        self.base_url = settings.WHATSAPP_API_BASE_URL
        self.phone_number_id = account.phone_number_id
        self.access_token = account.access_token

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers."""
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
        }

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to WhatsApp API."""
        url = f"{self.base_url}/{endpoint}"
        
        logger.debug(
            'WhatsApp API request',
            extra={'endpoint': endpoint, 'payload': data, 'params': params}
        )
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self._get_headers(),
                json=data,
                params=params,
                timeout=30
            )
            
            response_data = response.json() if response.content else {}
            
            if response.status_code >= 400:
                error = response_data.get('error', {})
                
                # Build a meaningful error message
                error_message = error.get('message', '')
                error_code = error.get('code', 'unknown')
                error_type = error.get('type', '')
                error_subcode = error.get('error_subcode', '')
                
                # If message is empty, build one from available info
                if not error_message:
                    error_message = f"WhatsApp API error (code: {error_code})"
                    if error_type:
                        error_message += f", type: {error_type}"
                    if error_subcode:
                        error_message += f", subcode: {error_subcode}"
                
                # Include error code in message for easier debugging
                full_message = f"(#{error_code}) {error_message}" if error_code != 'unknown' else error_message
                
                logger.error(
                    f"WhatsApp API error: {full_message}",
                    extra={
                        'status_code': response.status_code,
                        'endpoint': endpoint,
                        'error': error,
                        'error_code': error_code,
                        'error_message': error_message,
                    }
                )
                raise WhatsAppAPIError(
                    message=full_message,
                    code=str(error_code),
                    details=error
                )
            
            return response_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"WhatsApp API request failed: {str(e)}")
            raise WhatsAppAPIError(
                message=f"Request failed: {str(e)}",
                code='request_failed'
            )

    def send_text_message(
        self,
        to: str,
        text: str,
        preview_url: bool = False,
        reply_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send a text message."""
        if not self.phone_number_id:
            raise WhatsAppAPIError(
                message='WhatsApp phone_number_id is not configured',
                code='missing_phone_number_id'
            )

        payload = {
            'messaging_product': 'whatsapp',
            'recipient_type': 'individual',
            'to': to,
            'type': 'text',
            'text': {
                'body': text
            }
        }

        if preview_url:
            payload['text']['preview_url'] = True

        if reply_to:
            payload['context'] = {'message_id': reply_to}

        return self._make_request(
            'POST',
            f'{self.phone_number_id}/messages',
            data=payload
        )

    def send_template_message(
        self,
        to: str,
        template_name: str,
        language_code: str = 'pt_BR',
        components: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Send a template message."""
        payload = {
            'messaging_product': 'whatsapp',
            'recipient_type': 'individual',
            'to': to,
            'type': 'template',
            'template': {
                'name': template_name,
                'language': {
                    'code': language_code
                }
            }
        }
        
        if components:
            payload['template']['components'] = components
        
        return self._make_request(
            'POST',
            f'{self.phone_number_id}/messages',
            data=payload
        )

    def send_interactive_buttons(
        self,
        to: str,
        body_text: str,
        buttons: List[Dict[str, str]],
        header: Optional[Dict] = None,
        footer: Optional[str] = None,
        reply_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send interactive button message."""
        button_list = []
        for i, btn in enumerate(buttons[:3]):
            button_list.append({
                'type': 'reply',
                'reply': {
                    'id': btn.get('id', f'btn_{i}'),
                    'title': btn['title'][:20]
                }
            })
        
        payload = {
            'messaging_product': 'whatsapp',
            'recipient_type': 'individual',
            'to': to,
            'type': 'interactive',
            'interactive': {
                'type': 'button',
                'body': {'text': body_text},
                'action': {'buttons': button_list}
            }
        }
        
        if header:
            payload['interactive']['header'] = header
        if footer:
            payload['interactive']['footer'] = {'text': footer}
        if reply_to:
            payload['context'] = {'message_id': reply_to}
        
        return self._make_request(
            'POST',
            f'{self.phone_number_id}/messages',
            data=payload
        )

    def send_interactive_list(
        self,
        to: str,
        body_text: str,
        button_text: str,
        sections: List[Dict],
        header: Optional[str] = None,
        footer: Optional[str] = None,
        reply_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send interactive list message."""
        payload = {
            'messaging_product': 'whatsapp',
            'recipient_type': 'individual',
            'to': to,
            'type': 'interactive',
            'interactive': {
                'type': 'list',
                'body': {'text': body_text},
                'action': {
                    'button': button_text,
                    'sections': sections
                }
            }
        }
        
        if header:
            payload['interactive']['header'] = {'type': 'text', 'text': header}
        if footer:
            payload['interactive']['footer'] = {'text': footer}
        if reply_to:
            payload['context'] = {'message_id': reply_to}
        
        return self._make_request(
            'POST',
            f'{self.phone_number_id}/messages',
            data=payload
        )

    def send_image(
        self,
        to: str,
        image_url: Optional[str] = None,
        image_id: Optional[str] = None,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send an image message."""
        image_data = {}
        if image_url:
            image_data['link'] = image_url
        elif image_id:
            image_data['id'] = image_id
        
        if caption:
            image_data['caption'] = caption
        
        payload = {
            'messaging_product': 'whatsapp',
            'recipient_type': 'individual',
            'to': to,
            'type': 'image',
            'image': image_data
        }
        
        if reply_to:
            payload['context'] = {'message_id': reply_to}
        
        return self._make_request(
            'POST',
            f'{self.phone_number_id}/messages',
            data=payload
        )

    def send_document(
        self,
        to: str,
        document_url: Optional[str] = None,
        document_id: Optional[str] = None,
        filename: Optional[str] = None,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send a document message."""
        document_data = {}
        if document_url:
            document_data['link'] = document_url
        elif document_id:
            document_data['id'] = document_id
        
        if filename:
            document_data['filename'] = filename
        if caption:
            document_data['caption'] = caption
        
        payload = {
            'messaging_product': 'whatsapp',
            'recipient_type': 'individual',
            'to': to,
            'type': 'document',
            'document': document_data
        }
        
        if reply_to:
            payload['context'] = {'message_id': reply_to}
        
        return self._make_request(
            'POST',
            f'{self.phone_number_id}/messages',
            data=payload
        )

    def send_location(
        self,
        to: str,
        latitude: float,
        longitude: float,
        name: Optional[str] = None,
        address: Optional[str] = None,
        reply_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send a location message."""
        location_data = {
            'latitude': latitude,
            'longitude': longitude
        }
        
        if name:
            location_data['name'] = name
        if address:
            location_data['address'] = address
        
        payload = {
            'messaging_product': 'whatsapp',
            'recipient_type': 'individual',
            'to': to,
            'type': 'location',
            'location': location_data
        }
        
        if reply_to:
            payload['context'] = {'message_id': reply_to}
        
        return self._make_request(
            'POST',
            f'{self.phone_number_id}/messages',
            data=payload
        )

    def send_reaction(
        self,
        to: str,
        message_id: str,
        emoji: str
    ) -> Dict[str, Any]:
        """Send a reaction to a message."""
        payload = {
            'messaging_product': 'whatsapp',
            'recipient_type': 'individual',
            'to': to,
            'type': 'reaction',
            'reaction': {
                'message_id': message_id,
                'emoji': emoji
            }
        }
        
        return self._make_request(
            'POST',
            f'{self.phone_number_id}/messages',
            data=payload
        )

    def mark_as_read(self, message_id: str) -> Dict[str, Any]:
        """Mark a message as read."""
        payload = {
            'messaging_product': 'whatsapp',
            'status': 'read',
            'message_id': message_id
        }
        
        return self._make_request(
            'POST',
            f'{self.phone_number_id}/messages',
            data=payload
        )

    def get_media_url(self, media_id: str) -> str:
        """Get media URL from media ID."""
        response = self._make_request('GET', media_id)
        return response.get('url', '')

    def download_media(self, media_url: str) -> bytes:
        """Download media from URL."""
        try:
            response = requests.get(
                media_url,
                headers={'Authorization': f'Bearer {self.access_token}'},
                timeout=60
            )
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download media: {str(e)}")
            raise WhatsAppAPIError(
                message=f"Failed to download media: {str(e)}",
                code='media_download_failed'
            )

    def upload_media(
        self,
        file_data: bytes,
        mime_type: str,
        filename: str
    ) -> Dict[str, Any]:
        """Upload media to WhatsApp."""
        url = f"{self.base_url}/{self.phone_number_id}/media"
        
        files = {
            'file': (filename, file_data, mime_type)
        }
        data = {
            'messaging_product': 'whatsapp',
            'type': mime_type
        }
        
        try:
            response = requests.post(
                url,
                headers={'Authorization': f'Bearer {self.access_token}'},
                files=files,
                data=data,
                timeout=120
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to upload media: {str(e)}")
            raise WhatsAppAPIError(
                message=f"Failed to upload media: {str(e)}",
                code='media_upload_failed'
            )

    def get_business_profile(self) -> Dict[str, Any]:
        """Get business profile information."""
        return self._make_request(
            'GET',
            f'{self.phone_number_id}/whatsapp_business_profile',
            params={'fields': 'about,address,description,email,profile_picture_url,websites,vertical'}
        )

    def update_business_profile(self, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update business profile."""
        payload = {
            'messaging_product': 'whatsapp',
            **profile_data
        }
        
        return self._make_request(
            'POST',
            f'{self.phone_number_id}/whatsapp_business_profile',
            data=payload
        )

    def get_templates(self, limit: int = 100) -> Dict[str, Any]:
        """Get message templates."""
        return self._make_request(
            'GET',
            f'{self.account.waba_id}/message_templates',
            params={'limit': limit}
        )

    def get_phone_numbers(self) -> Dict[str, Any]:
        """Get phone numbers associated with WABA."""
        return self._make_request(
            'GET',
            f'{self.account.waba_id}/phone_numbers'
        )
