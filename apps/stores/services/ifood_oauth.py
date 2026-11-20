"""Autenticação do iFood: apps CENTRALIZADOS, uma credencial para todas as lojas.

Desde 19/11/2026. Antes era o modelo distribuído (cada lojista gerava um
userCode e colava o código de autorização no painel). Trocado porque webhook
de eventos só existe para app centralizado e o centralizado é o desenho do
iFood para sistema na nuvem que atende muitas lojas.

    token        `client_credentials` em POST /authentication/v1.0/oauth/token.
                 Sem refreshToken: renovar é pedir de novo. Vale ~6 h e cobre
                 TODAS as lojas que autorizaram o app.
    loja         informa o `merchant_id` (UUID) e aprova o app no Portal do
                 Parceiro. Sem a aprovação o iFood responde 403.

Dois apps, credenciais separadas (o iFood só libera a de Order depois da
homologação):

    pedidos   IFOOD_CLIENT_ID / IFOOD_CLIENT_SECRET            Order, Events
    entregas  IFOOD_ENTREGAS_CLIENT_ID / _CLIENT_SECRET        Shipping, Events

`api()` é a porta única de chamada: põe o token, e num 401 esquece o token e
tenta UMA vez com outro — token vencido no meio de um pedido entrando é o pior
momento para falhar.
"""
from __future__ import annotations

import logging
import re

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

BASE = 'https://merchant-api.ifood.com.br'
URL_TOKEN = f'{BASE}/authentication/v1.0/oauth/token'
TIMEOUT = 10

#: Critério de homologação: renovar o token SÓ quando expira, nunca antes.
#: O cache dura o expiresIn; token vencido no meio do caminho é tratado pelo
#: retry de 401 em `api()`.
FOLGA_S = 0

_CREDENCIAIS = {
    'pedidos': ('IFOOD_CLIENT_ID', 'IFOOD_CLIENT_SECRET'),
    'entregas': ('IFOOD_ENTREGAS_CLIENT_ID', 'IFOOD_ENTREGAS_CLIENT_SECRET'),
}

_UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


class IfoodNaoConfigurado(Exception):
    """Falta clientId/clientSecret do app na plataforma."""


class IfoodRecusou(Exception):
    """O iFood respondeu com erro. Carrega status e corpo para quem trata."""

    def __init__(self, mensagem: str, status: int | None = None, corpo: str = ''):
        super().__init__(mensagem)
        self.status = status
        self.corpo = corpo


# ── credencial e token ───────────────────────────────────────────────────

def credenciais(app: str) -> tuple[str, str]:
    # Modo homologação (Merchant/Shipping por vídeo): o iFood exige o app de
    # TESTE nas gravações. Com as duas variáveis no .env, todo app usa ela.
    # Tirar do .env quando a homologação for aprovada.
    teste_id = getattr(settings, 'IFOOD_HOMOLOGACAO_CLIENT_ID', '') or ''
    teste_segredo = getattr(settings, 'IFOOD_HOMOLOGACAO_CLIENT_SECRET', '') or ''
    if teste_id and teste_segredo:
        return teste_id, teste_segredo
    chave_id, chave_segredo = _CREDENCIAIS[app]
    return getattr(settings, chave_id, '') or '', getattr(settings, chave_segredo, '') or ''


def esta_configurado(app: str = 'pedidos') -> bool:
    return all(credenciais(app))


def _chave_cache(app: str) -> str:
    return f'ifood:token:{app}:{credenciais(app)[0]}'


def _post(url: str, dados: dict) -> dict:
    """A chamada crua do token. Isolada para o teste substituir sem rede."""
    import requests

    resposta = requests.post(
        url, data=dados,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        timeout=20,
    )
    if resposta.status_code >= 400:
        raise IfoodRecusou(f'{resposta.status_code}: {resposta.text[:300]}', resposta.status_code, resposta.text)
    return resposta.json()


def token(app: str = 'pedidos') -> str:
    """Token bom para usar agora. Levanta se o app não está configurado ou o iFood recusa."""
    client_id, segredo = credenciais(app)
    if not (client_id and segredo):
        raise IfoodNaoConfigurado(f'App "{app}" do iFood sem credencial na plataforma.')
    chave = _chave_cache(app)
    guardado = cache.get(chave)
    if guardado:
        return guardado
    dados = _post(URL_TOKEN, {
        'grantType': 'client_credentials', 'clientId': client_id, 'clientSecret': segredo,
    })
    novo = dados.get('accessToken') or ''
    if not novo:
        raise IfoodRecusou('iFood não devolveu token.')
    validade = int(dados.get('expiresIn') or 21600)
    cache.set(chave, novo, timeout=max(60, validade - FOLGA_S))
    return novo


def esquecer_token(app: str):
    cache.delete(_chave_cache(app))


#: 429/5xx: até 3 tentativas, esperando no máximo 5 s por vez (roda em task).
TENTATIVAS = 3
ESPERA_MAX_S = 5


