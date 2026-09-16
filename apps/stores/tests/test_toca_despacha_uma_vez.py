"""Pedido confirmado vira UMA corrida no Toca Delivery.

A tarefa é `acks_late` com retry: se o worker cai depois do `provider.create`
e antes de gravar `external_delivery_id`, ou se duas confirmações disparam a
tarefa ao mesmo tempo, a checagem `if order.external_delivery_id` não vê a
primeira corrida e chama o entregador de novo — corrida cobrada em dobro.
Até 15/set o log não mostra caso (165 pedidos despachados, 6 no log de 06/set
para cá), mas a porta estava aberta. Trava por pedido antes do `create`,
liberada só se o `create` falhou.
"""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

from apps.stores.models import Store, StoreOrder
from apps.stores.services.delivery_provider import TocaDeliveryProvider
from apps.stores.services.delivery_provider.base import DeliveryProviderError, DeliveryResult
from apps.stores.tasks import dispatch_order_to_toca_delivery

User = get_user_model()
RESULTADO = DeliveryResult(external_id='corrida-1', external_code='TCA-1', external_status='created')


@pytest.fixture(autouse=True)
def cache_limpo():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def pedido(db):
    dono = User.objects.create_user(username='dono_toca_uma_vez', password='x')
    loja = Store.objects.create(owner=dono, name='Loja Toca', slug='loja-toca-uma-vez')
    return StoreOrder.objects.create(
        store=loja, total=Decimal('50'), subtotal=Decimal('40'), delivery_fee=Decimal('10'),
        status='pending', payment_status='paid', payment_method='pix', delivery_method='delivery',
    )


def _rodar(pedido, **create_kw):
    with patch('apps.stores.services.delivery_provider.get_delivery_provider',
               return_value=TocaDeliveryProvider()), \
         patch.object(TocaDeliveryProvider, 'create', **create_kw) as create:
        dispatch_order_to_toca_delivery.apply(args=[str(pedido.id)], throw=False)
    return create


@pytest.mark.django_db
class TestTocaDespachaUmaVez:

    def test_despacha_e_grava_a_corrida(self, pedido):
        create = _rodar(pedido, return_value=RESULTADO)

        create.assert_called_once()
        pedido.refresh_from_db()
        assert pedido.external_delivery_id == 'corrida-1'

    def test_segunda_execucao_em_andamento_nao_chama_de_novo(self, pedido):
        """Outra execução segura a trava (create em curso, id ainda não gravado)."""
        cache.add(f'toca_dispatch:{pedido.id}', 1, timeout=600)

        create = _rodar(pedido, return_value=RESULTADO)

        create.assert_not_called()

    def test_falha_no_create_libera_para_o_retry(self, pedido):
        create = _rodar(pedido, side_effect=[DeliveryProviderError('fora do ar'), RESULTADO])

        assert create.call_count == 2
        pedido.refresh_from_db()
        assert pedido.external_delivery_id == 'corrida-1'
