"""Saldo e histórico só com o número COMPROVADO pelo código do WhatsApp.

REPRODUZIDO EM 12/SET, só com curl e um número de telefone, sem login:

    cashback/saldo/?phone=…       → saldo R$ 2,00 e data de vencimento
    customer/guest-orders/        → 9 pedidos, cada um com access_token
    orders/by-token/<token>/      → endereço de casa

Telefone não é segredo — está no Instagram, no grupo, no anúncio. Decisão do
dono: histórico E saldo exigem o código. Carimbos seguem abertos (não têm nome,
endereço nem valor).

O saldo não pode nem "vazar existência": dizer "você tem saldo, confirme" para
um telefone qualquer já responde "essa pessoa é cliente desta loja". Por isso o
aviso de bloqueio depende só de QUEM pergunta (comprovou ou não), nunca do banco.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreCashbackLot, StoreOrder
from apps.stores.services.cashback_service import CashbackService

User = get_user_model()
TELEFONE = '5563991386719'


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono-otp', email='d-otp@t.local', password='x')
    return Store.objects.create(
        owner=dono, name='Loja OTP', slug='loja-otp', status='active',
        whatsapp_number='5563999990000',
        metadata={'cashback_enabled': True, 'cashback_percent': '3',
                  'cashback_expiry_days': '30'},
    )


@pytest.fixture
def com_saldo(loja):
    CashbackService._creditar(loja, TELEFONE, Decimal('12.00'),
                              StoreCashbackLot.Origin.PURCHASE)
    return loja


@pytest.fixture
def com_pedidos(loja):
    for _ in range(2):
        StoreOrder.objects.create(
            store=loja, customer_name='Dono Do Número', customer_phone=TELEFONE,
            subtotal=Decimal('30'), total=Decimal('30'),
            delivery_address={'street': 'Rua Secreta', 'number': '42', 'city': 'Palmas'})
    return loja


@pytest.fixture
def anonimo():
    return APIClient()


@pytest.fixture
def comprovado(db):
    """Quem fez o login por código: usuário autenticado com o número no perfil."""
    from apps.core.models import UserProfile
    # Como o OTP cria a conta: sem senha utilizável (ver telefone_comprovado).
    u = User.objects.create_user(username=f'cliente_{TELEFONE}', password=None)
    perfil, _ = UserProfile.objects.get_or_create(user=u)
    perfil.phone = TELEFONE
    perfil.save()
    c = APIClient()
    c.force_authenticate(user=u)
    return c


def _saldo(cliente, loja, phone=TELEFONE):
    return cliente.get(f'/api/v1/stores/{loja.slug}/cashback/saldo/', {'phone': phone})


def _carteira(cliente, loja, phone=TELEFONE):
    return cliente.get(f'/api/v1/stores/{loja.slug}/carteira/', {'phone': phone})


def _historico(cliente, loja, phone=TELEFONE):
    return cliente.post(f'/api/v1/stores/{loja.slug}/customer/guest-orders/',
                        {'phone': phone}, format='json')


# ── saldo ────────────────────────────────────────────────────────────────
def test_anonimo_nao_ve_o_saldo(anonimo, com_saldo):
    r = _saldo(anonimo, com_saldo)
    assert r.status_code == 200
    assert Decimal(str(r.data['saldo'])) == Decimal('0')
    assert r.data['vence_em'] is None


def test_anonimo_nao_descobre_se_o_numero_tem_saldo(anonimo, com_saldo, loja):
    """O aviso de 'confirme' é igual para quem tem e quem não tem saldo."""
    com = _saldo(anonimo, com_saldo).data
    sem = _saldo(anonimo, loja, phone='5563988887777').data
    assert com['saldo_bloqueado'] is True
    assert sem['saldo_bloqueado'] is True
    assert {k: v for k, v in com.items()} == {k: v for k, v in sem.items()}


def test_comprovado_ve_o_proprio_saldo(comprovado, com_saldo):
    r = _saldo(comprovado, com_saldo)
    assert Decimal(str(r.data['saldo'])) == Decimal('12.00')
    assert r.data['vence_em'] is not None
    assert r.data['saldo_bloqueado'] is False


def test_comprovado_NAO_ve_saldo_de_outro_numero(comprovado, loja):
    CashbackService._creditar(loja, '5563977776666', Decimal('50.00'),
                              StoreCashbackLot.Origin.PURCHASE)
    r = _saldo(comprovado, loja, phone='5563977776666')
    assert Decimal(str(r.data['saldo'])) == Decimal('0')


def test_carteira_anonima_nao_mostra_saldo(anonimo, com_saldo):
    r = _carteira(anonimo, com_saldo)
    assert r.status_code == 200
    assert Decimal(str(r.data.get('saldo') or '0')) == Decimal('0')


# ── gastar ───────────────────────────────────────────────────────────────
def test_sem_comprovar_o_checkout_nao_gasta_saldo(com_saldo):
    """Ver e gastar são a mesma porta: digitar o número de alguém não pode
    abater o saldo dele."""
    assert CashbackService.aplicavel(com_saldo, TELEFONE, Decimal('30'),
                                     verificado=False) == Decimal('0.00')


def test_comprovado_gasta_o_proprio_saldo(com_saldo):
    assert CashbackService.aplicavel(com_saldo, TELEFONE, Decimal('30'),
                                     verificado=True) == Decimal('12.00')


def test_ajuste_do_painel_continua_enxergando_tudo(com_saldo):
    """O dono da loja não passa por código: o painel lê com verificado=True."""
    assert CashbackService.balance(com_saldo, TELEFONE, verificado=True) == Decimal('12.00')


# ── histórico ────────────────────────────────────────────────────────────
def test_anonimo_nao_recebe_historico_nem_tokens(anonimo, com_pedidos):
    r = _historico(anonimo, com_pedidos)
    assert r.status_code == 200
    assert r.data['results'] == []
    assert r.data.get('precisa_confirmar') is True
    assert 'access_token' not in str(r.data)


def test_comprovado_recebe_o_proprio_historico(comprovado, com_pedidos):
    r = _historico(comprovado, com_pedidos)
    assert r.status_code == 200
    assert len(r.data['results']) == 2
    assert not r.data.get('precisa_confirmar')


def test_comprovado_nao_puxa_historico_de_outro_numero(comprovado, loja):
    StoreOrder.objects.create(
        store=loja, customer_name='Outra Pessoa', customer_phone='5563977776666',
        subtotal=Decimal('30'), total=Decimal('30'))
    r = _historico(comprovado, loja, phone='5563977776666')
    assert r.data['results'] == []


def test_token_vencido_nao_derruba_o_cardapio(com_pedidos):
    """Token velho no aparelho não pode virar 401 na tela de pedidos (a
    lição do TokenExpirationMiddleware de 02/set)."""
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION='Token token-que-nao-existe')
    r = _historico(c, com_pedidos)
    assert r.status_code == 200
    assert r.data['results'] == []
