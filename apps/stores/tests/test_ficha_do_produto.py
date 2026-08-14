"""O bot não fala de receita que ele não sabe.

Regra do dono, 13/ago: o bot **não pode falar sobre uma receita que ele não
sabe, nem sobre ingrediente que não tem cadastrado**.

Não é preciosismo. Medido no catálogo real:

    ce-saladas    41 produtos · 34 com descrição · 7 SEM
    pastita       11 produtos ·  9 com descrição · 2 SEM
    ivoneth       57 produtos · 53 com descrição · 4 SEM

"Combo Camarão" e "suco 1" estão com a descrição VAZIA. Perguntado "o que vem
no Combo Camarão?", nada hoje impede o modelo de responder "camarão, alface,
tomate e molho especial" — e o cliente receber outra coisa. Numa loja de
comida, inventar ingrediente não é alucinação inofensiva: é risco de alergia.

Contrato: a ficha devolve SÓ o que está cadastrado, e diz explicitamente
quando não sabe. Quem responde ao cliente é obrigado a passar por aqui.
"""
import pytest

from apps.stores.services.ficha_do_produto import ficha, texto_seguro
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    return make_store(name='Cê Saladas')


def _produto(loja, nome, **kw):
    from apps.stores.models import StoreProduct

    return StoreProduct.objects.create(
        store=loja, name=nome, slug=nome.lower().replace(' ', '-'),
        price=kw.pop('price', 25), is_active=True, **kw,
    )


class TestQuandoSabe:
    def test_descricao_cadastrada_vem_literal(self, loja):
        p = _produto(loja, 'Tropical do Cê', description='Frango 120g, abacaxi 70g')

        f = ficha(p)

        assert f.sabe_composicao is True
        assert 'abacaxi 70g' in f.composicao

    def test_nao_reescreve_nem_resume_o_que_o_lojista_escreveu(self, loja):
        """Reescrever é o primeiro passo para inventar."""
        texto = 'Alface americana, tomate cereja e 3 colheres de grão-de-bico'
        p = _produto(loja, 'Salada X', description=texto)

        assert ficha(p).composicao == texto


class TestQuandoNaoSabe:
    def test_descricao_vazia_admite_que_nao_sabe(self, loja):
        """'Combo Camarão' está assim no catálogo real."""
        p = _produto(loja, 'Combo Camarão', description='')

        f = ficha(p)

        assert f.sabe_composicao is False
        assert not f.composicao

    def test_so_espaco_em_branco_tambem_e_nao_saber(self, loja):
        p = _produto(loja, 'suco 1', description='   \n  ')

        assert ficha(p).sabe_composicao is False

    def test_texto_seguro_nao_inventa_e_oferece_saida(self, loja):
        """Sem dado, a resposta honesta é admitir e chamar gente."""
        p = _produto(loja, 'Combo Camarão', description='')

        resposta = texto_seguro(p, 'o que vem nesse?')

        assert 'não tenho' in resposta.lower() or 'nao tenho' in resposta.lower()
        assert 'Combo Camarão' in resposta

    def test_texto_seguro_nunca_lista_ingrediente_inventado(self, loja):
        """Ecoar o NOME cadastrado é correto — o cliente precisa saber do que
        estamos falando. O que não pode é aparecer ingrediente que ninguém
        cadastrou."""
        p = _produto(loja, 'Combo Camarão', description='')

        resposta = texto_seguro(p, 'tem alface?').lower()

        for inventado in ('alface', 'tomate', 'molho', 'cebola', 'frango'):
            assert inventado not in resposta, inventado


class TestAlergenico:
    def test_alergenico_so_aparece_se_cadastrado(self, loja):
        p = _produto(loja, 'Salada Y', description='alface e tomate')

        f = ficha(p)

        assert f.sabe_alergenicos is False
        assert f.alergenicos == []

    def test_pergunta_de_alergia_sem_dado_nao_afirma_que_nao_tem(self, loja):
        """"Tem glúten?" respondido com "não" sem dado é o pior caso possível.

        Numa loja de comida, afirmar ausência de alérgeno sem base é risco de
        saúde — muito pior que não responder.
        """
        p = _produto(loja, 'Salada Y', description='alface e tomate')

        resposta = texto_seguro(p, 'tem glúten?').lower()

        assert not resposta.strip().startswith('não')
        assert 'confirmo' in resposta or 'confirmar' in resposta


class TestProdutoQueNaoExiste:
    def test_sem_produto_nao_ha_ficha(self, loja):
        assert ficha(None).sabe_composicao is False

    def test_texto_seguro_sem_produto_nao_descreve_nada(self, loja):
        resposta = texto_seguro(None, 'o que vem na lasanha de camarão?')

        assert 'camarão' not in resposta.lower()
