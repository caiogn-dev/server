"""Apelidos: o nome que o cliente usa, gravado pelo dono.

O cliente da Cê Saladas não escreve "Salada Premium Nº 3" — escreve "filé
especial", que é como a loja chama no balcão. A tela "ensinar" do painel grava
esses apelidos em `StoreProduct.metadata['apelidos']` (lista de strings); o
casamento do bot tem que considerá-los como se fossem o nome.

O campo `metadata` do StoreProduct chegou com a migração 0089 (commit
6c5b153b). Até lá o teste simulava o campo com um `property` na classe; com o
campo real, o Django não consegue mais instanciar o produto vindo do banco
("property ... has no setter") — então os apelidos agora são gravados no campo.
"""
import pytest

from apps.stores.models import StoreProduct
from apps.stores.services.busca_de_produto import candidatos_de_produto, casar_produto
from apps.stores.services.leitura_do_pedido import ler_pedido
from apps.stores.tests.factories import make_store

METADATA = {
    'premium-3': {'apelidos': ['filé especial', 'a da casa']},
    'suco': {'apelidos': None},
}


@pytest.fixture
def loja(db):
    store = make_store(name='Cê Saladas Apelidos')
    StoreProduct.objects.create(store=store, name='Salada Premium Nº 3', slug='premium-3', price=39.99,
                                is_active=True, metadata=METADATA['premium-3'])
    StoreProduct.objects.create(store=store, name='Suco de laranja', slug='suco', price=9,
                                is_active=True, metadata=METADATA['suco'])
    return store


def test_apelido_casa_o_produto(loja):
    assert [o.name for o in candidatos_de_produto(loja, 'quero um filé especial')] == ['Salada Premium Nº 3']
    assert casar_produto(loja, 'filé especial').name == 'Salada Premium Nº 3'


def test_apelido_entra_no_pedido_digitado_com_quantidade(loja):
    leitura = ler_pedido(loja, 'vou querer 2 filé especial e 1 suco de laranja')

    assert [(o.name, q) for o, q in leitura.itens] == [('Salada Premium Nº 3', 2), ('Suco de laranja', 1)]


def test_apelidos_vazios_nao_quebram(loja):
    assert [o.name for o in candidatos_de_produto(loja, 'suco')] == ['Suco de laranja']
