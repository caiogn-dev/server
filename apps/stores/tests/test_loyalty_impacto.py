"""`loyalty/impacto/`: quanto o programa custa e se está fazendo alguém voltar.

A tela de Fidelidade dizia "10 itens = 1 grátis" e nada sobre o que isso custa
nem se funciona. O dono decidia o número de itens no escuro. Este endpoint
entrega, dos últimos 90 dias, os números que respondem "quanto custa e está
valendo a pena" — tudo derivado de `StoreOrder`, `StoreLoyaltyAccount`,
`StoreLoyaltyTransaction` e `StoreCashbackLot`, sem campo inventado.

Janela: 90 dias = 3 meses; "por mês" é o total da janela ÷ 3.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.stores.models import (
    Store, StoreCashbackLot, StoreLoyaltyAccount, StoreLoyaltyTransaction, StoreOrder,
)

User = get_user_model()


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono-imp', email='dono-imp@x.com', password='x')
    loja = Store.objects.create(name='Loja Imp', slug='loja-imp', owner=dono, status='active')
    meta = loja.metadata or {}
    meta.update({'loyalty_enabled': True, 'loyalty_salads_required': 10, 'cashback_percent': 3})
    loja.metadata = meta
    loja.save(update_fields=['metadata'])
    return loja


@pytest.fixture
def api(loja):
    c = APIClient()
    c.force_authenticate(user=loja.owner)
    return c


def _impacto(api, loja):
    r = api.get(f'/api/v1/stores/{loja.slug}/loyalty/impacto/')
    assert r.status_code == 200, r.content
    return r.json()


def _pedido(loja, telefone, total='50', cliente=None, dias_atras=1, pago=True, metadata=None):
    p = StoreOrder.objects.create(
        store=loja, total=Decimal(total), subtotal=Decimal(total),
        payment_status='paid' if pago else 'pending',
        customer_phone=telefone, customer=cliente, customer_name='X',
        metadata=metadata or {},
    )
    # created_at é auto_now_add: a janela só se testa reescrevendo pelo update.
    StoreOrder.objects.filter(pk=p.pk).update(created_at=timezone.now() - timedelta(days=dias_atras))
    return p


def _cliente(i, telefone=''):
    # O padrão `cliente_<fone>` é como o OTP cria o usuário — é dele que sai o
    # telefone da conta de fidelidade.
    username = f'cliente_{telefone}' if telefone else f'semfone{i}'
    return User.objects.create_user(username=username, email=f'c{i}@x.com', password='x',
                                    first_name=f'Cliente{i}')


def _conta(loja, user, qualificados, resgatados=0):
    return StoreLoyaltyAccount.objects.create(
        store=loja, user=user, qualified_count=qualificados, redeemed_count=resgatados,
    )


@pytest.mark.django_db
class TestPermissao:
    def test_quem_nao_tem_vinculo_leva_403(self, loja):
        estranho = User.objects.create_user(username='estranho', email='e@x.com', password='x')
        c = APIClient()
        c.force_authenticate(user=estranho)
        r = c.get(f'/api/v1/stores/{loja.slug}/loyalty/impacto/')
        assert r.status_code == 403

    def test_anonimo_nao_entra(self, loja):
        r = APIClient().get(f'/api/v1/stores/{loja.slug}/loyalty/impacto/')
        assert r.status_code in (401, 403)


@pytest.mark.django_db
class TestTicketEPedidos:
    def test_ticket_medio_e_pedidos_por_mes_so_de_pedidos_pagos_da_janela(self, api, loja):
        _pedido(loja, '5563999990001', total='40')
        _pedido(loja, '5563999990002', total='60')
        _pedido(loja, '5563999990003', total='80')
        _pedido(loja, '5563999990004', total='1000', pago=False)      # não pago
        _pedido(loja, '5563999990005', total='1000', dias_atras=120)  # fora da janela

        r = _impacto(api, loja)
        assert r['ticket_medio'] == 60.0
        assert r['pedidos_por_mes'] == 1.0          # 3 pedidos ÷ 3 meses
        assert r['pedidos_pagos'] == 3

    def test_sem_pedido_nenhum_devolve_nulo_e_nao_zero(self, api, loja):
        # Zero diria "o ticket é R$ 0". Nulo diz "sem dados ainda".
        r = _impacto(api, loja)
        assert r['ticket_medio'] is None
        assert r['taxa_recompra_participantes'] is None
        assert r['taxa_recompra_nao_participantes'] is None


@pytest.mark.django_db
class TestAmostra:
    def test_menos_de_30_pedidos_pagos_nao_e_amostra_suficiente(self, api, loja):
        for i in range(29):
            _pedido(loja, f'55639999{i:05d}')
        r = _impacto(api, loja)
        assert r['amostra_suficiente'] is False
        assert r['pedidos_faltando'] == 1

    def test_30_pedidos_pagos_ja_e_amostra(self, api, loja):
        for i in range(30):
            _pedido(loja, f'55639999{i:05d}')
        r = _impacto(api, loja)
        assert r['amostra_suficiente'] is True
        assert r['pedidos_faltando'] == 0


@pytest.mark.django_db
class TestRecompra:
    def test_recompra_de_participantes_contra_nao_participantes(self, api, loja):
        # Participantes: A (2 pedidos) e B (1 pedido) → 1 de 2 voltou = 0,5
        a = _cliente(1, '5563999991111')
        b = _cliente(2, '5563999992222')
        _conta(loja, a, qualificados=4)
        _conta(loja, b, qualificados=1)
        _pedido(loja, '5563999991111', cliente=a)
        _pedido(loja, '5563999991111', cliente=a)
        _pedido(loja, '5563999992222', cliente=b)
        # Não participantes: C (2), D (1), E (1) → 1 de 3
        _pedido(loja, '5563999993333')
        _pedido(loja, '5563999993333')
        _pedido(loja, '5563999994444')
        _pedido(loja, '5563999995555')

        r = _impacto(api, loja)
        assert r['participantes'] == 2
        assert r['taxa_recompra_participantes'] == 0.5
        assert r['taxa_recompra_nao_participantes'] == pytest.approx(0.333, abs=0.001)

    def test_conta_zerada_nao_e_participante(self, api, loja):
        # "Pelo menos 1 carimbo": conta criada vazia pelo get_or_create não conta.
        a = _cliente(1, '5563999991111')
        _conta(loja, a, qualificados=0)
        _pedido(loja, '5563999991111', cliente=a)
        r = _impacto(api, loja)
        assert r['participantes'] == 0
        assert r['taxa_recompra_participantes'] is None
        assert r['taxa_recompra_nao_participantes'] == 0.0

    def test_participante_reconhecido_pelo_telefone_mesmo_sem_customer_no_pedido(self, api, loja):
        # Pedido de convidado (sem customer) de quem tem conta: é a mesma pessoa.
        a = _cliente(1, '5563999991111')
        _conta(loja, a, qualificados=3)
        _pedido(loja, '5563999991111')
        _pedido(loja, '5563999991111')
        r = _impacto(api, loja)
        assert r['taxa_recompra_participantes'] == 1.0

    def test_quem_tem_saldo_de_cashback_e_participante(self, api, loja):
        StoreCashbackLot.objects.create(
            store=loja, phone='5563999996666', amount=Decimal('5'), remaining=Decimal('5'),
            expires_at=timezone.now() + timedelta(days=30),
        )
        _pedido(loja, '5563999996666')
        r = _impacto(api, loja)
        assert r['participantes'] == 1
        assert r['taxa_recompra_participantes'] == 0.0


@pytest.mark.django_db
class TestProjecaoDoCarimbo:
    def _carimbos(self, loja, user, quantidade, dias_atras=5):
        conta = StoreLoyaltyAccount.objects.get(store=loja, user=user)
        t = StoreLoyaltyTransaction.objects.create(
            account=conta, kind=StoreLoyaltyTransaction.Kind.EARN, quantity=quantidade,
        )
        StoreLoyaltyTransaction.objects.filter(pk=t.pk).update(
            created_at=timezone.now() - timedelta(days=dias_atras))

    def test_brindes_por_mes_e_ritmo_de_carimbos_dividido_pelo_threshold(self, api, loja):
        a = _cliente(1, '5563999991111')
        _conta(loja, a, qualificados=90)
        self._carimbos(loja, a, 60)
        self._carimbos(loja, a, 30, dias_atras=200)   # fora da janela
        _pedido(loja, '5563999991111', total='30', cliente=a)

        r = _impacto(api, loja)
        assert r['itens_para_ganhar'] == 10
        assert r['carimbos_por_mes'] == 20.0           # 60 ÷ 3
        assert r['brindes_por_mes_projetados'] == 2.0  # 20 ÷ 10

    def test_custo_do_brinde_vem_dos_resgates_reais(self, api, loja):
        a = _cliente(1, '5563999991111')
        _conta(loja, a, qualificados=30)
        self._carimbos(loja, a, 30)
        _pedido(loja, '5563999991111', total='100', cliente=a,
                metadata={'loyalty_reward': {'applied': True, 'count': 1, 'discount': 24.0}})
        _pedido(loja, '5563999991111', total='100', cliente=a,
                metadata={'loyalty_reward': {'applied': True, 'count': 2, 'discount': 60.0}})

        r = _impacto(api, loja)
        # (24 + 60) ÷ 3 brindes = 28
        assert r['custo_por_brinde'] == 28.0
        assert r['custo_por_brinde_origem'] == 'resgates'
        # 30 carimbos ÷ 3 = 10/mês ÷ 10 itens = 1 brinde/mês × R$ 28
        assert r['custo_projetado_mes'] == 28.0

    def test_sem_resgate_o_custo_cai_no_ticket_medio(self, api, loja):
        a = _cliente(1, '5563999991111')
        _conta(loja, a, qualificados=30)
        self._carimbos(loja, a, 30)
        _pedido(loja, '5563999991111', total='45', cliente=a)

        r = _impacto(api, loja)
        assert r['custo_por_brinde'] == 45.0
        assert r['custo_por_brinde_origem'] == 'ticket_medio'
        assert r['custo_projetado_mes'] == 45.0


@pytest.mark.django_db
class TestCashback:
    def test_saldo_gerado_por_mes_e_percentual_da_receita_paga_mensal(self, api, loja):
        _pedido(loja, '5563999990001', total='1000')
        _pedido(loja, '5563999990002', total='2000')
        r = _impacto(api, loja)
        assert r['receita_paga_mes'] == 1000.0             # 3000 ÷ 3
        assert r['cashback_percentual'] == 3.0
        assert r['saldo_gerado_mes'] == 30.0


@pytest.mark.django_db
class TestAUmItem:
    def test_lista_quem_esta_a_um_item_com_telefone_mascarado(self, api, loja):
        a = _cliente(1, '5563999991111')
        b = _cliente(2, '5563999992222')
        c = _cliente(3, '5563999993333')
        _conta(loja, a, qualificados=9)
        _conta(loja, b, qualificados=19)
        _conta(loja, c, qualificados=5)

        r = _impacto(api, loja)
        assert r['a_um_item_total'] == 2
        linhas = r['a_um_item']
        assert {l['id'] for l in linhas} == {str(a.id), str(b.id)}
        assert all(l['faltam'] == 1 for l in linhas)
        tel = next(l['telefone'] for l in linhas if l['id'] == str(a.id))
        assert '99991111' not in tel and tel.endswith('1111')
        assert next(l['nome'] for l in linhas if l['id'] == str(a.id)) == 'Cliente1'

    def test_de_outra_loja_nao_aparece(self, api, loja):
        outra = Store.objects.create(name='Outra', slug='outra-imp', owner=loja.owner, status='active')
        _conta(outra, _cliente(9, '5563999999999'), qualificados=9)
        r = _impacto(api, loja)
        assert r['a_um_item'] == []
        assert r['a_um_item_total'] == 0
