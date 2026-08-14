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

COMBO5 = Grupo(titulo='Escolha suas 5 saladas', minimo=5, maximo=5, opcoes=SABORES,
               id_do_grupo='grupo-1')


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
        r = responder(estado, '1, 2', COMBO5)

        assert 'Faltam *3*' in r.texto
        assert r.estado is not None

    def test_a_escolha_ACUMULA_entre_os_turnos(self):
        """Sem acumular, o cliente recomeça do zero a cada mensagem."""
        from apps.automation.services.montagem_de_combo import iniciar, responder

        _, estado = iniciar(self._combo(), [COMBO5])
        estado = responder(estado, '1, 2', COMBO5).estado
        r = responder(estado, '3, 4, 5', COMBO5)

        assert r.estado is None
        assert 'Fechado' in r.texto

    def test_o_resumo_final_diz_o_que_vai_pra_cozinha(self):
        from apps.automation.services.montagem_de_combo import iniciar, responder

        _, estado = iniciar(self._combo(), [COMBO5])
        r = responder(estado, '2 de frango e 3 de camarão', COMBO5)

        assert 'Especial Filé de Frango' in r.texto
        assert 'Magnifico Camarão' in r.texto

    def test_palavra_desconhecida_e_avisada_sem_travar(self):
        from apps.automation.services.montagem_de_combo import iniciar, responder

        _, estado = iniciar(self._combo(), [COMBO5])
        r = responder(estado, '1, picanha', COMBO5)

        assert 'picanha' in r.texto
        assert 'Faltam *4*' in r.texto

    def test_passar_do_limite_NAO_corta_sozinho(self):
        """Cortar calado entrega salada que o cliente não pediu."""
        from apps.automation.services.montagem_de_combo import iniciar, responder

        _, estado = iniciar(self._combo(), [COMBO5])
        r = responder(estado, '1,2,3,4,5,6,7', COMBO5)

        assert 'Tira 2' in r.texto
        assert r.estado is not None


class TestOComboVAIProCarrinho:
    """O último passo: a escolha confirmada vira linha de pedido.

    Sem isto o bot conduzia a escolha inteira, dizia "Fechado!" e o combo
    sumia — a conversa toda terminava em nada. O formato é o que
    `create_order_from_whatsapp` já aceita desde 10/ago: `combo_id` +
    `group_selections`, com a REPETIÇÃO na lista virando quantidade.
    """

    def _pronto(self, resposta_do_cliente='1,2,3,4,5'):
        from unittest.mock import MagicMock
        from apps.automation.services.montagem_de_combo import iniciar, responder

        combo = MagicMock()
        combo.id = 'combo-5'
        combo.name = 'COMBO 5 SALADAS'
        combo.price = '239.98'
        _, estado = iniciar(combo, [COMBO5])
        return responder(estado, resposta_do_cliente, COMBO5)

    def test_devolve_a_linha_do_carrinho(self):
        assert self._pronto().item is not None

    def test_no_formato_que_o_pedido_aceita(self):
        item = self._pronto().item

        assert item['combo_id'] == 'combo-5'
        assert item['quantity'] == 1
        assert 'group_selections' in item

    def test_as_escolhas_vao_indexadas_pelo_GRUPO(self):
        """`group_selections` é {grupo: [produtos]} — chave errada perde tudo."""
        item = self._pronto().item

        assert list(item['group_selections'].keys()) == ['grupo-1']

    def test_manda_os_cinco_sabores(self):
        assert len(self._pronto().item['group_selections']['grupo-1']) == 5

    def test_repeticao_vira_quantidade_no_pedido(self):
        """"5 de camarão" são cinco ids iguais — é assim que o checkout conta."""
        ids = self._pronto('5 de camarão').item['group_selections']['grupo-1']

        assert len(ids) == 5
        assert len(set(ids)) == 1

    def test_montagem_incompleta_NAO_devolve_item(self):
        """Combo pela metade no carrinho vai pra cozinha sem dizer o quê."""
        assert self._pronto('1, 2').item is None

    def test_passar_do_limite_tambem_nao_devolve_item(self):
        assert self._pronto('1,2,3,4,5,6,7').item is None
