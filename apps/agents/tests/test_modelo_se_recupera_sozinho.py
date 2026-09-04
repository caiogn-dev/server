"""A morte de um modelo não pode mais derrubar a IA.

QUATRO VEZES EM OITO SEMANAS o modelo default foi aposentado pelo provedor:

    15/jul  meta/llama-3.1-405b-instruct    saiu do catálogo
    26/ago  meta/llama-3.1-70b-instruct     410 Gone
    01/set  nvidia/nemotron-3-nano-30b-a3b  410 Gone
    03/set  openai/gpt-oss-120b             410 Gone

As três primeiras correções fizeram a mesma coisa: apontar para o próximo
nome à mão. Na quarta, o substituto escolhido em 01/set morreu dois dias
depois — e a escada de fallback passou a apontar para uma lápide, então tanto
o modelo pedido quanto o substituto devolviam 410. A IA caiu inteira.

Uma lista fixa de nomes bons é, por construção, uma lista que envelhece. O
provedor é quem sabe o que está vivo, e ele responde isso em `/v1/models`.

A REGRA NOVA: a preferência continua sendo escolha humana (foi MEDIDA com o
prompt real do painel — velocidade e JSON válido não se adivinham pelo nome),
mas quem estiver morto é pulado automaticamente. Um modelo aposentado vira uma
resposta um pouco pior, nunca uma tela vazia.

FALHA ABERTA de propósito: se a consulta ao catálogo falhar, o comportamento
antigo vale. Uma indisponibilidade momentânea da listagem não pode derrubar a
IA que ainda funcionaria.
"""
from unittest.mock import patch

import pytest

from apps.agents.runtime import modelos


@pytest.fixture(autouse=True)
def sem_cache():
    modelos.esquecer_catalogo()
    yield
    modelos.esquecer_catalogo()


def _catalogo(*vivos):
    return patch.object(modelos, 'catalogo_vivo', return_value=frozenset(vivos))


class TestPulaOQueMorreu:

    def test_usa_o_modelo_pedido_quando_ele_esta_vivo(self):
        with _catalogo('nvidia/nemotron-3-super-120b-a12b', 'outro/modelo'):
            assert modelos.modelo_vivo('outro/modelo') == 'outro/modelo'

    def test_modelo_morto_cai_para_a_melhor_preferencia_VIVA(self):
        """O caso de 03/set: o pedido morreu E o substituto fixo também."""
        with _catalogo('nvidia/nemotron-3-super-120b-a12b'):
            escolhido = modelos.modelo_vivo('openai/gpt-oss-120b')

        assert escolhido == 'nvidia/nemotron-3-super-120b-a12b'

    def test_respeita_a_ordem_medida_da_preferencia(self):
        """A ordem é resultado de medição, não de gosto — tem que ser seguida."""
        primeiro, segundo = modelos.PREFERENCIA[0], modelos.PREFERENCIA[1]

        with _catalogo(primeiro, segundo):
            assert modelos.modelo_vivo('morto/qualquer') == primeiro
        with _catalogo(segundo):
            assert modelos.modelo_vivo('morto/qualquer') == segundo

    def test_sem_pedido_tambem_escolhe_um_vivo(self):
        with _catalogo(modelos.PREFERENCIA[1]):
            assert modelos.modelo_vivo(None) == modelos.PREFERENCIA[1]

    def test_o_padrao_estatico_nao_e_mais_um_modelo_morto(self):
        """Peneira: o default do código não pode ser um nome já enterrado."""
        assert modelos.MODELO_PADRAO not in modelos.MODELOS_APOSENTADOS
        assert modelos.MODELO_PADRAO == modelos.PREFERENCIA[0]

    def test_nenhuma_preferencia_esta_na_lista_de_aposentados(self):
        for m in modelos.PREFERENCIA:
            assert m not in modelos.MODELOS_APOSENTADOS, f'{m} está morto e ainda é preferência'


class TestQuandoOCatalogoNaoResponde:
    """Falha aberta: listagem fora do ar não pode derrubar a IA."""

    def test_mantem_o_modelo_pedido(self):
        with patch.object(modelos, 'catalogo_vivo', return_value=None):
            assert modelos.modelo_vivo('algum/modelo') == 'algum/modelo'

    def test_ainda_recusa_quem_sabidamente_morreu(self):
        """A lista estática vira a única defesa — ela continua valendo."""
        with patch.object(modelos, 'catalogo_vivo', return_value=None):
            escolhido = modelos.modelo_vivo('nvidia/nemotron-3-nano-30b-a3b')

        assert escolhido == modelos.MODELO_PADRAO

    def test_nunca_levanta_excecao(self):
        """Tela quebrada é pior que resposta pior — em qualquer cenário."""
        with patch.object(modelos, 'catalogo_vivo', side_effect=RuntimeError('boom')):
            assert modelos.modelo_vivo('algum/modelo')


class TestCatalogo:

    def test_a_consulta_e_cacheada(self):
        """Uma chamada HTTP por pedido de modelo seria absurdo."""
        with patch.object(modelos, '_buscar_catalogo', return_value=frozenset({'a'})) as busca:
            modelos.catalogo_vivo()
            modelos.catalogo_vivo()
            modelos.catalogo_vivo()

        assert busca.call_count == 1

    def test_falha_de_rede_devolve_None_e_nao_explode(self):
        with patch.object(modelos, '_buscar_catalogo', side_effect=OSError('sem rede')):
            assert modelos.catalogo_vivo() is None

    def test_catalogo_vazio_conta_como_indisponivel(self):
        """Lista vazia é resposta estranha do provedor, não 'tudo morreu'.

        Tratá-la como verdade reprovaria TODO modelo e derrubaria a IA — o
        oposto do que este módulo existe para evitar.
        """
        with patch.object(modelos, '_buscar_catalogo', return_value=frozenset()):
            assert modelos.catalogo_vivo() is None
