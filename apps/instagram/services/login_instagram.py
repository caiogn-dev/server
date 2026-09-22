"""Login com Instagram (Business Login for Instagram): conectar a conta do lojista.

O lojista entra com o próprio Instagram — sem Página do Facebook — e autoriza
só o que a loja usa: ler a conta, responder o direct e os comentários.
Substitui o login do Facebook, que dependia de permissões de Página que a Meta
recusou e por isso nunca conectou uma loja cliente.
"""
import logging
from datetime import timedelta
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Marca o state deste fluxo; o retorno antigo (Facebook) segue para quem não tem.
PREFIXO = 'iglogin:'
VALIDADE_DO_STATE = 600  # 10 min para o lojista concluir o login

ESCOPOS = (
    'instagram_business_basic',
    'instagram_business_manage_messages',
    'instagram_business_manage_comments',
)
WEBHOOKS = ('messages', 'messaging_postbacks', 'messaging_seen', 'comments', 'mentions')


class LoginFalhou(Exception):
    """Motivo curto, seguro para ir na URL de volta ao painel."""


def disponivel() -> bool:
    return bool(settings.INSTAGRAM_LOGIN_APP_ID and settings.INSTAGRAM_LOGIN_APP_SECRET)


def url_de_autorizacao(user) -> str:
    state = TimestampSigner().sign(f'{PREFIXO}{user.id}')
    return 'https://www.instagram.com/oauth/authorize?' + urlencode({
        'client_id': settings.INSTAGRAM_LOGIN_APP_ID,
        'redirect_uri': settings.INSTAGRAM_OAUTH_REDIRECT_URI,
        'response_type': 'code',
        'scope': ','.join(ESCOPOS),
        'state': state,
    })


def eh_deste_fluxo(state: str) -> bool:
    return (state or '').startswith(PREFIXO)


def usuario_do_state(state: str):
    from django.contrib.auth import get_user_model

    try:
        valor = TimestampSigner().unsign(state, max_age=VALIDADE_DO_STATE)
    except (BadSignature, SignatureExpired):
        raise LoginFalhou('login_expirado')
    if not valor.startswith(PREFIXO):
        raise LoginFalhou('login_expirado')
    user = get_user_model().objects.filter(id=valor[len(PREFIXO):]).first()
    if user is None:
        raise LoginFalhou('login_expirado')
    return user


def _json(resposta, etapa: str) -> dict:
    try:
        resposta.raise_for_status()
        return resposta.json()
    except Exception as exc:
        logger.error('Login com Instagram falhou em %s: %s', etapa, exc)
        raise LoginFalhou(etapa)


def concluir(user, code: str):
    """Troca o código, guarda a conta e assina os webhooks. Devolve a conta."""
    from apps.instagram.models import InstagramAccount

    curto = _json(requests.post(
        'https://api.instagram.com/oauth/access_token',
        data={
            'client_id': settings.INSTAGRAM_LOGIN_APP_ID,
            'client_secret': settings.INSTAGRAM_LOGIN_APP_SECRET,
            'grant_type': 'authorization_code',
            'redirect_uri': settings.INSTAGRAM_OAUTH_REDIRECT_URI,
            'code': code,
        },
        timeout=30,
    ), 'troca_do_codigo')

    longo = _json(requests.get(
        'https://graph.instagram.com/access_token',
        params={
            'grant_type': 'ig_exchange_token',
            'client_secret': settings.INSTAGRAM_LOGIN_APP_SECRET,
            'access_token': curto['access_token'],
        },
        timeout=30,
    ), 'token_de_60_dias')
    token = longo['access_token']

    info = _json(requests.get(
        f'{settings.INSTAGRAM_GRAPH_URL}/me',
        params={
            'fields': 'user_id,username,name,profile_picture_url,followers_count,media_count',
            'access_token': token,
        },
        timeout=30,
    ), 'dados_da_conta')
    # `user_id` é o ID da conta profissional — o mesmo que chega nos webhooks.
    ig_id = str(info.get('user_id') or curto.get('user_id') or '')
    if not ig_id:
        raise LoginFalhou('dados_da_conta')

    conta, _ = InstagramAccount.objects.update_or_create(
        instagram_business_id=ig_id,
        defaults={
            'user': user,
            'platform': 'instagram',
            'username': info.get('username') or ig_id,
            'access_token': token,
            'token_expires_at': timezone.now() + timedelta(seconds=int(longo.get('expires_in') or 0)),
            'facebook_page_id': None,
            'page_access_token': '',
            'followers_count': info.get('followers_count') or 0,
            'media_count': info.get('media_count') or 0,
            'profile_picture_url': info.get('profile_picture_url') or '',
            'is_active': True,
        },
    )

    # Sem assinar, a Meta não avisa de direct nem de comentário. Falha aqui não
    # desfaz a conexão: fica registrada e pode ser refeita reconectando.
    try:
        _json(requests.post(
            f'{settings.INSTAGRAM_GRAPH_URL}/me/subscribed_apps',
            params={'subscribed_fields': ','.join(WEBHOOKS), 'access_token': token},
            timeout=30,
        ), 'assinatura_dos_avisos')
    except LoginFalhou:
        logger.error('Instagram @%s conectado sem assinar os avisos', conta.username)

    return conta


def volta_ao_painel(erro: str = '') -> str:
    base = f"{settings.PAINEL_URL.rstrip('/')}/instagram/callback"
    return f'{base}?ig_error={erro}' if erro else f'{base}?ig_connected=1'
