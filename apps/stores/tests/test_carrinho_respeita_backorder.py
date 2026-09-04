"""Vender sem estoque é uma decisão do lojista, e o carrinho tem que obedecer.

O CASO REAL (04/09, Cê Saladas): clientes não conseguiam adicionar molho à
sacola. "Erro ao adicionar à sacola" e o pedido morria ali.

O produto "Molho" estava com `stock_quantity=996` e `allow_backorder=True` —
o dono dizendo, de duas formas, que molho é item de reposição contínua e
sempre pode ser vendido. Mas as VARIANTES (os sabores) tinham estoque próprio,
e duas delas estavam em zero: "Mostarda e mel" e "Lemon Pepper". Metade do
cardápio de molhos travava a venda inteira.

A CAUSA: `add_to_cart` checa `track_stock` e compara com o estoque, e nunca lê
`allow_backorder`. A flag existe no modelo, aparece no painel, e não era
consultada em lugar nenhum na hora de adicionar — o lojista marcava e nada
acontecia.

Duas regras aqui:

1. `allow_backorder` do PRODUTO vale para as variantes dele. Sabor é atributo
   do molho, não um produto separado com política própria de estoque — quem
   marcou "pode vender sem estoque" no molho não vai marcar de novo em cada
   sabor, e não teria como: a variante nem tem esse campo.

2. Sem `allow_backorder`, a trava continua valendo. Item que acaba de verdade
   (a salada de salmão do dia) tem que parar de ser vendido, senão o cliente
   paga por comida que não existe.
"""
from decimal import Decimal

import pytest

from apps.stores.models import (
    Store, StoreCart, StoreCategory, StoreProduct, StoreProductVariant,
)
from apps.stores.services import cart_service


@pytest.fixture
def loja(db):
    from django.contrib.auth import get_user_model
    dono = get_user_model().objects.create_user(
        username='dono-backorder', email='d@t.local', password='x',
    )
    return Store.objects.create(
        owner=dono, name='Cê Teste', slug='ce-teste-backorder',
        store_type='food', status='active',
    )


@pytest.fixture
def categoria(loja):
    return StoreCategory.objects.create(store=loja, name='Molhos', slug='molhos')


def _molho(loja, categoria, *, backorder: bool, estoque_produto=996):
    """O molho da Cê: estoque alto no produto e reposição contínua."""
    return StoreProduct.objects.create(
        store=loja, category=categoria, name='Molho', slug='molho',
        price=Decimal('5.00'), status='active',
        track_stock=True, stock_quantity=estoque_produto,
        allow_backorder=backorder,
    )


def _sabor(produto, nome, estoque):
    return StoreProductVariant.objects.create(
        product=produto, name=nome, price=Decimal('5.00'), stock_quantity=estoque,
    )


@pytest.fixture
def carrinho(loja):
    return StoreCart.objects.create(store=loja, session_key='sess-backorder')


@pytest.mark.django_db
class TestBackorderDoProdutoValeParaOSabor:

    def test_sabor_zerado_entra_quando_o_produto_permite(self, loja, categoria, carrinho):
        """O caso da cliente: escolheu 'Mostarda e mel', que estava em 0."""
        molho = _molho(loja, categoria, backorder=True)
        zerado = _sabor(molho, 'Mostarda e mel', 0)

        item = cart_service.add_item(carrinho, molho.id, 1, variant_id=zerado.id)

        assert item.quantity == 1
        assert carrinho.items.count() == 1

    def test_sabor_com_estoque_segue_entrando(self, loja, categoria, carrinho):
        molho = _molho(loja, categoria, backorder=True)
        com = _sabor(molho, 'Red Pepper', 6)

        assert cart_service.add_item(carrinho, molho.id, 1, variant_id=com.id).quantity == 1


@pytest.mark.django_db
class TestSemBackorderATravaContinua:
    """A trava existe por um motivo: comida que acabou não pode ser vendida."""

    def test_sabor_zerado_e_recusado(self, loja, categoria, carrinho):
        molho = _molho(loja, categoria, backorder=False)
        zerado = _sabor(molho, 'Mostarda e mel', 0)

        with pytest.raises(ValueError, match='Estoque insuficiente'):
            cart_service.add_item(carrinho, molho.id, 1, variant_id=zerado.id)

    def test_nao_deixa_passar_do_que_existe(self, loja, categoria, carrinho):
        molho = _molho(loja, categoria, backorder=False)
        pouco = _sabor(molho, 'Maracujá', 2)

        cart_service.add_item(carrinho, molho.id, 2, variant_id=pouco.id)
        with pytest.raises(ValueError, match='Estoque insuficiente'):
            cart_service.add_item(carrinho, molho.id, 1, variant_id=pouco.id)

    def test_produto_sem_variante_tambem_respeita_o_backorder(self, loja, categoria, carrinho):
        """Não é regra só de variante: vale para o produto simples também."""
        esgotado = StoreProduct.objects.create(
            store=loja, category=categoria, name='Suco', slug='suco',
            price=Decimal('8.00'), status='active',
            track_stock=True, stock_quantity=0, allow_backorder=True,
        )

        assert cart_service.add_item(carrinho, esgotado.id, 1).quantity == 1


@pytest.mark.django_db
class TestOCaminhoInteiroAteOCheckout:
    """Deixar entrar na sacola e reprovar depois é pior que recusar na hora.

    O `add` era só a primeira porta. Mudar a quantidade e a validação que roda
    ANTES do checkout contavam estoque do mesmo jeito — a cliente colocaria o
    molho, e o pedido morreria no pagamento, sem entender por quê.
    """

    def test_aumentar_a_quantidade_do_sabor_zerado(self, loja, categoria, carrinho):
        molho = _molho(loja, categoria, backorder=True)
        zerado = _sabor(molho, 'Lemon Pepper', 0)
        item = cart_service.add_item(carrinho, molho.id, 1, variant_id=zerado.id)

        atualizado = cart_service.update_item_quantity(carrinho, item.id, 3)

        assert atualizado.quantity == 3

    def test_carrinho_com_sabor_zerado_passa_na_validacao(self, loja, categoria, carrinho):
        """Esta é a peneira que roda no checkout."""
        molho = _molho(loja, categoria, backorder=True)
        zerado = _sabor(molho, 'Mostarda e mel', 0)
        cart_service.add_item(carrinho, molho.id, 2, variant_id=zerado.id)

        erros = cart_service.validate_stock_for_checkout(carrinho)

        assert erros == []

    def test_sem_backorder_a_validacao_reprova(self, loja, categoria, carrinho):
        molho = _molho(loja, categoria, backorder=True)
        zerado = _sabor(molho, 'Mostarda e mel', 0)
        cart_service.add_item(carrinho, molho.id, 1, variant_id=zerado.id)

        # O lojista desliga a venda sem estoque depois que o item já está na
        # sacola: agora a peneira do checkout tem que pegar.
        molho.allow_backorder = False
        molho.save(update_fields=['allow_backorder'])

        erros = cart_service.validate_stock_for_checkout(carrinho)

        assert len(erros) == 1
        assert 'Estoque insuficiente' in erros[0]['error']
