"""Venda de pacote não é pedido de comida — e não pode entupir o quadro.

A TENSÃO REAL. A compra de carteira PRECISA virar pedido, senão os R$ 270 somem
do faturamento: os pedidos seguintes saem com desconto e o mês fecha como se a
loja não tivesse vendido. Mas ela NÃO é trabalho para ninguém — não tem comida
para preparar nem endereço para ir.

Então o registro fica, e some da lista OPERACIONAL: quem abre a tela de pedidos
está perguntando "o que eu tenho que fazer agora", e uma linha que não pede ação
nenhuma só rouba atenção das que pedem. Quem quiser ver os pacotes vendidos
filtra por eles de propósito.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreOrder

User = get_user_model()


@pytest.fixture
def dono(db):
    return User.objects.create_user(username='dono-quadro', email='q@t.local', password='x')


@pytest.fixture
def loja(db, dono):
    return Store.objects.create(
        owner=dono, name='Cê Teste', slug='ce-teste-quadro', store_type='food', status='active',
    )


@pytest.fixture
def cliente(dono):
    c = APIClient()
    c.force_authenticate(user=dono)
    return c


def _pedido(loja, source, numero):
    return StoreOrder.objects.create(
        store=loja, order_number=numero, customer_name='C', customer_phone='5563991386719',
        subtotal=Decimal('38.00'), delivery_fee=Decimal('0'), discount=Decimal('0'),
        total=Decimal('38.00'), status='confirmed', payment_status='paid', source=source,
    )


@pytest.mark.django_db
class TestQuadroDePedidos:

    def _listar(self, cliente, loja, **params):
        r = cliente.get(f'/api/v1/stores/{loja.slug}/orders/', params)
        assert r.status_code == 200, r.content
        dados = r.json()
        return [o['order_number'] for o in (dados.get('results') or dados)]

    def test_pacote_de_carteira_nao_aparece_na_lista_de_trabalho(self, loja, cliente):
        _pedido(loja, 'web', 'CE-COMIDA')
        _pedido(loja, 'carteira', 'CE-PACOTE')

        numeros = self._listar(cliente, loja)
        assert 'CE-COMIDA' in numeros
        assert 'CE-PACOTE' not in numeros, 'venda de saldo entupindo o quadro'

    def test_mas_aparece_para_quem_pede_por_ela(self, loja, cliente):
        """Pedido explícito vence o padrão — é como o dono confere o que vendeu."""
        _pedido(loja, 'web', 'CE-COMIDA')
        _pedido(loja, 'carteira', 'CE-PACOTE')

        numeros = self._listar(cliente, loja, source='carteira')
        assert numeros == ['CE-PACOTE']

    def test_os_outros_canais_continuam_intactos(self, loja, cliente):
        for src in ['web', 'whatsapp', 'pdv', 'payment_link']:
            _pedido(loja, src, f'CE-{src.upper()}')

        numeros = self._listar(cliente, loja)
        assert len(numeros) == 4, 'a exclusão pegou canal que não devia'


@pytest.mark.django_db
class TestFaturamentoContinuaContando:
    """O contrário do teste acima, e o motivo de o registro existir."""

    def test_a_venda_de_pacote_segue_no_banco_e_paga(self, loja):
        _pedido(loja, 'carteira', 'CE-PACOTE')
        pedido = StoreOrder.objects.get(store=loja, source='carteira')
        assert pedido.payment_status == 'paid'
        assert pedido.total == Decimal('38.00')
        # Relatórios consultam StoreOrder direto, não a lista da tela: a
        # exclusão é da VISUALIZAÇÃO operacional, nunca do dado.
        assert StoreOrder.objects.filter(store=loja, payment_status='paid').count() == 1
