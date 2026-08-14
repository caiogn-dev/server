"""Nada do que foi escrito hoje pode vazar catálogo entre lojas.

A plataforma é multi-tenant e hoje nasceram seis módulos novos que leem
catálogo: busca_de_produto, triagem, classificador, ficha_do_produto,
marca_da_loja e o comandos. Nenhum deles passou por auditoria.

O vazamento aqui não seria abstrato: o bot da Cê Saladas oferecendo prato da
Ivoneth, ou a ficha de um produto de outra loja respondida como se fosse da
casa.
"""
from decimal import Decimal

import pytest

from apps.stores.models import StoreProduct
from apps.stores.tests.factories import make_store


@pytest.fixture
def duas_lojas(db):
    a = make_store(name='Cê Saladas')
    b = make_store(name='Ivoneth')
    StoreProduct.objects.create(
        store=a, name='Salada Caesar', slug='caesar-a',
        price=Decimal('30'), is_active=True, status='active',
    )
    StoreProduct.objects.create(
        store=b, name='Coxinha de frango', slug='coxinha-b',
        price=Decimal('8'), is_active=True, status='active',
    )
    return a, b


class TestCasadorNaoAtravessaLoja:
    def test_nao_acha_produto_da_outra_loja(self, duas_lojas):
        from apps.stores.services.busca_de_produto import candidatos_de_produto

        a, _ = duas_lojas
        assert candidatos_de_produto(a, 'coxinha de frango') == []

    def test_acha_o_proprio(self, duas_lojas):
        from apps.stores.services.busca_de_produto import candidatos_de_produto

        a, _ = duas_lojas
        assert [p.name for p in candidatos_de_produto(a, 'salada caesar')] == ['Salada Caesar']

    def test_sem_loja_nao_devolve_nada(self, duas_lojas):
        """`store=None` não pode virar 'busca em tudo'."""
        from apps.stores.services.busca_de_produto import candidatos_de_produto

        assert candidatos_de_produto(None, 'salada') == []

    def test_disponiveis_sem_store_nao_e_usado_como_catalogo_de_loja(self, duas_lojas):
        """`disponiveis()` sem loja devolve a plataforma inteira — de propósito,
        para uso administrativo. O teste existe para deixar isso explícito: quem
        chamar sem `store` num contexto de cliente está vazando."""
        a, b = duas_lojas

        todos = set(StoreProduct.disponiveis().values_list('name', flat=True))

        assert {'Salada Caesar', 'Coxinha de frango'} <= todos
        assert set(StoreProduct.disponiveis(a).values_list('name', flat=True)) == {'Salada Caesar'}


class TestTriagemNaoAtravessaLoja:
    def test_produto_da_outra_loja_nao_vira_item(self, duas_lojas):
        from apps.automation.services.triagem import Intencao, triar

        a, _ = duas_lojas
        d = triar('quero uma coxinha de frango', store=a)

        assert d.intencao is not Intencao.ITEM, d
        assert d.itens == []


class TestClassificadorNaoVazaCatalogo:
    def test_prompt_leva_so_o_cardapio_da_loja(self, duas_lojas):
        from apps.automation.services.classificador import ClassificadorNIM

        a, _ = duas_lojas
        prompt = ClassificadorNIM()._prompt('oi', a, None)

        assert 'Salada Caesar' in prompt
        assert 'Coxinha' not in prompt, 'cardápio de outra loja foi para o modelo'