def api(app: str, metodo: str, caminho: str, corpo=None, cabecalhos=None, params=None, timeout=TIMEOUT):
    """Chamada autenticada. JSON da resposta (inclusive 202 com corpo), ou None sem corpo.

    401 → esquece o token e tenta uma vez. Outros ≥400 → `IfoodRecusou`.
    """
    import requests
    from requests import RequestException

    import time

    renovou = False
    for tentativa in range(1, TENTATIVAS + 1):
        headers = {'Authorization': f'Bearer {token(app)}', **(cabecalhos or {})}
        try:
            resposta = requests.request(
                metodo, f'{BASE}{caminho}', json=corpo, params=params, headers=headers, timeout=timeout,
            )
        except RequestException as exc:
            raise IfoodRecusou(f'iFood fora do ar: {exc}') from exc
        if resposta.status_code == 401 and not renovou:
            renovou = True
            esquecer_token(app)
            continue
        # 429 (respeita Retry-After) e 5xx: backoff exponencial curto.
        if (resposta.status_code == 429 or resposta.status_code >= 500) and tentativa < TENTATIVAS:
            espera = _espera(resposta, tentativa)
            if espera is not None:
                time.sleep(espera)
                continue
        if resposta.status_code >= 400:
            raise IfoodRecusou(
                f'{resposta.status_code}: {resposta.text[:300]}', resposta.status_code, resposta.text,
            )
        # 202 pode trazer corpo: o Shipping devolve {id, trackingUrl} no POST /orders.
        if resposta.status_code == 204 or not resposta.content:
            return None
        try:
            return resposta.json()
        except ValueError:
            return None
    return None  # pragma: no cover — o laço sempre retorna ou levanta


def _espera(resposta, tentativa: int):
    """Segundos até a próxima tentativa; None = não vale esperar (desiste já)."""
    try:
        pedido = float(resposta.headers.get('Retry-After') or 0)
    except (TypeError, ValueError):
        pedido = 0
    espera = pedido or (0.5 * 2 ** (tentativa - 1))
    return espera if espera <= ESPERA_MAX_S else None


# ── eventos: deduplicação pelo id ────────────────────────────────────────

#: Um evento cujo ACK se perdeu volta no próximo polling; o id dele fica
#: lembrado por 1 dia para não ser aplicado duas vezes (recebe ACK de novo).
EVENTO_TTL_S = 60 * 60 * 24


def evento_ja_visto(evento_id) -> bool:
    return bool(evento_id) and cache.get(f'ifood:evento:{evento_id}') is not None


def lembrar_evento(evento_id):
    if evento_id:
        cache.set(f'ifood:evento:{evento_id}', 1, timeout=EVENTO_TTL_S)


# ── a loja ───────────────────────────────────────────────────────────────

def integracao_da_loja(store):
    from apps.stores.models import StoreIfoodIntegration
    integracao, _ = StoreIfoodIntegration.objects.get_or_create(store=store)
    return integracao


def _app_para_conferir() -> str | None:
    for app in ('pedidos', 'entregas'):
        if esta_configurado(app):
            return app
    return None


def verificar(store):
    """Pergunta ao iFood se a loja autorizou o app. Atualiza `conectado`/nome/erro."""
    integracao = integracao_da_loja(store)
    app = _app_para_conferir()
    if not integracao.merchant_id or app is None:
        integracao.conectado = False
        integracao.save(update_fields=['conectado', 'updated_at'])
        return integracao
    try:
        dados = api(app, 'GET', f'/merchant/v1.0/merchants/{integracao.merchant_id}') or {}
    except (IfoodRecusou, IfoodNaoConfigurado) as erro:
        integracao.conectado = False
        status = getattr(erro, 'status', None)
        if status in (401, 403, 404) or 'permission' in str(erro).lower():
            integracao.ultimo_erro = 'Aprove o app Cardapidex no Portal do Parceiro do iFood.'
        else:
            integracao.ultimo_erro = str(erro)[:500]
        integracao.save(update_fields=['conectado', 'ultimo_erro', 'updated_at'])
        return integracao
    integracao.conectado = True
    integracao.merchant_name = str(dados.get('name') or integracao.merchant_name or '')[:255]
    integracao.ultimo_erro = ''
    integracao.save(update_fields=['conectado', 'merchant_name', 'ultimo_erro', 'updated_at'])
    return integracao


def vincular(store, merchant_id: str):
    """Guarda o ID da loja no iFood e confere se o app já foi aprovado."""
    merchant_id = (merchant_id or '').strip().lower()
    if not _UUID.match(merchant_id):
        raise ValueError('ID da loja no iFood inválido (formato UUID).')
    integracao = integracao_da_loja(store)
    if integracao.merchant_id != merchant_id:
        integracao.merchant_id = merchant_id
        integracao.merchant_name = ''
        integracao.save(update_fields=['merchant_id', 'merchant_name', 'updated_at'])
    return verificar(store)


def token_valido(store):
    """Token do app de PEDIDOS para esta loja, ou None (loja sem ID / app sem credencial)."""
    integracao = integracao_da_loja(store)
    if not integracao.merchant_id or not esta_configurado('pedidos'):
        return None
    try:
        return token('pedidos')
    except (IfoodRecusou, IfoodNaoConfigurado) as erro:
        logger.warning('iFood: token de pedidos recusado (%s): %s', store.slug, erro)
        return None


def desconectar(store):
    """Esquece a loja e desliga as entregas. O lojista revoga no portal se quiser."""
    integracao = integracao_da_loja(store)
    integracao.merchant_id = ''
    integracao.merchant_name = ''
    integracao.conectado = False
    integracao.ultimo_erro = ''
    integracao.frete_pelo_ifood = False
    integracao.chamar_entregador = integracao.ChamarEntregador.MANUAL
    integracao.save()
    return integracao
