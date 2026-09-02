"""O pedido lançado pelo PAINEL tem que cobrar o preço da promoção do dia.

O dono relatou (02/09): pedido feito pelo PDV/painel sai com o valor CHEIO,
mesmo com a promoção do dia ativa. O painel já mostra certo — `precoVigente`
está em todas as telas do PDV desde 12/08 — e manda para a API só
`product_id` e `quantity`. Quem precifica é o backend, e ele lia
`product.price` direto:

    apps/stores/api/serializers.py   → StoreOrderCreateSerializer.create
    apps/stores/api/views/order_views.py → adjust, op 'add'

Ou seja: a tela dizia R$ 30,75, o pedido nascia R$ 44,90. É o MESMO erro que
`preco_vigente()` foi criado para impedir — "quem lê `price` direto para
cobrar está errado" —, só que num caminho que ninguém tinha religado.

O bot (WhatsApp) tem o mesmo buraco e está coberto em
`test_pedido_do_bot_usa_preco_da_promocao`.
"""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.stores.api.serializers import StoreOrderCreateSerializer
from apps.stores.models import Store, StoreOrder, StoreOrderItem, StoreProduct

User = get_user_model()

QUARTA, QUINTA = 2, 3


def _quarta():
    """13:00 de uma quarta-feira real (12/08/2026)."""
    return timezone.make_aware(timezone.datetime(2026, 8, 12, 13, 0))


def _quinta():
    return timezone.make_aware(timezone.datetime(2026, 8, 13, 13, 0))


@pytest.fixture
def dono(db):
    return User.objects.create_user(username='dono-promo', email='dono-promo@x.com', password='x')


@pytest.fixture
def loja(dono):
    return Store.objects.create(name='Cê Saladas', slug='ce-promo', owner=dono, status='active')


@pytest.fixture
def almondega(loja):
    # `track_stock=False`: este teste é sobre PREÇO, não sobre estoque.
    return StoreProduct.objects.create(
        store=loja, name='Almôndega Premium', slug='almondega-premium',
        price=Decimal('44.90'), track_stock=False,
        status=StoreProduct.ProductStatus.ACTIVE,
        promo_price=Decimal('30.75'), promo_weekday=QUARTA,
    )


def _criar_pelo_painel(loja, produto, quantidade=1, **extra):
    dados = {
        'store': loja.slug,
        'customer_name': 'Cliente Balcão',
        'customer_phone': '00000000000',
        'delivery_method': 'pickup',
        'source': 'dashboard',
        'items': [{'product_id': str(produto.id), 'quantity': quantidade}],
        **extra,
    }
    s = StoreOrderCreateSerializer(data=dados)
    assert s.is_valid(), s.errors
    return s.save()


@pytest.mark.django_db
class TestPedidoDoPainel:
    def test_no_dia_da_promo_o_pedido_nasce_com_o_preco_promocional(self, loja, almondega):
        with patch('django.utils.timezone.localtime', return_value=_quarta()):
            pedido = _criar_pelo_painel(loja, almondega, quantidade=2)

        item = pedido.items.first()
        assert item.unit_price == Decimal('30.75')
        assert item.subtotal == Decimal('61.50')
        assert pedido.subtotal == Decimal('61.50')
        assert pedido.total == Decimal('61.50')

    def test_fora_do_dia_cobra_cheio(self, loja, almondega):
        with patch('django.utils.timezone.localtime', return_value=_quinta()):
            pedido = _criar_pelo_painel(loja, almondega)

        assert pedido.items.first().unit_price == Decimal('44.90')
        assert pedido.total == Decimal('44.90')

    def test_desconto_manual_incide_sobre_o_preco_ja_promocional(self, loja, almondega):
        """Promoção e desconto do caixa se somam — não se substituem."""
        with patch('django.utils.timezone.localtime', return_value=_quarta()):
            pedido = _criar_pelo_painel(loja, almondega, discount='5.00')

        assert pedido.subtotal == Decimal('30.75')
        assert pedido.total == Decimal('25.75')

    def test_produto_sem_promocao_nao_muda_de_preco(self, loja):
        simples = StoreProduct.objects.create(
            store=loja, name='Suco', slug='suco', price=Decimal('9.00'),
            track_stock=False, status=StoreProduct.ProductStatus.ACTIVE,
        )
        with patch('django.utils.timezone.localtime', return_value=_quarta()):
            pedido = _criar_pelo_painel(loja, simples, quantidade=3)

        assert pedido.items.first().unit_price == Decimal('9.00')
        assert pedido.total == Decimal('27.00')


@pytest.mark.django_db
class TestItemAdicionadoNoPedidoAberto:
    """`POST /orders/{id}/adjust/` com `op: add` — o painel também vende por aqui."""

    def test_item_adicionado_entra_com_o_preco_do_dia(self, dono, loja, almondega):
        pedido = StoreOrder.objects.create(
            store=loja, customer_name='C', customer_phone='6300000000',
            subtotal=Decimal('0.00'), total=Decimal('0.00'),
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=dono).key}')
        url = f'/api/v1/stores/{loja.slug}/orders/{pedido.id}/adjust/'

        with patch('django.utils.timezone.localtime', return_value=_quarta()):
            resp = client.post(url, {
                'item_ops': [{'op': 'add', 'product_id': str(almondega.id), 'quantity': 2}],
            }, format='json')

        assert resp.status_code == 200, resp.content
        item = StoreOrderItem.objects.get(order=pedido, product=almondega)
        assert item.unit_price == Decimal('30.75')
        assert item.subtotal == Decimal('61.50')
        pedido.refresh_from_db()
        assert pedido.total == Decimal('61.50')
