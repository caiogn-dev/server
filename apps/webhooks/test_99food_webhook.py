"""Recebedor de webhooks da 99Food: POST /webhooks/v1/99food/.

Contrato publicado pela 99 (developer-food.99app.com, "Webhooks" e
"Authentication & Signature Mechanism", lido em 03/nov/2026):

- assinatura no header `didi-header-sign` = MD5(corpo bruto + app_secret);
- resposta esperada é JSON `{"errno": 0, "errmsg": "ok"}`; qualquer outra coisa
  e a 99 reenvia "várias vezes";
- timeout de 6 s por aviso;
- IDs de pedido/loja são inteiros de 64 bits.
"""
import hashlib
import json

import pytest
from django.test import override_settings

from apps.webhooks.models import WebhookEvent

URL = '/webhooks/v1/99food/'
SEGREDO = 'segredo-de-teste-99'
PEDIDO_ID_64BITS = 5764607801871631353


def _corpo(tipo='orderNew', **dados):
    return json.dumps({
        'app_id': 5764607801871600001,
        'app_shop_id': 'ce-saladas',
        'type': tipo,
        'timestamp': 1793700000,
        'data': {'order_id': PEDIDO_ID_64BITS, **dados},
    }).encode()


def _assinatura(corpo, segredo=SEGREDO):
    return hashlib.md5(corpo + segredo.encode()).hexdigest()


def _post(client, corpo, assinatura):
    headers = {'HTTP_DIDI_HEADER_SIGN': assinatura} if assinatura is not None else {}
    return client.post(URL, data=corpo, content_type='application/json', **headers)


def _resposta_aceita(resposta):
    assert resposta.status_code == 200, resposta.content
    assert resposta.json() == {'errno': 0, 'errmsg': 'ok'}


@pytest.mark.django_db
@override_settings(NINETY_NINE_APP_SECRET=SEGREDO)
def test_aviso_assinado_e_aceito_e_registrado(client):
    corpo = _corpo()

    _resposta_aceita(_post(client, corpo, _assinatura(corpo)))

    evento = WebhookEvent.objects.get(provider='99food')
    assert evento.event_type == 'orderNew'
    assert evento.signature_valid is True
    # 64 bits sem arredondar: é o ID que vai voltar para a API da 99.
    assert evento.payload['data']['order_id'] == PEDIDO_ID_64BITS


@pytest.mark.django_db
@override_settings(NINETY_NINE_APP_SECRET=SEGREDO)
def test_assinatura_errada_e_recusada_sem_gravar(client):
    corpo = _corpo()

    resposta = _post(client, corpo, _assinatura(corpo, segredo='outro'))

    assert resposta.status_code == 403
    assert not WebhookEvent.objects.filter(provider='99food').exists()


@pytest.mark.django_db
@override_settings(NINETY_NINE_APP_SECRET=SEGREDO)
def test_sem_assinatura_e_recusado(client):
    resposta = _post(client, _corpo(), None)

    assert resposta.status_code == 403
    assert not WebhookEvent.objects.filter(provider='99food').exists()


@pytest.mark.django_db
@override_settings(NINETY_NINE_APP_SECRET='')
def test_sem_segredo_configurado_recusa(client):
    # Fail-closed: pedido da 99 carrega dados do cliente. Sem segredo, qualquer
    # um forjaria pedido ou status de entrega.
    corpo = _corpo()

    resposta = _post(client, corpo, _assinatura(corpo))

    assert resposta.status_code == 403
    assert not WebhookEvent.objects.filter(provider='99food').exists()


@pytest.mark.django_db
@override_settings(NINETY_NINE_APP_SECRET=SEGREDO)
def test_reenvio_do_mesmo_aviso_nao_duplica(client):
    corpo = _corpo()

    _resposta_aceita(_post(client, corpo, _assinatura(corpo)))
    _resposta_aceita(_post(client, corpo, _assinatura(corpo)))

    assert WebhookEvent.objects.filter(provider='99food').count() == 1


@pytest.mark.django_db
@override_settings(NINETY_NINE_APP_SECRET=SEGREDO)
def test_avisos_diferentes_do_mesmo_pedido_sao_dois_eventos(client):
    novo = _corpo('orderNew')
    cancelado = _corpo('orderCancel')

    _resposta_aceita(_post(client, novo, _assinatura(novo)))
    _resposta_aceita(_post(client, cancelado, _assinatura(cancelado)))

    tipos = set(WebhookEvent.objects.filter(provider='99food').values_list('event_type', flat=True))
    assert tipos == {'orderNew', 'orderCancel'}


@pytest.mark.django_db
@override_settings(NINETY_NINE_APP_SECRET=SEGREDO)
def test_tipo_desconhecido_ainda_responde_errno_zero(client):
    # A 99 avisa que pode criar tipos novos. Responder erro faria ela reenviar
    # sem fim um aviso que nunca vamos entender; o evento fica guardado.
    corpo = _corpo('algumTipoNovo2027')

    _resposta_aceita(_post(client, corpo, _assinatura(corpo)))

    assert WebhookEvent.objects.get(provider='99food').event_type == 'algumTipoNovo2027'
