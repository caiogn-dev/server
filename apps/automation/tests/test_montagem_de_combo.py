"""Montar combo pelo WhatsApp — o fluxo que o dono pediu e nunca existiu.

"montar pedidos com COMBOS (deve selecionar os sabores)" — 13/ago.

O buraco era maior que parecia: o `ProductMentionHandler` procura só em
`StoreProduct`, então COMBO NÃO EXISTIA PARA O BOT. Medido na Cê Saladas em
14/ago: "combo 5 saladas" — R$ 239,98, o item mais caro da loja — recebia
"😕 Não encontrei no cardápio".

Os dados aqui são os reais: 1 grupo, escolher 5, entre os 7 sabores da loja.
"""
import pytest

from apps.automation.services.montagem_de_combo import (
    Escolha, Grupo, Opcao, faltam, interpretar, resumo, texto_das_opcoes,
)

# Os 7 sabores da Cê Saladas, na ordem em que estão cadastrados.
SABORES = [
    Opcao('1', 'Queridinha'),
    Opcao('2', 'Especial Filé de Frango'),
    Opcao('3', 'Almôndega Premium'),
    Opcao('4', 'Basic Lombo'),
    Opcao('5', 'Tilápia Suprema'),
    Opcao('6', 'Magnifico Camarão'),
    Opcao('7', 'Salmão Sublime'),
]

COMBO5 = Grupo(titulo='Escolha suas 5 saladas', minimo=5, maximo=5, opcoes=SABORES)


class TestOClienteEscolhePorNumero:
    def test_lista_de_numeros(self):
        e = interpretar('1, 3, 5, 6, 7', COMBO5)

        assert [o.nome for o in e.selecionados] == [
            'Queridinha', 'Almôndega Premium', 'Tilápia Suprema',
            'Magnifico Camarão', 'Salmão Sublime',
        ]

    def test_numeros_sem_virgula(self):
        assert interpretar('1 2 3 4 5', COMBO5).quantidade == 5

    def test_numero_fora_da_lista_nao_e_engolido(self):
        """Escolher calado por um número que não existe entrega salada errada."""
        e = interpretar('1, 99', COMBO5)

        assert e.quantidade == 1
        assert e.nao_reconhecidos == ['99']


class TestOClienteEscolhePorNome:
    def test_nomes_soltos(self):
        e = interpretar('frango, camarão, salmão', COMBO5)

        assert [o.nome for o in e.selecionados] == [
            'Especial Filé de Frango', 'Magnifico Camarão', 'Salmão Sublime',
        ]

    def test_acento_nao_atrapalha(self):
        assert interpretar('tilapia', COMBO5).selecionados[0].nome == 'Tilápia Suprema'

    def test_nome_completo(self):
        assert interpretar('Almôndega Premium', COMBO5).quantidade == 1

    def test_nome_que_nao_existe_e_avisado(self):
        e = interpretar('frango, picanha', COMBO5)

        assert e.quantidade == 1
        assert 'picanha' in e.nao_reconhecidos[0]


class TestOClienteEscolhePorQuantidade:
    def test_dois_de_um_e_tres_de_outro(self):
        """"2 de frango e 3 de camarão" — como as pessoas realmente escrevem."""
        e = interpretar('2 de frango e 3 de camarão', COMBO5)

        assert e.quantidade == 5
        assert resumo(e) == '2x Especial Filé de Frango, 3x Magnifico Camarão'

    def test_com_x(self):
        assert interpretar('2x tilapia, 3x salmao', COMBO5).quantidade == 5

    def test_sem_preposicao(self):
        assert interpretar('2 frango, 3 camarao', COMBO5).quantidade == 5


class TestContarEObrigacao:
    """Fechar combo incompleto manda o pedido para a cozinha sem dizer o quê."""

    def test_faltando_avisa_quantos(self):
        assert faltam(interpretar('1, 2', COMBO5), COMBO5) == 3

    def test_completo_nao_falta_nada(self):
        assert faltam(interpretar('1,2,3,4,5', COMBO5), COMBO5) == 0

    def test_passou_do_limite_e_negativo(self):
        assert faltam(interpretar('1,2,3,4,5,6,7', COMBO5), COMBO5) == -2

    def test_nada_escolhido_falta_tudo(self):
        assert faltam(Escolha(), COMBO5) == 5

    def test_o_bot_NUNCA_completa_sozinho(self):
        """Completar "faltam 2" entrega salada que ninguém pediu."""
        e = interpretar('1, 2', COMBO5)

        assert e.quantidade == 2


