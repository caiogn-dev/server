"""A comanda diz se é o 1º ou o 5º pedido do cliente (22/10).

O dono imprimia pelo painel e não via o número; o papel do print agent também
não trazia. Conta só pedido que valeu (pago, não cancelado, não teste) feito
ANTES deste, mais este — reimprimir um pedido antigo não pode dizer "12º".
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.stores.api.serializers import StoreOrderSerializer
from apps.stores.models import Store, StoreOrder
from apps.stores.services.pedidos_do_cliente import numero_do_pedido_do_cliente
from apps.stores.services.print_service import build_order_print_payload

FONE = '5563991232486'


@pytest.fixture
def loja(db):
    dono = get_user_model().objects.create_user(
        username='dono-cmd', email='dono-cmd@teste.local', password='x')
    return Store.objects.create(owner=dono, name='Loja Cmd', slug='loja-cmd', status='active')


def _pedido(loja, phone=FONE, **kw):
    dados = dict(
        store=loja, customer_name='Cliente', customer_phone=phone,
        subtotal=Decimal('30.00'), total=Decimal('30.00'),
        payment_status='paid', status='delivered',
    )
    dados.update(kw)
    return StoreOrder.objects.create(**dados)


@pytest.mark.django_db
class TestNumeroDoPedidoDoCliente:
    def test_primeiro_pedido(self, loja):
        assert numero_do_pedido_do_cliente(_pedido(loja, payment_status='pending', status='pending')) == 1

    def test_conta_os_anteriores_que_valeram(self, loja):
        _pedido(loja)
        _pedido(loja, phone='556391232486')  # sem o nono dígito: mesma pessoa
        atual = _pedido(loja, payment_status='pending', status='confirmed')
        assert numero_do_pedido_do_cliente(atual) == 3

    def test_cancelado_abandonado_e_teste_nao_contam(self, loja):
        _pedido(loja, status='cancelled')
        _pedido(loja, payment_status='pending', status='pending')
        _pedido(loja, metadata={'is_test': True})
        assert numero_do_pedido_do_cliente(_pedido(loja)) == 1

    def test_reimprimir_pedido_antigo_nao_conta_os_depois_dele(self, loja):
        antigo = _pedido(loja)
        StoreOrder.objects.filter(pk=antigo.pk).update(created_at=timezone.now() - timedelta(days=3))
        antigo.refresh_from_db()
        _pedido(loja)
        _pedido(loja)
        assert numero_do_pedido_do_cliente(antigo) == 1

    def test_sem_telefone_e_none(self, loja):
        assert numero_do_pedido_do_cliente(_pedido(loja, phone='')) is None

    def test_vai_na_comanda_do_print_agent(self, loja):
        _pedido(loja)
        atual = _pedido(loja, payment_status='pending', status='confirmed')
        assert build_order_print_payload(atual)['customer']['pedidos'] == 2

    def test_painel_usa_a_mesma_conta(self, loja):
        _pedido(loja, status='cancelled')
        atual = _pedido(loja)
        assert StoreOrderSerializer(atual).data['pedidos_do_cliente'] == 1
