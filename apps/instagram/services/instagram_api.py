import requests
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from django.conf import settings
from ..models import InstagramAccount

logger = logging.getLogger(__name__)


class InstagramAPI:
    """Cliente base para Instagram Graph API"""
    
    BASE_URL = "https://graph.facebook.com/v22.0"
    
    def __init__(self, account: InstagramAccount):
        self.account = account
        self.access_token = account.access_token
        self.session = requests.Session()

    def _resolve_token(self, endpoint: str) -> str:
        """
        Retorna o token correto para o endpoint.
        Endpoints de mensagens (/{page_id}/messages) exigem o Page Access Token.
        Demais endpoints usam o User/Instagram Access Token.
        """
        page_id = (self.account.facebook_page_id or '').strip()
        if page_id and endpoint.startswith(f'{page_id}/'):
            page_token = (self.account.page_access_token or '').strip()
            if not page_token:
                raise InstagramAPIException(
                    f"page_access_token não configurado para a conta @{self.account.username}. "
                    "Acesse o admin e preencha o campo 'Page Access Token'."
                )
            return page_token
        return self.access_token

    def _make_request(self, method: str, endpoint: str, params: Dict = None, data: Dict = None, files: Dict = None) -> Dict:
        """Faz requisição para a Graph API"""
        url = f"{self.BASE_URL}/{endpoint}"

        params = params or {}
        params['access_token'] = self._resolve_token(endpoint)
        
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
            api_error = error_data.get('error', {})
            code = api_error.get('code')
            subcode = api_error.get('error_subcode')
            message = api_error.get('message', str(e))
            fbtrace_id = api_error.get('fbtrace_id', '')
            logger.error(
                "Instagram API error: code=%s subcode=%s message=%s fbtrace_id=%s endpoint=%s",
                code, subcode, message, fbtrace_id, endpoint,
            )
            # Erros conhecidos da Messenger API for Instagram
            # https://developers.facebook.com/docs/instagram-platform/
            if code in (10, 551) or subcode == 2018108:
                raise InstagramAPIException(
                    'Janela de mensagens fechada: o usuário não enviou nenhuma mensagem nas últimas 24 horas.'
                )
            if code == 190:
                raise InstagramAPIException(
                    'Page Access Token inválido ou expirado. Atualize o token no admin.'
                )
            if code == 200:
                raise InstagramAPIException(
                    'Permissão insuficiente. Verifique se o app tem instagram_manage_messages e pages_manage_metadata.'
                )
            if code == 1:
                raise InstagramAPIException(
                    f'Requisição inválida para a API do Instagram (code=1). '
                    f'Verifique se as métricas solicitadas são suportadas na versão atual da API. '
                    f'Detalhe: {message}'
                )
            raise InstagramAPIException(message)
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
                'client_id': settings.INSTAGRAM_APP_ID,
                'client_secret': settings.INSTAGRAM_APP_SECRET,
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

    def refresh_page_token(self) -> bool:
        """Busca e salva o Page Access Token usando o User Access Token já configurado.

        O Page Access Token é necessário para enviar mensagens via /{page_id}/messages.
        Ele é obtido chamando GET /{page_id}?fields=access_token com o User Token.
        Tokens de página Long-Lived não expiram enquanto o User Token não expirar.
        """
        page_id = (self.account.facebook_page_id or '').strip()
        if not page_id:
            raise InstagramAPIException(
                "facebook_page_id não configurado. Preencha o campo no admin antes de renovar o token."
            )

        try:
            # Usa o user/instagram token para buscar o token da página
            url = f"{self.BASE_URL}/{page_id}"
            response = self.session.get(url, params={
                'fields': 'access_token',
                'access_token': self.access_token,
            }, timeout=30)
            response.raise_for_status()
            data = response.json()

            page_token = data.get('access_token')
            if not page_token:
                raise InstagramAPIException(
                    "A API não retornou um access_token para a página. "
                    "Verifique se o User Token tem a permissão 'pages_show_list' e 'pages_manage_metadata'."
                )

            self.account.page_access_token = page_token
            self.account.save(update_fields=['page_access_token', 'updated_at'])
            logger.info("Page Access Token renovado com sucesso para @%s", self.account.username)
            return True

        except InstagramAPIException:
            raise
        except Exception as e:
            logger.error("Erro ao renovar Page Access Token para @%s: %s", self.account.username, e)
            raise InstagramAPIException(f"Falha ao buscar Page Access Token: {e}")
    
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