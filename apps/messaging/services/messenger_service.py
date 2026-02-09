import requests
import logging
from typing import Optional, Dict, List, Any
from django.conf import settings
from ..models import MessengerAccount, MessengerConversation, MessengerMessage

logger = logging.getLogger(__name__)


class MessengerService:
    """Serviço base para Messenger Platform"""
    
    BASE_URL = "https://graph.facebook.com/v18.0"
    
    def __init__(self, account: MessengerAccount):
        self.account = account
        self.access_token = account.page_access_token
        self.session = requests.Session()
    
    def _make_request(self, method: str, endpoint: str, 
                      params: Dict = None, data: Dict = None,
                      headers: Dict = None) -> Dict:
        """Faz requisição para a Messenger API"""
        url = f"{self.BASE_URL}/{endpoint}"
        
        params = params or {}
        params['access_token'] = self.access_token
        
        default_headers = {'Content-Type': 'application/json'}
        if headers:
            default_headers.update(headers)
        
        try:
            if method == 'GET':
                response = self.session.get(url, params=params, timeout=30)
            elif method == 'POST':
                response = self.session.post(
                    url, 
                    params=params,
                    json=data,
                    headers=default_headers,
                    timeout=30
                )
            elif method == 'DELETE':
                response = self.session.delete(url, params=params, timeout=30)
            else:
                response = self.session.request(method, url, params=params, timeout=30)
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            error_data = response.json() if response.content else {}
            logger.error(f"Messenger API error: {error_data}")
            raise MessengerAPIException(error_data.get('error', {}).get('message', str(e)))
        except Exception as e:
            logger.error(f"Request error: {str(e)}")
            raise MessengerAPIException(str(e))
    
    def get(self, endpoint: str, params: Dict = None) -> Dict:
        return self._make_request('GET', endpoint, params=params)
    
    def post(self, endpoint: str, data: Dict = None, params: Dict = None) -> Dict:
        return self._make_request('POST', endpoint, params=params, data=data)
    
    def delete(self, endpoint: str, params: Dict = None) -> Dict:
        return self._make_request('DELETE', endpoint, params=params)
    
    def send_message(self, psid: str, message: Dict, 
                     messaging_type: str = "RESPONSE") -> Dict:
        """Envia mensagem para um usuário"""
        payload = {
            'recipient': {'id': psid},
            'message': message,
            'messaging_type': messaging_type
        }
        
        return self.post('me/messages', payload)
    
    def get_user_profile(self, psid: str, fields: List[str] = None) -> Dict:
        """Obtém perfil do usuário"""
        if not fields:
            fields = ['first_name', 'last_name', 'profile_pic']
        
        return self.get(psid, {'fields': ','.join(fields)})
    
    def mark_seen(self, psid: str) -> Dict:
        """Marca mensagens como vistas"""
        payload = {
            'recipient': {'id': psid},
            'sender_action': 'mark_seen'
        }
        return self.post('me/messages', payload)
    
    def typing_on(self, psid: str) -> Dict:
        """Indica que está digitando"""
        payload = {
            'recipient': {'id': psid},
            'sender_action': 'typing_on'
        }
        return self.post('me/messages', payload)
    
    def typing_off(self, psid: str) -> Dict:
        """Remove indicador de digitação"""
        payload = {
            'recipient': {'id': psid},
            'sender_action': 'typing_off'
        }
        return self.post('me/messages', payload)


class MessengerAPIException(Exception):
    """Exceção para erros da API do Messenger"""
    pass