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


def credenciais_reais(app: str) -> tuple[str, str]:
    """A credencial do app de verdade, ignorando o modo homologação."""
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

    _barrar_loja_fora_do_app_de_teste(app, caminho)
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


_MERCHANT_NO_CAMINHO = re.compile(r'/merchants/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})')
LOJAS_DE_TESTE_TTL_S = 600


def merchants_autorizados(app: str = 'pedidos'):
    """Lojas que o app tem autorizadas, em minúsculas. None quando não dá para saber.

    O token traz `merchant_scope` só enquanto a lista é curta: com a rede inteira
    autorizada (8 lojas, 26/11) ele vem `type: compact`, sem lista — aí pergunta
    ao iFood (GET /merchants devolve só as autorizadas) e guarda 10 min.
    """
    import base64
    import json
    try:
        corpo = token(app).split('.')[1]
        dados = json.loads(base64.urlsafe_b64decode(corpo + '=' * (-len(corpo) % 4)))
    except Exception:  # noqa: BLE001 — sem token legível, sem filtro
        return None
    escopo = dados.get('merchant_scope') if isinstance(dados, dict) else None
    if isinstance(escopo, list) and escopo:
        return {str(m).split(':')[0].lower() for m in escopo if m}
    chave = f'ifood:autorizadas:{credenciais(app)[0]}'
    guardado = cache.get(chave)
    if guardado is not None:
        return set(guardado)
    try:
        lista = api(app, 'GET', '/merchant/v1.0/merchants', params={'page': 1, 'size': 100}) or []
    except Exception:  # noqa: BLE001
        return None
    ids = {str(m.get('id') or '').lower() for m in lista if isinstance(m, dict) and m.get('id')}
    cache.set(chave, sorted(ids), timeout=600)
    return ids


def em_homologacao() -> bool:
    return bool(getattr(settings, 'IFOOD_HOMOLOGACAO_CLIENT_ID', '')
                and getattr(settings, 'IFOOD_HOMOLOGACAO_CLIENT_SECRET', ''))


def _lojas_do_app_de_teste(app: str) -> set:
    chave = f'ifood:lojas_do_app:{credenciais(app)[0]}'
    guardado = cache.get(chave)
    if guardado is not None:
        return set(guardado)
    dados = api(app, 'GET', '/merchant/v1.0/merchants', params={'page': 1, 'size': 100}) or []
    ids = {str(m.get('id') or '').lower() for m in dados if isinstance(m, dict) and m.get('id')}
    cache.set(chave, sorted(ids), timeout=LOJAS_DE_TESTE_TTL_S)
    return ids


def merchants_do_app(app: str, ids) -> list:
    """Homologação: só as lojas que o app de teste enxerga (polling com uma loja
    a mais leva 403 no lote inteiro). Fora dela, todas."""
    ids = [str(i) for i in ids if i]
    if not em_homologacao():
        # Fora da homologação vale o mesmo: UMA loja sem autorização (ex.: a
        # de TESTE que continuou conectada) derruba o lote inteiro com 403
        # "Some polling merchants are not authorized" — medido 25/11 00:36 a
        # 26/11 10:35, 4054 pollings perdidos. Sem saber quais, manda todas.
        autorizadas = merchants_autorizados(app)
        return ids if autorizadas is None else [i for i in ids if i.lower() in autorizadas]
    try:
        visiveis = _lojas_do_app_de_teste(app)
    except (IfoodRecusou, IfoodNaoConfigurado):
        return []
    return [i for i in ids if i.lower() in visiveis]


def _barrar_loja_fora_do_app_de_teste(app: str, caminho: str):
    """Homologação: o app de teste só enxerga a loja de teste. Chamada para
    outra loja voltaria 403 e sujaria o log que o iFood confere nos vídeos —
    então nem sai daqui (medido 23/11: status da Cê Saladas a cada minuto)."""
    if not em_homologacao():
        return
    achado = _MERCHANT_NO_CAMINHO.search(caminho or '')
    if not achado:
        return
    if achado.group(1).lower() not in _lojas_do_app_de_teste(app):
        raise IfoodRecusou('403: loja fora do app de teste (homologação)', 403, '')


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


def _merchant_fora_do_app(erro) -> bool:
    """403 "User is forbidden": o app não tem o módulo Merchant liberado (ainda
    em homologação), mas a loja pode ter autorizado o app para pedidos."""
    return getattr(erro, 'status', None) == 403 and 'forbidden to access' in str(erro).lower()


def _autorizada_no_polling(app: str, merchant_id: str) -> bool:
    """Polling com só esta loja: 403 "not authorized" = loja não aprovou o app.
    Evento que vier aqui fica sem ACK e volta no polling normal."""
    try:
        api(app, 'GET', '/events/v1.0/events:polling', cabecalhos={'x-polling-merchants': merchant_id})
    except (IfoodRecusou, IfoodNaoConfigurado):
        return False
    return True


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
        if _merchant_fora_do_app(erro) and _autorizada_no_polling(app, integracao.merchant_id):
            integracao.conectado = True
            integracao.ultimo_erro = ''
            integracao.save(update_fields=['conectado', 'ultimo_erro', 'updated_at'])
            return integracao
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
