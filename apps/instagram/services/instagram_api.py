import requests
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from django.conf import settings
from ..models import InstagramAccount

logger = logging.getLogger(__name__)


class InstagramAPI:
    """Cliente base para Instagram Graph API"""
    
    BASE_URL = "https://graph.facebook.com/v18.0"
    
    def __init__(self, account: InstagramAccount):
        self.account = account
        self.access_token = account.access_token
        self.session = requests.Session()
    
    def _make_request(self, method: str, endpoint: str, params: Dict = None, data: Dict = None, files: Dict = None) -> Dict:
        """Faz requisição para a Graph API"""
        url = f"{self.BASE_URL}/{endpoint}"
        
        params = params or {}
        params['access_token'] = self.access_token
        
        try:
            if files:
                response = self.session.request(method, url, params=params, data=data, files=files, timeout=120)
            elif method == 'GET':
                response = self.session.get(url, params=params, timeout=30)
            else:
                response = self.session.request(method, url, params=params, json=data, timeout=30)
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            error_data = response.json() if response.content else {}
            logger.error(f"Instagram API error: {error_data}")
            raise InstagramAPIException(error_data.get('error', {}).get('message', str(e)))
        except Exception as e:
            logger.error(f"Request error: {str(e)}")
            raise InstagramAPIException(str(e))
    
    def get(self, endpoint: str, params: Dict = None) -> Dict:
        return self._make_request('GET', endpoint, params=params)
    
    def post(self, endpoint: str, data: Dict = None, params: Dict = None, files: Dict = None) -> Dict:
        return self._make_request('POST', endpoint, params=params, data=data, files=files)
    
    def delete(self, endpoint: str, params: Dict = None) -> Dict:
        return self._make_request('DELETE', endpoint, params=params)
    
    def refresh_token(self) -> bool:
        """Renova o token de acesso"""
        try:
            response = self.get('oauth/access_token', {
                'grant_type': 'fb_exchange_token',
                'client_id': settings.FACEBOOK_APP_ID,
                'client_secret': settings.FACEBOOK_APP_SECRET,
                'fb_exchange_token': self.access_token
            })
            
            if 'access_token' in response:
                self.account.access_token = response['access_token']
                expires_in = response.get('expires_in', 5184000)  # 60 dias default
                self.account.token_expires_at = datetime.now() + timedelta(seconds=expires_in)
                self.account.save()
                return True
            return False
        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            return False
    
    def get_account_info(self) -> Dict:
        """Obtém informações da conta"""
        if not self.account.instagram_business_id:
            raise InstagramAPIException("Instagram Business ID não configurado")
        
        fields = [
            'id', 'username', 'name', 'biography', 'website',
            'followers_count', 'follows_count', 'media_count',
            'profile_picture_url', 'verified'
        ]
        
        return self.get(self.account.instagram_business_id, {'fields': ','.join(fields)})
    
    def sync_account_info(self) -> bool:
        """Sincroniza informações da conta com o banco de dados"""
        try:
            info = self.get_account_info()
            self.account.username = info.get('username', self.account.username)
            self.account.biography = info.get('biography', '')
            self.account.website = info.get('website', '')
            self.account.followers_count = info.get('followers_count', 0)
            self.account.follows_count = info.get('follows_count', 0)
            self.account.media_count = info.get('media_count', 0)
            self.account.profile_picture_url = info.get('profile_picture_url', '')
            self.account.is_verified = info.get('verified', False)
            self.account.last_sync_at = datetime.now()
            self.account.save()
            return True
        except Exception as e:
            logger.error(f"Error syncing account: {e}")
            return False


class InstagramAPIException(Exception):
    """Exceção para erros da API do Instagram"""
    pass