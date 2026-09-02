"""Painel do cashback: o que o dono precisa DECIDIR olhando a tela.

Os números aqui não são decorativos. "R$ 340 de saldo vence em 7 dias" é uma
campanha de WhatsApp que se manda hoje; "saldo em circulação" é passivo que a
loja vai pagar. Por isso o endpoint agrega no BANCO e não devolve página para
o frontend somar — somar página dá número menor que o real com cara de total.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreCashbackLot


@pytest.fixture
def dono(db):
    return get_user_model().objects.create_user(
        username='dono-cbv', email='dono-cbv@teste.local', password='x',
    )


@pytest.fixture
def loja(db, dono):
    return Store.objects.create(
        owner=dono, name='Loja CB', slug='loja-cb', store_type='food',
        status='active', metadata={'cashback_enabled': True},
    )


@pytest.fixture
def cliente(dono):
    c = APIClient()
    c.force_authenticate(user=dono)
    return c


def _lote(loja, phone, valor, dias=60, restante=None, origin='purchase'):
    return StoreCashbackLot.objects.create(
        store=loja, phone=phone, origin=origin,
        amount=Decimal(valor), remaining=Decimal(restante if restante is not None else valor),
        expires_at=timezone.now() + timedelta(days=dias),
    )


def _url(loja):
    # Caminho literal, como o resto da suíte: estas rotas vivem em
    # store_frontend_patterns e não são alcançáveis por reverse() pelo nome.
    return f'/api/v1/stores/{loja.slug}/cashback/'


@pytest.mark.django_db
class TestPermissao:
    def test_exige_autenticacao(self, loja):
        assert APIClient().get(_url(loja)).status_code in (401, 403)

    def test_loja_de_outro_dono_e_negada(self, loja, db):
        outro = get_user_model().objects.create_user(
            username='intruso', email='intruso@teste.local', password='x',
        )
        c = APIClient()
        c.force_authenticate(user=outro)
        assert c.get(_url(loja)).status_code == 403


@pytest.mark.django_db
class TestResumo:
    def test_saldo_em_circulacao_soma_o_que_sobrou(self, loja, cliente):
        _lote(loja, '5563999547790', '10.00', restante='4.00')
        _lote(loja, '5563988887777', '6.00')
        r = cliente.get(_url(loja))
        assert r.status_code == 200
        assert Decimal(str(r.data['resumo']['saldo_em_circulacao'])) == Decimal('10.00')

    def test_lote_vencido_sai_do_saldo(self, loja, cliente):
        _lote(loja, '5563999547790', '10.00', dias=-1)
        assert Decimal(str(cliente.get(_url(loja)).data['resumo']['saldo_em_circulacao'])) == Decimal('0.00')

    def test_conta_clientes_com_saldo_nao_lotes(self, loja, cliente):
        _lote(loja, '5563999547790', '5.00')
        _lote(loja, '5563999547790', '5.00')
        _lote(loja, '5563988887777', '5.00')
        assert cliente.get(_url(loja)).data['resumo']['clientes_com_saldo'] == 2

    def test_vence_em_7_dias_e_a_campanha_de_hoje(self, loja, cliente):
        _lote(loja, '5563999547790', '30.00', dias=3)
        _lote(loja, '5563988887777', '99.00', dias=40)
        assert Decimal(str(cliente.get(_url(loja)).data['resumo']['vence_em_7_dias'])) == Decimal('30.00')

    def test_separa_o_que_veio_de_indicacao(self, loja, cliente):
        _lote(loja, '5563999547790', '3.00', origin='purchase')
        _lote(loja, '5563988887777', '5.00', origin='referral')
        resumo = cliente.get(_url(loja)).data['resumo']
        assert Decimal(str(resumo['saldo_de_indicacao'])) == Decimal('5.00')

    def test_loja_sem_cashback_responde_zerado_e_nao_quebra(self, db, dono):
        loja = Store.objects.create(
            owner=dono, name='Sem CB', slug='sem-cb', store_type='food', status='active',
        )
        c = APIClient()
        c.force_authenticate(user=dono)
        r = c.get(_url(loja))
        assert r.status_code == 200
        assert r.data['enabled'] is False
        assert Decimal(str(r.data['resumo']['saldo_em_circulacao'])) == Decimal('0.00')


@pytest.mark.django_db
class TestListaDeClientes:
    def test_ordena_por_quem_vence_primeiro(self, loja, cliente):
        """A ordem É a decisão: quem perde saldo antes é quem recebe mensagem."""
        _lote(loja, '5563900000001', '10.00', dias=30)
        _lote(loja, '5563900000002', '10.00', dias=2)
        nomes = [c['phone'] for c in cliente.get(_url(loja)).data['results']]
        assert nomes[0] == '5563900000002'

    def test_cliente_sem_saldo_nao_aparece(self, loja, cliente):
        _lote(loja, '5563900000001', '10.00', restante='0.00')
        assert cliente.get(_url(loja)).data['results'] == []

    def test_agrupa_lotes_do_mesmo_telefone(self, loja, cliente):
        _lote(loja, '5563900000001', '4.00', dias=10)
        _lote(loja, '5563900000001', '6.00', dias=50)
        linhas = cliente.get(_url(loja)).data['results']
        assert len(linhas) == 1
        assert Decimal(str(linhas[0]['saldo'])) == Decimal('10.00')
