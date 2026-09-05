"""Autenticação do iFood: um app, muitos restaurantes.

NÃO EXISTE TOKEN ESTÁTICO no iFood. Só OAuth2, e os dois fluxos batem no mesmo
endereço (`POST /authentication/v1.0/oauth/token`, corpo form-urlencoded). O que
muda é o `grantType`:

    centralizado   `client_credentials` — para quem integra as PRÓPRIAS lojas.
                   Sem refreshToken: cada renovação repete a chamada.

    distribuído    `authorization_code` e depois `refresh_token` — para quem
                   integra lojas DE TERCEIROS. O lojista autoriza uma vez com
                   um `userCode` no portal, e o refresh renova sozinho daí em
                   diante.

ESTE MÓDULO IMPLEMENTA O DISTRIBUÍDO, e a razão é o negócio: o Cardapidex é
vendido para donos de restaurante, cada um com o próprio cadastro no iFood.
Centralizado só serviria se todas as lojas fossem da mesma empresa. Começar
centralizado e migrar depois obrigaria a refazer o vínculo com cada cliente,
um a um, pedindo que autorizem de novo.

O TOKEN DURA 6 HORAS. É por isso que `token_valido()` existe e é o ÚNICO jeito
de obter o token: quem chama recebe um token bom ou `None`, e nunca precisa
lembrar de renovar. O OAuth do Mercado Pago neste projeto tinha `renovar()`
escrito e sem nenhum caller — a loja conectava, funcionava, e pararia de vender
meses depois. Aqui a renovação está no caminho de quem usa.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

BASE = 'https://merchant-api.ifood.com.br'
URL_TOKEN = f'{BASE}/authentication/v1.0/oauth/token'
URL_USER_CODE = f'{BASE}/authentication/v1.0/oauth/userCode'

#: Renova com folga. Token que vence no meio de uma sequência de chamadas
#: derruba a operação no pior momento — o pedido entrando.
FOLGA = timedelta(minutes=10)


class IfoodNaoConfigurado(Exception):
    """Falta clientId/clientSecret do aplicativo da plataforma."""


class IfoodRecusou(Exception):
    """O iFood respondeu com erro. Carrega o motivo para a tela mostrar."""


def esta_configurado() -> bool:
    return bool(
        getattr(settings, 'IFOOD_CLIENT_ID', '')
        and getattr(settings, 'IFOOD_CLIENT_SECRET', '')
    )


def _exigir_configuracao():
    if not esta_configurado():
        raise IfoodNaoConfigurado(
            'Aplicativo do iFood sem clientId/clientSecret. '
            'Configure IFOOD_CLIENT_ID e IFOOD_CLIENT_SECRET.'
        )


def _post(url: str, dados: dict) -> dict:
    """A chamada crua. Isolada para o teste substituir sem tocar em rede."""
    import requests

    resposta = requests.post(
        url,
        data=dados,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        timeout=20,
    )
    if resposta.status_code >= 400:
        raise IfoodRecusou(f'{resposta.status_code}: {resposta.text[:300]}')
    return resposta.json()


def integracao_da_loja(store):
    from apps.stores.models import StoreIfoodIntegration
    integracao, _ = StoreIfoodIntegration.objects.get_or_create(store=store)
    return integracao


# ── o vínculo: o lojista autoriza uma vez ───────────────────────────────

def iniciar_vinculo(store) -> dict:
    """Pede o código que o lojista digita no Portal do Parceiro.

    Devolve o código e o endereço. O `authorizationCodeVerifier` fica guardado:
    ele só existe entre pedir o código e trocar pelo token, e perdê-lo obriga o
    lojista a recomeçar — depois de já ter saído da tela.
    """
    _exigir_configuracao()

    dados = _post(URL_USER_CODE, {'clientId': settings.IFOOD_CLIENT_ID})

    integracao = integracao_da_loja(store)
    integracao.user_code = dados.get('userCode', '')
    integracao.authorization_code_verifier = dados.get('authorizationCodeVerifier', '')
    integracao.user_code_expires_at = timezone.now() + timedelta(
        seconds=int(dados.get('expiresIn') or 600),
    )
    integracao.save(update_fields=[
        'user_code', 'authorization_code_verifier', 'user_code_expires_at', 'updated_at',
    ])

    return {
        'user_code': integracao.user_code,
        'url': dados.get('verificationUrl', ''),
        'expira_em': integracao.user_code_expires_at,
    }


def concluir_vinculo(store, authorization_code: str):
    """Troca o código do portal pelos tokens. Só acontece uma vez por loja."""
    _exigir_configuracao()
    integracao = integracao_da_loja(store)

    dados = _post(URL_TOKEN, dados={
        'grantType': 'authorization_code',
        'clientId': settings.IFOOD_CLIENT_ID,
        'clientSecret': settings.IFOOD_CLIENT_SECRET,
        'authorizationCode': (authorization_code or '').strip(),
        'authorizationCodeVerifier': integracao.authorization_code_verifier,
    })
    return _guardar_tokens(integracao, dados)


# ── o uso: quem chama nunca precisa lembrar de renovar ──────────────────

def token_valido(store):
    """O token bom para usar AGORA, renovando se preciso. `None` se não dá.

    Único ponto de saída de propósito: espalhar "se venceu, renove" pelos
    chamadores é como se esquece de renovar em um deles.
    """
    integracao = integracao_da_loja(store)
    if not integracao.conectado or not integracao.refresh_token:
        return None

    vence = integracao.token_expires_at
    if integracao.access_token and vence and vence - FOLGA > timezone.now():
        return integracao.access_token

    try:
        _exigir_configuracao()
        dados = _post(URL_TOKEN, dados={
            'grantType': 'refresh_token',
            'clientId': settings.IFOOD_CLIENT_ID,
            'clientSecret': settings.IFOOD_CLIENT_SECRET,
            'refreshToken': integracao.refresh_token,
        })
    except (IfoodRecusou, IfoodNaoConfigurado) as erro:
        # O lojista pode ter revogado o acesso no portal. A loja precisa SABER:
        # falhar calado aqui é o pedido do iFood parando de entrar sem ninguém
        # perceber, que é o modo de falha mais caro de uma integração de venda.
        integracao.conectado = False
        integracao.ultimo_erro = str(erro)[:500]
        integracao.save(update_fields=['conectado', 'ultimo_erro', 'updated_at'])
        logger.warning('iFood: renovação recusada para %s: %s', store.slug, erro)
        return None

    return _guardar_tokens(integracao, dados).access_token


def _guardar_tokens(integracao, dados: dict):
    integracao.access_token = dados.get('accessToken', '')
    novo_refresh = dados.get('refreshToken', '')
    if novo_refresh:
        # O iFood pode rotacionar o refresh. Guardar o novo é o que impede a
        # próxima renovação de falhar com um token já usado.
        integracao.refresh_token = novo_refresh
    integracao.token_expires_at = timezone.now() + timedelta(
        seconds=int(dados.get('expiresIn') or 21600),
    )
    integracao.conectado = bool(integracao.access_token)
    integracao.ultimo_erro = ''
    integracao.ultima_renovacao = timezone.now()
    integracao.save()
    return integracao
