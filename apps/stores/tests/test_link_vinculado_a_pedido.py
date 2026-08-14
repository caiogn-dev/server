"""Pedido manual pode nascer com link de pagamento vinculado.

Pedido do dono em 14/ago: "caso eu lance um pedido manual, é possível vincular /
gerar um link de pagamento vinculado ao pedido".

O caminho já existia quase inteiro: a cobrança do tipo `link` faz
`StorePayment.objects.create(order=order, ...)`. O que faltava era o endpoint do
painel — ele chamava `create_payment(None, 'link', ...)`, com pedido sempre
None, então TODO link nascia avulso.

Foi por isso que a cobrança da Yeda precisou de link colado à mão: não havia
como gerar um já amarrado ao pedido que a dona tinha acabado de lançar.

Contrato: `order` é opcional. Com pedido, a cobrança nasce amarrada e o webhook
reconcilia nele. Sem pedido, segue avulsa (e vira venda quando paga).
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.stores.models import StoreOrder, StorePayment
from apps.stores.tests.factories import make_store

User = get_user_model()


@pytest.fixture
def dono_e_loja(db):
    loja = make_store(name='Cê Saladas')
    return loja.owner, loja


@pytest.fixture
def cliente(dono_e_loja):
    dono, _ = dono_e_loja
    c = APIClient()
    c.force_authenticate(user=dono)
    return c


def _pedido(loja, total='142.00'):
    return StoreOrder.objects.create(
        store=loja, total=Decimal(total), subtotal=Decimal(total),
        status='pending', payment_status='pending', payment_method='card',
    )


@pytest.mark.django_db
class TestLinkVinculadoAoPedido:
    def test_endpoint_aceita_pedido(self, cliente, dono_e_loja, monkeypatch):
        from apps.stores.services.checkout_service import CheckoutService

        _, loja = dono_e_loja
        pedido = _pedido(loja)
        recebido = {}

        def falso(order, metodo, dados, **kw):
            recebido['order'] = order
            recebido['metodo'] = metodo
            return {'success': True, 'payment_url': 'https://mp/x', 'payment_db_id': None}

        monkeypatch.setattr(CheckoutService, 'create_payment', staticmethod(falso))

        r = cliente.post('/api/v1/stores/payments/create_link/', {
            'store': str(loja.id), 'amount': '142.00', 'order': str(pedido.id),
        }, format='json')

        assert r.status_code in (200, 201), r.content[:200]
        assert recebido['order'] is not None, 'o pedido não chegou no serviço'
        assert recebido['order'].id == pedido.id

    def test_sem_pedido_continua_funcionando(self, cliente, dono_e_loja, monkeypatch):
        """Cobrança avulsa é caso legítimo — não pode virar obrigatória."""
        from apps.stores.services.checkout_service import CheckoutService

        _, loja = dono_e_loja
        recebido = {}
        monkeypatch.setattr(CheckoutService, 'create_payment', staticmethod(
            lambda order, m, d, **kw: recebido.update(order=order) or {
                'success': True, 'payment_url': 'https://mp/x', 'payment_db_id': None}))

        r = cliente.post('/api/v1/stores/payments/create_link/', {
            'store': str(loja.id), 'amount': '50.00',
        }, format='json')

        assert r.status_code in (200, 201)
        assert recebido['order'] is None

    def test_pedido_de_outra_loja_e_recusado(self, cliente, dono_e_loja):
        """Sem esta guarda, dá para cobrar pelo pedido de qualquer loja."""
        _, loja = dono_e_loja
        outra = make_store(name='Ivoneth')
        alheio = _pedido(outra)

        r = cliente.post('/api/v1/stores/payments/create_link/', {
            'store': str(loja.id), 'amount': '142.00', 'order': str(alheio.id),
        }, format='json')

        assert r.status_code == 400, r.content[:200]

    def test_pedido_inexistente_e_recusado(self, cliente, dono_e_loja):
        _, loja = dono_e_loja

        r = cliente.post('/api/v1/stores/payments/create_link/', {
            'store': str(loja.id), 'amount': '10.00',
            'order': '00000000-0000-0000-0000-000000000000',
        }, format='json')

        assert r.status_code == 400
