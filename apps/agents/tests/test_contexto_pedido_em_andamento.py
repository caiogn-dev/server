"""O bot tem que saber que a cliente JÁ fez o pedido.

19/10/2026, Maria Vitória (Mavi): pediu pelo site (CE-2610194335, retirada,
em preparo) e mandou "oii" no WhatsApp. O bot respondeu "O que você gostaria
de pedir hoje?". Depois "posso ir retirar?" → "Quer montar seu pedido?". Depois
"eu já pedi" → "Qual foi o pedido — foi hoje ou outro dia?".

O pedido ESTAVA no contexto — misturado com o histórico, sob a ordem "use
apenas como histórico, nunca trate pedido antigo como pedido atual". A IA
obedeceu. E o pedido de retirada aparecia com "endereço: Q. 112 Sul" (o da
loja), como se fosse entrega.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.agents.services.langchain_service import LangchainService
from apps.stores.models import Store, StoreOrder

ENDERECO_DA_LOJA = {'street': 'Q. 112 Sul, Rua Sr 01', 'number': '2', 'city': 'Palmas'}


@pytest.fixture
def loja(db):
    dono = get_user_model().objects.create_user(username='dono-ctx-andamento', password='x')
    return Store.objects.create(owner=dono, name='Cê Saladas', slug='loja-ctx-andamento')


def _pedido(loja, **extra):
    dados = dict(
        store=loja, total=Decimal('76.43'), subtotal=Decimal('76.43'),
        status='preparing', payment_status='pending', payment_method='cash',
        customer_name='Maria Vitória Matsubara', customer_phone='5563981039494',
        delivery_method='pickup', delivery_address=ENDERECO_DA_LOJA,
    )
    dados.update(extra)
    return StoreOrder.objects.create(**dados)


def _contexto(loja, telefone='556381039494'):
    svc = LangchainService.__new__(LangchainService)
    return svc._build_customer_context(phone_number=telefone, store=loja)


@pytest.mark.django_db
def test_pedido_de_hoje_em_preparo_vira_pedido_em_andamento(loja):
    pedido = _pedido(loja)
    ctx = _contexto(loja)  # WhatsApp sem o nono dígito, pedido com

    assert 'PEDIDO EM ANDAMENTO' in ctx
    bloco = ctx.split('PEDIDO EM ANDAMENTO', 1)[1]
    assert f'#{pedido.order_number}' in bloco
    assert 'retirada' in bloco.lower()
    assert 'em preparo' in bloco.lower()
    # A ordem tem que mandar FALAR do pedido, não ignorá-lo.
    assert 'não pergunte o que' in bloco.lower()


@pytest.mark.django_db
def test_retirada_nao_mostra_endereco_da_loja_como_se_fosse_entrega(loja):
    _pedido(loja)
    ctx = _contexto(loja)

    assert 'Q. 112 Sul' not in ctx


@pytest.mark.django_db
def test_pedido_entregue_ou_antigo_nao_e_pedido_em_andamento(loja):
    _pedido(loja, status='delivered', payment_status='paid')
    velho = _pedido(loja, status='pending')
    StoreOrder.objects.filter(pk=velho.pk).update(created_at=timezone.now() - timedelta(days=3))

    ctx = _contexto(loja)

    assert ctx  # o histórico continua lá
    assert 'PEDIDO EM ANDAMENTO' not in ctx


@pytest.mark.django_db
def test_cancelado_nao_e_pedido_em_andamento(loja):
    _pedido(loja, status='cancelled', payment_status='cancelled')
    assert 'PEDIDO EM ANDAMENTO' not in _contexto(loja)


@pytest.mark.django_db
def test_entrega_em_andamento_diz_entrega_e_o_endereco_do_cliente(loja):
    _pedido(
        loja, delivery_method='delivery', status='out_for_delivery',
        delivery_address={'street': 'Quadra 110 Norte Alameda 8', 'number': '29', 'city': 'Palmas'},
    )
    bloco = _contexto(loja).split('PEDIDO EM ANDAMENTO', 1)[1]

    assert 'entrega' in bloco.lower()
    assert 'saiu para entrega' in bloco.lower()
    assert 'Quadra 110 Norte Alameda 8' in bloco
