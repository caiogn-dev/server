"""O agente não pode inventar composição — nem por omissão.

Regra do dono (13/ago): o bot não fala sobre receita que não sabe nem sobre
ingrediente que não tem cadastrado.

A tool `detalhes_do_produto` já não inventava, mas fazia algo pior de forma
sutil: quando a descrição estava vazia, ela **omitia a linha**. Para um modelo
de linguagem, ausência de dado lê como permissão para preencher com o que ele
"sabe" de saladas em geral. Um "não cadastrado" explícito lê como proibição.

7 dos 41 produtos ativos da Cê Saladas estão sem descrição — "Combo Camarão" e
"suco 1" entre eles. Numa loja de comida, ingrediente inventado é risco de
alergia, não deslize de texto.
"""
from django.test import TestCase

from apps.stores.models import StoreProduct
from apps.stores.tests.factories import make_store


class AgenteNaoInventaReceitaTest(TestCase):
    def setUp(self):
        self.store = make_store(name='Cê Saladas')

    def _servico(self):
        from apps.agents.models import Agent
        from apps.agents.services.langchain_service import LangchainService

        agente = Agent.objects.create(
            name='Teste', provider=Agent.AgentProvider.NVIDIA,
            model_name='meta/llama-3.1-8b-instruct',
        )
        return LangchainService(agente)

    def test_sem_descricao_a_tool_DIZ_que_nao_sabe(self):
        p = StoreProduct.objects.create(
            store=self.store, name='Combo Camarão', slug='combo-camarao',
            price=90, is_active=True, description='',
        )

        texto = self._servico()._descrever_produto(p).lower()

        assert 'nao cadastrada' in texto or 'não cadastrada' in texto, texto

    def test_com_descricao_nao_muda_nada(self):
        p = StoreProduct.objects.create(
            store=self.store, name='Tropical', slug='tropical', price=30,
            is_active=True, description='Frango 120g, abacaxi 70g',
        )

        texto = self._servico()._descrever_produto(p)

        assert 'abacaxi 70g' in texto
        assert 'não cadastrada' not in texto.lower()


class PromptProibeInventarTest(TestCase):
    """A tool avisa, mas o prompt precisa PROIBIR.

    A tool que diz "não cadastrada" resolve o caso em que ela é chamada. O
    prompt cobre o resto: deduzir composição pelo nome do prato, e — o mais
    perigoso — responder "não tem glúten" sem dado nenhum.
    """

    def test_prompt_proibe_descrever_sem_dado(self):
        from apps.agents.graph import nodes

        fonte = open(nodes.__file__, encoding='utf-8').read()

        assert 'NÃO INVENTE RECEITA' in fonte
        assert 'NÃO CADASTRADA' in fonte

    def test_prompt_trata_alergenico_como_caso_a_parte(self):
        from apps.agents.graph import nodes

        fonte = open(nodes.__file__, encoding='utf-8').read()

        assert 'ALÉRGENO' in fonte
        assert 'glúten' in fonte.lower() or 'gluten' in fonte.lower()
