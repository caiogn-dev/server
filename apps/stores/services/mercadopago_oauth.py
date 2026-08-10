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
from datetime import timedelta
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.utils import timezone

from apps.stores.models import StorePaymentGateway

logger = logging.getLogger(__name__)

AUTORIZACAO_URL = 'https://auth.mercadopago.com.br/authorization'
TOKEN_URL = 'https://api.mercadopago.com/oauth/token'


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


def url_de_autorizacao(store) -> str:
    """URL para onde o lojista é enviado ao clicar em "Conectar".

    O `state` carrega o slug da loja porque o callback do Mercado Pago não diz
    de quem é o código — sem isso, o token voltaria órfão.
    """
    _exigir_configuracao()
    params = {
        'client_id': settings.MP_OAUTH_CLIENT_ID,
        'response_type': 'code',
        'platform_id': 'mp',
        'state': f'loja:{store.slug}',
        'redirect_uri': getattr(settings, 'MP_OAUTH_REDIRECT_URI', ''),
    }
    return f'{AUTORIZACAO_URL}?{urlencode(params)}'


def loja_do_state(state: str) -> str:
    """Extrai o slug do state devolvido pelo provedor."""
    if not state or not state.startswith('loja:'):
        return ''
    return state.split('loja:', 1)[1].strip()


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
