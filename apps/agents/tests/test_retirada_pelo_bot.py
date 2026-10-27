"""27/10, Carlos (CE-2610277336): pediu para RETIRAR e o pedido nasceu entrega.

A ferramenta `finalizar_pedido` do agente criava SEMPRE `delivery_method=
"delivery"` — não havia como dizer retirada. O LLM escreveu "Retirada na loja"
no único campo que tinha, o de endereço; o texto foi geocodificado, ganhou um
ponto no mapa e o painel mostrou entrega para um cliente que vinha buscar.
"""
from decimal import Decimal

import pytest

from apps.agents.services.retirada import pediu_retirada
from apps.stores.tests.factories import make_product, make_store
from apps.whatsapp.services.order_service import WhatsAppOrderService


class TestPediuRetirada:
    @pytest.mark.parametrize('texto', [
        'Retirada na loja', 'retirada', 'Vou retirar', 'retirar no local',
        'vou buscar na loja', 'Busco aí', 'pego na loja', 'Retiro no balcão',
    ])
    def test_frases_de_retirada(self, texto):
        assert pediu_retirada(texto)

    @pytest.mark.parametrize('texto', [
        'Quadra 110 Sul Alameda 3, 51', 'Av. Teotônio Segurado, 1500',
        'Rua do Retiro, 12', 'FIETO - sede temporária Orla 14', '', None,
    ])
    def test_endereco_nao_e_retirada(self, texto):
        assert not pediu_retirada(texto)


@pytest.mark.django_db
class TestPedidoDeRetiradaPeloBot:
    def test_retirada_nasce_pickup_sem_frete_e_sem_endereco(self):
        store = make_store()
        produto = make_product(store, price=Decimal('30.00'))
        svc = WhatsAppOrderService(store=store, phone_number='5563999990077', customer_name='Carlos')
        r = svc.create_order_from_cart(
            items=[{'product_id': str(produto.id), 'quantity': 1, 'unit_price': 30.0}],
            delivery_address='', delivery_method='pickup', payment_method='cash',
        )
        assert r['success'] is True, r
        from apps.stores.models import StoreOrder
        o = StoreOrder.objects.get(order_number=r['order_number'])
        assert o.delivery_method == 'pickup'
        assert o.delivery_fee == Decimal('0')
        assert not (o.delivery_address or {}).get('lat')
