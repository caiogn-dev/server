"""Pedaço de palavra não é nome de produto.

16/10, Cê Saladas: com o pedido esperando observação, a cliente mandou "Olá" e
o bot respondeu "Ah, você quer *Cebola roxa*? Isso é um item, não uma
observação". `_casa` fazia `alvo in nome` por substring, e "ola" está dentro de
"cebOLA". O casamento por trecho tem que respeitar palavra inteira.
"""
import pytest

from apps.stores.models import StoreProduct
from apps.stores.services.busca_de_produto import candidatos_de_produto, parece_pedido_de_produto
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    store = make_store(name='Cê Saladas Saudação')
    for nome in ('Cebola roxa', 'Suco de laranja 400ml', 'Salada Caesar'):
        StoreProduct.objects.create(
            store=store, name=nome, slug=nome.lower().replace(' ', '-'), price=10, is_active=True,
        )
    return store


@pytest.mark.parametrize('texto', ['Olá', 'ola', 'oi', 'Bom dia', 'sal'])
def test_pedaco_de_palavra_nao_vira_produto(loja, texto):
    assert parece_pedido_de_produto(loja, texto) is None
    assert candidatos_de_produto(loja, texto) == []


def test_palavra_inteira_e_nome_completo_continuam_casando(loja):
    assert parece_pedido_de_produto(loja, 'cebola').name == 'Cebola roxa'
    assert parece_pedido_de_produto(loja, 'quero suco de laranja 400ml').name == 'Suco de laranja 400ml'
    assert parece_pedido_de_produto(loja, 'quero salada').name == 'Salada Caesar'