class TestAPerguntaQueVaiProCliente:
    def test_lista_numerada_com_todos_os_sabores(self):
        t = texto_das_opcoes(COMBO5)

        assert '1. Queridinha' in t
        assert '7. Salmão Sublime' in t

    def test_diz_quantos_escolher(self):
        assert '*5*' in texto_das_opcoes(COMBO5)

    def test_faixa_quando_min_e_max_diferem(self):
        g = Grupo(titulo='Escolha', minimo=1, maximo=3, opcoes=SABORES)

        assert 'de *1* a *3*' in texto_das_opcoes(g)


class TestOQueNaoPodeAcontecer:
    def test_texto_vazio_nao_escolhe_nada(self):
        for vazio in ('', '   ', None):
            assert interpretar(vazio, COMBO5).quantidade == 0

    def test_repetir_o_mesmo_sabor_e_permitido(self):
        """"quero 5 de camarão" é pedido legítimo, não erro."""
        assert interpretar('5 de camarão', COMBO5).quantidade == 5

    def test_pedaco_de_palavra_nao_casa_sabor(self):
        """A lição do 'sem' dentro de 'sempre': casar substring escolhe errado."""
        assert interpretar('sal', COMBO5).nao_reconhecidos == ['sal']


class TestAConversaEmDoisTurnos:
    """A pergunta vai num turno e a resposta vem no outro.

    O estado mora no módulo, e não no handler, porque regra partida entre dois
    arquivos foi o que produziu as duas máquinas de estado divergentes de
    12/ago — cada uma decidindo diferente sobre o mesmo pedido.
    """

    def _combo(self):
        from unittest.mock import MagicMock
        c = MagicMock()
        c.id = 'combo-5'
        c.name = 'COMBO 5 SALADAS'
        c.price = '239.98'
        return c

    def test_iniciar_pergunta_e_guarda_estado(self):
        from apps.automation.services.montagem_de_combo import iniciar

        texto, estado = iniciar(self._combo(), [COMBO5])

        assert 'COMBO 5 SALADAS' in texto
        assert '1. Queridinha' in texto
        assert estado['escolhidos'] == []

    def test_combo_sem_escolha_vai_direto(self):
        from apps.automation.services.montagem_de_combo import iniciar

        _, estado = iniciar(self._combo(), [])

        assert estado is None

    def test_escolha_parcial_pede_o_que_falta(self):
        from apps.automation.services.montagem_de_combo import iniciar, responder

        _, estado = iniciar(self._combo(), [COMBO5])
        texto, estado = responder(estado, '1, 2', COMBO5)

        assert 'Faltam *3*' in texto
        assert estado is not None

    def test_a_escolha_ACUMULA_entre_os_turnos(self):
        """Sem acumular, o cliente recomeça do zero a cada mensagem."""
        from apps.automation.services.montagem_de_combo import iniciar, responder

        _, estado = iniciar(self._combo(), [COMBO5])
        _, estado = responder(estado, '1, 2', COMBO5)
        texto, estado = responder(estado, '3, 4, 5', COMBO5)

        assert estado is None
        assert 'Fechado' in texto

    def test_o_resumo_final_diz_o_que_vai_pra_cozinha(self):
        from apps.automation.services.montagem_de_combo import iniciar, responder

        _, estado = iniciar(self._combo(), [COMBO5])
        texto, _ = responder(estado, '2 de frango e 3 de camarão', COMBO5)

        assert 'Especial Filé de Frango' in texto
        assert 'Magnifico Camarão' in texto

    def test_palavra_desconhecida_e_avisada_sem_travar(self):
        from apps.automation.services.montagem_de_combo import iniciar, responder

        _, estado = iniciar(self._combo(), [COMBO5])
        texto, estado = responder(estado, '1, picanha', COMBO5)

        assert 'picanha' in texto
        assert 'Faltam *4*' in texto

    def test_passar_do_limite_NAO_corta_sozinho(self):
        """Cortar calado entrega salada que o cliente não pediu."""
        from apps.automation.services.montagem_de_combo import iniciar, responder

        _, estado = iniciar(self._combo(), [COMBO5])
        texto, estado = responder(estado, '1,2,3,4,5,6,7', COMBO5)

        assert 'Tira 2' in texto
        assert estado is not None
