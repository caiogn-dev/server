"""Conexão OAuth da conta Mercado Pago do lojista — pronta, desligada.

POR QUE ISTO EXISTE DESLIGADO

Sem gateway próprio, o dinheiro do cliente final cai na conta da PLATAFORMA.
Isso é aceitável nas lojas do próprio dono (allowlist
`PLATFORM_GATEWAY_STORE_SLUGS`) e inaceitável num cliente pagante: seria
intermediação de pagamento de terceiro sem contrato, e tornaria falsa a frase
"o PIX cai direto na sua conta" do material de venda.

O caminho que resolve HOJE é o token manual: o lojista cola o access_token dele
e pronto — não depende de aprovação de ninguém. O OAuth (modelo marketplace do
Mercado Pago) é melhor de usar, mas exige app registrado, redirect URI aprovada
e renovação de token.

Este módulo deixa o OAuth plugável: no dia em que o app existir, preencher
MP_OAUTH_CLIENT_ID e MP_OAUTH_CLIENT_SECRET liga o fluxo sem migração nova e
sem tocar no checkout. Enquanto estiverem vazios, `esta_configurado()` é False
e qualquer tentativa levanta OAuthNaoConfigurado em vez de falhar torto.
"""
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.stores.models import StorePaymentGateway

logger = logging.getLogger(__name__)

AUTORIZACAO_URL = 'https://auth.mercadopago.com.br/authorization'
TOKEN_URL = 'https://api.mercadopago.com/oauth/token'

# O lojista sai do painel, loga no Mercado Pago e volta. Dez minutos cobrem isso
# com folga e mantêm curta a janela em que um state vazado ainda vale.
STATE_TTL_SEGUNDOS = 600
PREFIXO_STATE = 'mp_oauth_state:'


class OAuthNaoConfigurado(Exception):
    """App do Mercado Pago ainda não registrado — fluxo indisponível."""


def esta_configurado() -> bool:
    return bool(
        getattr(settings, 'MP_OAUTH_CLIENT_ID', '')
        and getattr(settings, 'MP_OAUTH_CLIENT_SECRET', '')
    )


def _exigir_configuracao():
    if not esta_configurado():
        raise OAuthNaoConfigurado(
            'OAuth do Mercado Pago não configurado. Registre o app e preencha '
            'MP_OAUTH_CLIENT_ID e MP_OAUTH_CLIENT_SECRET. Enquanto isso, use o '
            'token manual.'
        )


def criar_state(store) -> str:
    """Nonce de uso único que amarra o callback à loja que iniciou a conexão.

    O callback do Mercado Pago não diz de quem é o código — só devolve o
    `state`. A primeira versão disto era `loja:<slug>`, e slug é público: dava
    para montar a URL de autorização com o slug de OUTRA loja e induzir o
    lojista a plugar a conta dele lá (a conta certa, na loja errada). Um valor
    aleatório guardado do nosso lado fecha isso, e ser de uso único também mata
    replay do callback.
    """
    state = secrets.token_urlsafe(32)
    cache.set(f'{PREFIXO_STATE}{state}', store.slug, STATE_TTL_SEGUNDOS)
    return state


def consumir_state(state: str) -> str:
    """Resolve o slug e QUEIMA o state. Devolve '' se inválido ou já usado."""
    if not state:
        return ''
    chave = f'{PREFIXO_STATE}{state}'
    slug = cache.get(chave) or ''
    if slug:
        cache.delete(chave)
    return slug


def url_de_autorizacao(store) -> str:
    """URL para onde o lojista é enviado ao clicar em "Conectar"."""
    _exigir_configuracao()
    params = {
        'client_id': settings.MP_OAUTH_CLIENT_ID,
        'response_type': 'code',
        'platform_id': 'mp',
        'state': criar_state(store),
        'redirect_uri': getattr(settings, 'MP_OAUTH_REDIRECT_URI', ''),
    }
    return f'{AUTORIZACAO_URL}?{urlencode(params)}'


def trocar_codigo_por_token(codigo: str) -> dict:
    """Troca o `code` do callback pelo access_token do lojista."""
    _exigir_configuracao()
    resposta = requests.post(
        TOKEN_URL,
        json={
            'client_id': settings.MP_OAUTH_CLIENT_ID,
            'client_secret': settings.MP_OAUTH_CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': codigo,
            'redirect_uri': getattr(settings, 'MP_OAUTH_REDIRECT_URI', ''),
        },
        timeout=20,
    )
    resposta.raise_for_status()
    return resposta.json()


def renovar(gateway: StorePaymentGateway) -> StorePaymentGateway:
    """Renova o access_token usando o refresh_token guardado."""
    _exigir_configuracao()
    if not gateway.refresh_token:
        raise OAuthNaoConfigurado('Gateway sem refresh_token — reconecte a loja.')
    resposta = requests.post(
        TOKEN_URL,
        json={
            'client_id': settings.MP_OAUTH_CLIENT_ID,
            'client_secret': settings.MP_OAUTH_CLIENT_SECRET,
            'grant_type': 'refresh_token',
            'refresh_token': gateway.refresh_token,
        },
        timeout=20,
    )
    resposta.raise_for_status()
    return salvar_conexao(gateway.store, resposta.json())


def salvar_conexao(store, dados: dict) -> StorePaymentGateway:
    """Grava (ou atualiza) o gateway da loja a partir da resposta do provedor.

    `update_or_create` e não `create`: a constraint do model só permite um
    gateway Mercado Pago habilitado por loja, e reconectar é operação normal
    (token trocado, conta trocada).
    """
    expira_em = dados.get('expires_in')
    gateway, _ = StorePaymentGateway.objects.update_or_create(
        store=store,
        gateway_type=StorePaymentGateway.GatewayType.MERCADOPAGO,
        defaults={
            'name': 'Mercado Pago',
            'connection_type': StorePaymentGateway.ConnectionType.OAUTH,
            'access_token': dados.get('access_token', ''),
            'refresh_token': dados.get('refresh_token', ''),
            'public_key': dados.get('public_key', ''),
            'external_account_id': str(dados.get('user_id', '') or ''),
            'token_expires_at': (
                timezone.now() + timedelta(seconds=int(expira_em)) if expira_em else None
            ),
            'is_enabled': True,
            'is_sandbox': False,
        },
    )
    logger.info(
        '[MP OAuth] Loja %s conectada (conta %s)',
        store.slug, gateway.external_account_id,
    )
    return gateway
