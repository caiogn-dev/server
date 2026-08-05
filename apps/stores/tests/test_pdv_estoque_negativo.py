"""
Venda de balcão não pode deixar o estoque negativo.

Regressão (S2-RACE-006): `StoreOrderCreateSerializer.create` — o caminho do
PDV/painel — resolvia os produtos sem lock, nunca validava disponibilidade e ia
direto ao `F('stock_quantity') - quantity`. Como o campo é IntegerField sem piso
nem CheckConstraint, o valor ficava negativo em silêncio.

O estrago não para aí: com stock_quantity <= 0, `is_in_stock` vira False e o
produto aparece ESGOTADO no cardápio web e no do bot — 100% dos visitantes
deixam de poder comprar. E a reposição parte do número errado: repor +4 sobre
-3 dá 1, não 4.

O caminho do storefront sempre fez a coisa certa (validate_stock_for_checkout com
select_for_update antes de decrementar); o PDV tinha copiado só o UPDATE.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError

from apps.stores.api.serializers import StoreOrderCreateSerializer
from apps.stores.models import Store, StoreProduct

User = get_user_model()


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono_pdv', password='x')
    return Store.objects.create(owner=dono, name='Loja PDV', slug='loja-pdv-test')


def _produto(loja, estoque, backorder=False):
    return StoreProduct.objects.create(
        store=loja,
        name='Torta de Limão',
        price=Decimal('30.00'),
        status=StoreProduct.ProductStatus.ACTIVE,
        track_stock=True,
        stock_quantity=estoque,
        allow_backorder=backorder,
    )


def _payload(loja, produto, qtd):
    return {
        # `_resolve_store` resolve por UUID/slug em string, não pelo objeto.
        'store': str(loja.id),
        'items': [{'product_id': str(produto.id), 'quantity': qtd, 'options': {}, 'notes': ''}],
        'customer_name': 'Balcão',
        'customer_phone': '63999999999',
    }


def _cria(loja, produto, qtd):
    s = StoreOrderCreateSerializer()
    return s.create(_payload(loja, produto, qtd))


@pytest.mark.django_db
class TestEstoqueNoPDV:

    def test_venda_maior_que_o_estoque_e_recusada(self, loja):
        """O caso real: freezer tinha 5, sistema achava que tinha 2."""
        p = _produto(loja, estoque=2)
        with pytest.raises(ValidationError):
            _cria(loja, p, 5)
        p.refresh_from_db()
        assert p.stock_quantity == 2, 'estoque não pode ter sido tocado'
        assert p.stock_quantity >= 0

    def test_venda_dentro_do_estoque_passa_e_da_baixa(self, loja):
        p = _produto(loja, estoque=10)
        _cria(loja, p, 3)
        p.refresh_from_db()
        assert p.stock_quantity == 7

    def test_venda_exata_do_saldo_e_permitida(self, loja):
        p = _produto(loja, estoque=4)
        _cria(loja, p, 4)
        p.refresh_from_db()
        assert p.stock_quantity == 0

    def test_backorder_continua_podendo_estourar(self, loja):
        """Quem optou por vender sem estoque não pode ser bloqueado."""
        p = _produto(loja, estoque=1, backorder=True)
        _cria(loja, p, 5)
        p.refresh_from_db()
        assert p.stock_quantity == -4

    def test_produto_sem_track_stock_nao_e_validado(self, loja):
        p = _produto(loja, estoque=0)
        StoreProduct.objects.filter(pk=p.pk).update(track_stock=False)
        p.refresh_from_db()
        _cria(loja, p, 99)  # não deve levantar
