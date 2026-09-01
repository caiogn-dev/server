"""
Token de OAuth vence. Sem quem renove, a loja para de vender e ninguém percebe.

O `renovar()` existe desde 10/ago e NUNCA foi chamado por nada — `grep renovar`
não achava um único caller. O access token do Mercado Pago dura ~6 meses: a
falha chegaria meio ano depois de conectar, longe de qualquer deploy, e o
sintoma seria "o PIX parou" sem nada no código ter mudado.

Renovar cedo (7 dias antes) e não no vencimento é de propósito: dá margem para
a task falhar alguns dias — MP fora do ar, Celery parado, deploy demorado —
sem que o lojista sinta.
"""
from datetime import timedelta

import pytest
import requests
from django.utils import timezone

from apps.stores.models import StorePaymentGateway
from apps.stores.tasks import renovar_tokens_oauth_do_mercadopago
from apps.stores.tests.factories import make_store


def _gateway(loja, **campos):
    padroes = dict(
        name='Mercado Pago',
        gateway_type=StorePaymentGateway.GatewayType.MERCADOPAGO,
        access_token='APP_USR-antigo',
        refresh_token='TG-refresh',
        connection_type=StorePaymentGateway.ConnectionType.OAUTH,
        is_enabled=True,
    )
    padroes.update(campos)
    return StorePaymentGateway.objects.create(store=loja, **padroes)


@pytest.fixture
def loja(db):
    return make_store()


def test_renova_token_que_vence_em_menos_de_sete_dias(loja, monkeypatch):
    g = _gateway(loja, token_expires_at=timezone.now() + timedelta(days=3))
    renovados = []
    monkeypatch.setattr(
        'apps.stores.services.mercadopago_oauth.renovar',
        lambda gw: renovados.append(gw.id) or gw,
    )

    renovar_tokens_oauth_do_mercadopago()

    assert renovados == [g.id]


def test_nao_renova_token_com_folga(loja, monkeypatch):
    """Renovar à toa gasta chamada e ainda roda o risco de invalidar o atual."""
    _gateway(loja, token_expires_at=timezone.now() + timedelta(days=90))
    renovados = []
    monkeypatch.setattr(
        'apps.stores.services.mercadopago_oauth.renovar',
        lambda gw: renovados.append(gw.id) or gw,
    )

    renovar_tokens_oauth_do_mercadopago()

    assert renovados == []


def test_ignora_gateway_manual(loja, monkeypatch):
    """Token colado à mão não expira e não tem refresh_token — renovar estoura."""
    _gateway(
        loja,
        connection_type=StorePaymentGateway.ConnectionType.MANUAL,
        refresh_token='',
        token_expires_at=timezone.now() + timedelta(days=1),
    )
    renovados = []
    monkeypatch.setattr(
        'apps.stores.services.mercadopago_oauth.renovar',
        lambda gw: renovados.append(gw.id) or gw,
    )

    renovar_tokens_oauth_do_mercadopago()

    assert renovados == []


def test_ja_vencido_ainda_e_tentado(loja, monkeypatch):
    """O refresh_token sobrevive ao access_token: perder a janela não é fim."""
    g = _gateway(loja, token_expires_at=timezone.now() - timedelta(days=2))
    renovados = []
    monkeypatch.setattr(
        'apps.stores.services.mercadopago_oauth.renovar',
        lambda gw: renovados.append(gw.id) or gw,
    )

    renovar_tokens_oauth_do_mercadopago()

    assert renovados == [g.id]


def test_falha_em_uma_loja_nao_impede_as_outras(db, monkeypatch):
    """Uma loja com refresh revogado não pode derrubar a renovação das demais."""
    a = _gateway(make_store(), token_expires_at=timezone.now() + timedelta(days=1))
    b = _gateway(make_store(), token_expires_at=timezone.now() + timedelta(days=1))
    renovados = []

    def renovar(gw):
        if gw.id == a.id:
            raise requests.HTTPError('invalid_grant')
        renovados.append(gw.id)
        return gw

    monkeypatch.setattr('apps.stores.services.mercadopago_oauth.renovar', renovar)

    resultado = renovar_tokens_oauth_do_mercadopago()

    assert renovados == [b.id]
    assert resultado['falhas'] == 1
    assert resultado['renovados'] == 1


def test_gateway_desabilitado_e_ignorado(loja, monkeypatch):
    _gateway(loja, is_enabled=False, token_expires_at=timezone.now() + timedelta(days=1))
    renovados = []
    monkeypatch.setattr(
        'apps.stores.services.mercadopago_oauth.renovar',
        lambda gw: renovados.append(gw.id) or gw,
    )

    renovar_tokens_oauth_do_mercadopago()

    assert renovados == []
