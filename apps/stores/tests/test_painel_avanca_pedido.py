"""O painel pode avançar o pedido pulando etapa — e a recusa fala português.

MEDIDO (nginx, 28/09 → 05/10): 23 de 163 mudanças de status vindas do painel
foram recusadas com 400 (14%). O Kanban deixa arrastar para qualquer coluna e
o KDS oferece "Iniciar preparo" para pedido pendente, mas o serviço só aceitava
`pending → confirmed`: arrastar um pedido em dinheiro de "Novos" direto para
"Em preparo" voltava "Invalid status transition from pending to preparing" — em
inglês, na tela do operador, no meio do almoço.

Regras:
1. Avançar pulando etapa é permitido (a trava do PIX não pago continua na view).
   Quem pula a confirmação ganha `confirmed_at` — as métricas de SLA leem ele.
2. `confirmed → ready` também é avanço.
3. Voltar continua recusado (não reenviamos aviso ao cliente), mas a mensagem é
   em português e diz de onde para onde.
"""
from decimal import Decimal

import pytest

from apps.stores.models import StoreOrder
from apps.stores.services.order_service import OrderService
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    return make_store(name='Cê Saladas')


def _pedido(loja, status='pending', metodo='cash'):
    return StoreOrder.objects.create(
        store=loja, total=Decimal('40.00'), subtotal=Decimal('40.00'),
        status=status, payment_status='pending', payment_method=metodo,
        customer_phone='+5563984143551', customer_name='Ana',
    )


@pytest.mark.django_db
class TestAvancarPulandoEtapa:
    @pytest.mark.parametrize('destino', ['preparing', 'ready', 'out_for_delivery', 'delivered'])
    def test_pendente_avanca_direto(self, loja, destino):
        pedido = _pedido(loja)
        resultado = OrderService().update_status(pedido, destino, notify_customer=False)
        assert resultado['success'], resultado
        pedido.refresh_from_db()
        assert pedido.status == destino

    def test_quem_pula_a_confirmacao_ganha_confirmed_at(self, loja):
        pedido = _pedido(loja)
        OrderService().update_status(pedido, 'preparing', notify_customer=False)
        pedido.refresh_from_db()
        assert pedido.confirmed_at is not None
        assert pedido.preparing_at is not None

    def test_confirmado_vai_para_pronto(self, loja):
        pedido = _pedido(loja, status='confirmed')
        resultado = OrderService().update_status(pedido, 'ready', notify_customer=False)
        assert resultado['success'], resultado


@pytest.mark.django_db
class TestVoltarEhRecusadoEmPortugues:
    def test_entregue_nao_volta_para_preparo(self, loja):
        pedido = _pedido(loja, status='delivered')
        resultado = OrderService().update_status(pedido, 'preparing', notify_customer=False)
        assert not resultado['success']
        assert resultado['error'] == 'O pedido está "Entregue" e não pode ir para "Em preparo".'
        pedido.refresh_from_db()
        assert pedido.status == 'delivered'

    def test_preparo_nao_volta_para_pendente(self, loja):
        pedido = _pedido(loja, status='preparing')
        resultado = OrderService().update_status(pedido, 'pending', notify_customer=False)
        assert not resultado['success']
        assert 'Em preparo' in resultado['error']


@pytest.mark.django_db
def test_pix_nao_pago_continua_travado_na_view(loja, client):
    """A regra 1 não abre a porta do PIX: a view barra antes do serviço."""
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient

    pedido = _pedido(loja, metodo='pix')
    dono = loja.owner if loja.owner_id else get_user_model().objects.create_superuser('su', 's@t.com', 'x')
    api = APIClient()
    api.force_authenticate(dono)
    resp = api.post(f'/api/v1/stores/orders/{pedido.id}/update_status/', {'status': 'preparing'}, format='json')
    assert resp.status_code == 400
    assert resp.json()['code'] == 'payment_not_confirmed'


@pytest.mark.django_db
def test_cancelar_entregue_recusa_em_portugues(loja):
    pedido = _pedido(loja, status='delivered')
    resultado = OrderService().cancel_order(pedido, reason='duplicado')
    assert not resultado['success']
    assert resultado['error'] == 'O pedido está "Entregue" e não pode ser cancelado.'
