"""A linha de combo do carrinho tem que virar PEDIDO — com os sabores.

É o último elo. A montagem já pergunta e o resumo já mostra; se o pedido nascer
sem os sabores, a cozinha recebe "COMBO 5 SALADAS" e nenhuma instrução do que
preparar — pior do que não ter o fluxo, porque parece que funcionou.

Prova o caminho inteiro com o formato REAL que a montagem produz, incluindo a
repetição virando quantidade (2x frango, 3x camarão).
"""
from decimal import Decimal

import pytest

from apps.stores.models import StoreCombo, StoreOrder, StoreProduct
from apps.stores.models.combo_group import (
    ComboProductGroup, ComboProductGroupProductOption,
)
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    return make_store(name='Cê Saladas', city='Palmas', state='TO', is_active=True)


@pytest.fixture
def cenario(loja):
    frango = StoreProduct.objects.create(
        store=loja, name='Especial Filé de Frango', slug='frango',
        price=Decimal('47.99'), is_active=True, status='active', track_stock=False,
    )
    camarao = StoreProduct.objects.create(
        store=loja, name='Magnifico Camarão', slug='camarao',
        price=Decimal('47.99'), is_active=True, status='active', track_stock=False,
    )
    combo = StoreCombo.objects.create(
        store=loja, name='COMBO 5 SALADAS', slug='combo-5',
        price=Decimal('239.98'), is_active=True,
    )
    grupo = ComboProductGroup.objects.create(
        combo=combo, title='Escolha suas 5 saladas',
        min_selections=5, max_selections=5, is_required=True,
    )
    for p in (frango, camarao):
        ComboProductGroupProductOption.objects.create(group=grupo, product=p)
    return combo, grupo, frango, camarao


def _item(combo, grupo, frango, camarao):
    """Exatamente o que `montagem_de_combo.responder` devolve."""
    return {
        'combo_id': str(combo.id),
        'quantity': 1,
        'group_selections': {
            str(grupo.id): [str(frango.id)] * 2 + [str(camarao.id)] * 3,
        },
    }


def _criar(loja, itens):
    from apps.whatsapp.services import create_order_from_whatsapp

    return create_order_from_whatsapp(
        store_slug=loja.slug,
        phone_number='+5563984143551',
        items=itens,
        customer_name='Dyana',
        delivery_method='pickup',
        payment_method='pix',
    )


@pytest.mark.django_db
class TestOComboViraPedido:
    def test_o_pedido_nasce(self, loja, cenario):
        r = _criar(loja, [_item(*cenario)])

        assert r.get('success'), r
        assert StoreOrder.objects.filter(store=loja).count() == 1

    def test_o_pedido_cobra_o_preco_do_COMBO(self, loja, cenario):
        """Cobrar item a item daria R$ 239,95 em vez do preço do combo."""
        _criar(loja, [_item(*cenario)])

        pedido = StoreOrder.objects.get(store=loja)
        assert Decimal(str(pedido.subtotal)) == Decimal('239.98')

    def test_os_sabores_chegam_na_COZINHA(self, loja, cenario):
        """Sem isto a comanda diz "COMBO 5 SALADAS" e nada do que preparar."""
        _criar(loja, [_item(*cenario)])

        pedido = StoreOrder.objects.get(store=loja)
        linha = pedido.combo_items.first()
        assert linha is not None, 'o combo não virou linha do pedido'

        nomes = {
            v.get('product_name'): v.get('quantity')
            for v in (linha.selected_variants_data or [])
        }
        assert nomes.get('Especial Filé de Frango') == 2
        assert nomes.get('Magnifico Camarão') == 3


@pytest.mark.django_db
class TestOQueNaoPodeAcontecer:
    def test_combo_de_OUTRA_loja_e_recusado(self, loja, cenario):
        """Aceitar seria pedido cross-tenant — vazamento entre lojas."""
        outra = make_store(name='Kero Kero')
        combo, grupo, frango, camarao = cenario

        r = _criar(outra, [_item(combo, grupo, frango, camarao)])

        assert not r.get('success')
        assert StoreOrder.objects.filter(store=outra).count() == 0

    def test_o_cliente_nao_dita_o_preco(self, loja, cenario):
        """Preço vem do catálogo. Aceitar do payload é a fraude de 3f550c6."""
        item = _item(*cenario)
        item['unit_price'] = '0.01'

        _criar(loja, [item])

        pedido = StoreOrder.objects.get(store=loja)
        assert Decimal(str(pedido.subtotal)) == Decimal('239.98')

    def test_combo_junto_com_produto_soma_os_dois(self, loja, cenario):
        combo, grupo, frango, camarao = cenario

        _criar(loja, [
            _item(combo, grupo, frango, camarao),
            {'product_id': str(frango.id), 'quantity': 1},
        ])

        pedido = StoreOrder.objects.get(store=loja)
        assert Decimal(str(pedido.subtotal)) == Decimal('287.97')
