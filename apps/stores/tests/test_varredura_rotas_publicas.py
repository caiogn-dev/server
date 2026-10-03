"""
Varredura: nenhuma rota pública de leitura devolve segredo da loja.

Em 2 dias saíram dois vazamentos com a mesma causa — rota AllowAny
reaproveitando o que é do painel: o token fiscal da Focus (02/10) e o preço
de custo (03/10). Corrigir rota a rota não fecha a porta: a próxima rota
pública nasce aberta de novo.

Este teste DESCOBRE as rotas sozinho (pelo roteador do Django), sem lista
manual: toda view com AllowAny que aceite GET é chamada com uma loja semeada
de valores-sentinela nos campos secretos. Se um sentinela aparecer em
qualquer resposta, em qualquer profundidade, o teste falha e diz onde.
Rota pública nova já nasce coberta.
"""
import re
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.permissions import AllowAny
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreCategory, StoreProduct
from apps.stores.models.payment import StorePaymentGateway

# Valores que só existem nos campos secretos. Achar qualquer um deles numa
# resposta pública é vazamento — não importa o nome da chave.
SENTINELAS = {
    'custo do produto': '987654.32',
    'token do Meta CAPI': 'SENTINELA-CAPI-TOKEN',
    'token fiscal no metadata': 'SENTINELA-FOCUS-TOKEN',
    'segredo genérico no metadata': 'SENTINELA-METADATA-SECRET',
    'access token do gateway': 'SENTINELA-GW-ACCESS',
    'api secret do gateway': 'SENTINELA-GW-SECRET',
    'webhook secret do gateway': 'SENTINELA-GW-WEBHOOK',
    'refresh token do gateway': 'SENTINELA-GW-REFRESH',
    'configuração do gateway': 'SENTINELA-GW-CONFIG',
    'e-mail do dono': 'sentinela-dono@exemplo.com.br',
}

# kwargs de URL que sabemos preencher com a loja semeada.
SLUG_KWARGS = {'store_slug', 'slug'}


def _rotas(resolver=None, prefixo=''):
    resolver = resolver or get_resolver()
    for p in resolver.url_patterns:
        if isinstance(p, URLResolver):
            yield from _rotas(p, prefixo + str(p.pattern))
        elif isinstance(p, URLPattern):
            yield prefixo + str(p.pattern), p


def _view_publica_com_get(callback):
    cls = getattr(callback, 'view_class', None) or getattr(callback, 'cls', None)
    if cls is None:
        return False
    perms = getattr(cls, 'permission_classes', None) or []
    if not any(p is AllowAny for p in perms):
        return False
    acoes = getattr(callback, 'actions', None)
    if acoes is not None:
        return 'get' in acoes
    return hasattr(cls, 'get')


def _montar_url(padrao, slug, pid):
    """Preenche os kwargs conhecidos. Devolve None se houver kwarg que não sabemos."""
    url = padrao
    for nome in re.findall(r'<(?:\w+:)?(\w+)>', padrao):
        if nome in SLUG_KWARGS:
            valor = slug
        elif nome in {'pk', 'id', 'product_id'}:
            valor = pid
        else:
            return None
        url = re.sub(rf'<(?:\w+:)?{nome}>', valor, url)
    if '(?P<' in url or '^' in url or '$' in url:
        return None
    return '/' + url.lstrip('/')


@pytest.fixture
def loja_com_segredos(db):
    dono = get_user_model().objects.create_user(
        username='dono-sentinela', email=SENTINELAS['e-mail do dono'], password='pw',
    )
    loja = Store.objects.create(
        name='Loja Sentinela', slug='loja-sentinela', owner=dono, status='active',
        meta_capi_access_token=SENTINELAS['token do Meta CAPI'],
        metadata={
            'focus_token': SENTINELAS['token fiscal no metadata'],
            'fiscal': {'token': SENTINELAS['token fiscal no metadata']},
            'integracao_secreta': SENTINELAS['segredo genérico no metadata'],
            'city': 'Palmas',
        },
    )
    cat = StoreCategory.objects.create(store=loja, name='Pratos', slug='pratos', is_active=True)
    produto = StoreProduct.objects.create(
        store=loja, category=cat, name='Prato', slug='prato', price=Decimal('23.00'),
        cost_price=Decimal(SENTINELAS['custo do produto']), featured=True,
        track_stock=False, status='active',
    )
    StorePaymentGateway.objects.create(
        store=loja, name='MP', gateway_type=StorePaymentGateway.GatewayType.MERCADOPAGO,
        is_enabled=True, is_default=True,
        access_token=SENTINELAS['access token do gateway'],
        api_secret=SENTINELAS['api secret do gateway'],
        webhook_secret=SENTINELAS['webhook secret do gateway'],
        refresh_token=SENTINELAS['refresh token do gateway'],
        configuration={'merchant_key': SENTINELAS['configuração do gateway']},
    )
    return loja, produto


@pytest.mark.django_db
def test_nenhuma_rota_publica_devolve_segredo(loja_com_segredos, monkeypatch):
    loja, produto = loja_com_segredos

    # Nada de rede de verdade durante a varredura (geocoder, gateways...).
    import requests

    def _sem_rede(self, method, url, *a, **k):
        raise requests.ConnectionError(f'varredura sem rede: {url}')
    monkeypatch.setattr(requests.Session, 'request', _sem_rede)

    client = APIClient()
    vazamentos, chamadas = [], 0
    for padrao, pattern in _rotas():
        if not _view_publica_com_get(pattern.callback):
            continue
        url = _montar_url(padrao, loja.slug, str(produto.id))
        if not url:
            continue
        try:
            resp = client.get(url)
        except Exception:  # rota que exige parâmetro/serviço externo: não é o alvo aqui
            continue
        chamadas += 1
        corpo = resp.content.decode('utf-8', 'replace')
        for nome, valor in SENTINELAS.items():
            if valor in corpo:
                vazamentos.append(f'{url} [{resp.status_code}] vaza {nome}')

    # A varredura precisa ter varrido de verdade — senão passa por não olhar nada.
    assert chamadas >= 40, f'só {chamadas} rotas públicas chamadas; a descoberta quebrou'
    assert not vazamentos, 'Rotas públicas vazando segredo:\n' + '\n'.join(sorted(set(vazamentos)))
