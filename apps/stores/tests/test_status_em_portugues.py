"""`status_display` existe para ser LIDO — então precisa estar em português.

Em 08/ago/2026 o dono viu "Cancelled" e "Delivered" na home do painel. A causa
não estava no frontend: os `TextChoices` do `StoreOrder` têm rótulo em inglês,
e `get_status_display()` devolve exatamente esse rótulo. Toda tela que confia
em `status_display` — home, app Flutter, e-mail de confirmação — mostrava
inglês para o cliente brasileiro.

Traduzir no frontend consertaria uma tela. Traduzir aqui conserta todas, e a
próxima também.

O VALOR não muda: `status` continua sendo `'delivered'`. Só o rótulo de
exibição é traduzido — comparações, filtros da API e integrações continuam
funcionando exatamente igual.
"""
import re

import pytest

from apps.stores.models import StoreOrder, StorePayment

# Palavras que denunciam rótulo não traduzido. Não é lista de tradução: é
# catraca. Rótulo novo em inglês para o teste antes de chegar na tela.
PALAVRAS_EM_INGLES = re.compile(
    r'\b(pending|confirmed|processing|paid|preparing|ready|shipped|delivered|'
    r'completed|cancelled|refunded|failed|partially|pickup|out for|claimed)\b',
    re.IGNORECASE,
)


def _rotulos(choices):
    return [(valor, rotulo) for valor, rotulo in choices]


@pytest.mark.parametrize('valor,rotulo', _rotulos(StoreOrder.OrderStatus.choices))
def test_status_de_pedido_em_portugues(valor, rotulo):
    assert not PALAVRAS_EM_INGLES.search(rotulo), (
        f'O status {valor!r} exibe {rotulo!r} — chega assim na home do painel.'
    )


@pytest.mark.parametrize('valor,rotulo', _rotulos(StoreOrder.PaymentStatus.choices))
def test_status_de_pagamento_em_portugues(valor, rotulo):
    assert not PALAVRAS_EM_INGLES.search(rotulo), (
        f'O pagamento {valor!r} exibe {rotulo!r}.'
    )


@pytest.mark.parametrize('valor,rotulo', _rotulos(StorePayment.PaymentStatus.choices))
def test_status_de_cobranca_em_portugues(valor, rotulo):
    assert not PALAVRAS_EM_INGLES.search(rotulo)


def test_os_valores_nao_mudaram():
    """A tradução é só do rótulo.

    Se o VALOR mudasse, quebrariam de uma vez: filtros da API, o kanban (que
    casa por `status`), os webhooks de pagamento e todo pedido já gravado no
    banco. É a diferença entre uma tradução e uma migração de dados.
    """
    assert StoreOrder.OrderStatus.DELIVERED == 'delivered'
    assert StoreOrder.OrderStatus.CANCELLED == 'cancelled'
    assert StoreOrder.PaymentStatus.PAID == 'paid'
    assert StorePayment.PaymentStatus.COMPLETED == 'completed'


@pytest.mark.django_db
def test_get_status_display_devolve_o_texto_da_tela():
    from apps.stores.models import Store
    from django.contrib.auth import get_user_model

    dono = get_user_model().objects.create_user(username='dono-pt', email='pt@x.com', password='x')
    loja = Store.objects.create(name='Loja PT', slug='loja-pt', owner=dono)
    pedido = StoreOrder.objects.create(
        store=loja, status=StoreOrder.OrderStatus.DELIVERED,
        payment_status=StoreOrder.PaymentStatus.PAID,
        subtotal=10, total=10,
    )
    assert pedido.get_status_display() == 'Entregue'
    assert pedido.get_payment_status_display() == 'Pago'
