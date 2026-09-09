"""O modal precisa dizer QUEM é esse cliente, não só o que ele pediu.

O dono pediu, em 09/set, três informações que a tela do pedido não dava:
quantos pedidos essa pessoa já fez, qual cupom ela usou e quanto de saldo
gastou. Cupom (`coupon_code`) e cashback (`metadata.cashback_aplicado`) já
saíam no serializer e o painel só não os desenhava; a contagem não existia.

A contagem sai por VARIANTES do telefone (o wa_id vem sem o nono dígito) e é
escopada à loja — o histórico do cliente na Cê Saladas não é o da Pastita.

Só no DETALHE: numa lista de 50 pedidos isso seriam 50 COUNT extras, e a
listagem é a tela mais quente do painel.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.stores.api.serializers import StoreOrderSerializer
from apps.stores.models import Store, StoreOrder


@pytest.fixture
def loja(db):
    dono = get_user_model().objects.create_user(
        username='dono-hist', email='dono-hist@teste.local', password='x')
    return Store.objects.create(owner=dono, name='Loja Hist', slug='loja-hist', status='active')


def _pedido(loja, phone, **kw):
    return StoreOrder.objects.create(
        store=loja, customer_name='Cliente', customer_phone=phone,
        subtotal=Decimal('30.00'), total=Decimal('30.00'), **kw,
    )


@pytest.mark.django_db
class TestQuantosPedidosOClienteJaFez:
    def test_conta_os_pedidos_anteriores_da_mesma_pessoa(self, loja):
        _pedido(loja, '5563991232486')
        _pedido(loja, '5563991232486')
        atual = _pedido(loja, '5563991232486')

        dados = StoreOrderSerializer(atual).data
        assert dados['pedidos_do_cliente'] == 3

    def test_o_nono_digito_nao_divide_o_historico(self, loja):
        """wa_id vem sem o 9, o site grava com — é a mesma pessoa."""
        _pedido(loja, '556391232486')
        atual = _pedido(loja, '5563991232486')

        assert StoreOrderSerializer(atual).data['pedidos_do_cliente'] == 2

    def test_nao_soma_o_historico_de_outra_loja(self, loja):
        outra = Store.objects.create(
            owner=loja.owner, name='Outra', slug='outra-hist', status='active')
        _pedido(outra, '5563991232486')
        atual = _pedido(loja, '5563991232486')

        assert StoreOrderSerializer(atual).data['pedidos_do_cliente'] == 1

    def test_na_listagem_nao_paga_o_count_por_linha(self, loja):
        """N+1 na tela mais quente do painel não vale a informação."""
        _pedido(loja, '5563991232486')
        _pedido(loja, '5563991232486')

        linhas = StoreOrderSerializer(StoreOrder.objects.all(), many=True).data
        assert all(l['pedidos_do_cliente'] is None for l in linhas)

    def test_pedido_sem_telefone_nao_quebra(self, loja):
        atual = _pedido(loja, '')
        assert StoreOrderSerializer(atual).data['pedidos_do_cliente'] == 0
