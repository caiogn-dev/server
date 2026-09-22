"""Público montado por condição: campo, operador, valor.

Até 21/09 a audiência era um punhado de caixas fixas ("VIP", "inativos"). Quem
queria "pediu mais de 3 vezes E sumiu faz 30 dias E é do Plano Diretor" não
tinha como pedir — e é exatamente essa pergunta que vira campanha que vende.

O vocabulário vive aqui, em módulo puro: a tela LÊ os campos e operadores
daqui (não os copia), e o mesmo avaliador decide quem entra.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.campaigns.services import regras


def _perfil(pedidos=1, ticket='30.00', dias_desde_a_compra=5, bairro='Centro', produtos=()):
    return {
        'pedidos': pedidos,
        'ticket_medio': Decimal(ticket),
        'ultima_compra': timezone.now() - timedelta(days=dias_desde_a_compra),
        'bairro': bairro,
        'produtos': set(produtos),
    }


class TestCatalogo:
    def test_a_tela_descobre_os_campos_daqui(self):
        campos = {c['campo'] for c in regras.catalogo()}

        assert {'pedidos', 'ticket_medio', 'ultima_compra', 'bairro', 'produto'} <= campos

    def test_cada_campo_diz_quais_operadores_aceita(self):
        por_campo = {c['campo']: c for c in regras.catalogo()}

        assert 'maior_que' in por_campo['pedidos']['operadores']
        assert 'contem' in por_campo['bairro']['operadores']
        assert 'ha_mais_de' in por_campo['ultima_compra']['operadores']

    def test_campo_de_texto_nao_oferece_operador_de_numero(self):
        por_campo = {c['campo']: c for c in regras.catalogo()}

        assert 'maior_que' not in por_campo['bairro']['operadores']


class TestOperadores:
    def test_numero(self):
        p = _perfil(pedidos=4)

        assert regras.condicao_bate({'campo': 'pedidos', 'operador': 'maior_que', 'valor': 3}, p)
        assert not regras.condicao_bate({'campo': 'pedidos', 'operador': 'maior_que', 'valor': 4}, p)
        assert regras.condicao_bate({'campo': 'pedidos', 'operador': 'entre', 'valor': [2, 5]}, p)

    def test_texto_ignora_acento_e_caixa(self):
        p = _perfil(bairro='Plano Diretor Sul')

        assert regras.condicao_bate({'campo': 'bairro', 'operador': 'contem', 'valor': 'diretor'}, p)
        assert regras.condicao_bate({'campo': 'bairro', 'operador': 'comeca_com', 'valor': 'plano'}, p)
        assert regras.condicao_bate({'campo': 'bairro', 'operador': 'termina_com', 'valor': 'SUL'}, p)
        assert not regras.condicao_bate({'campo': 'bairro', 'operador': 'e_igual_a', 'valor': 'Centro'}, p)

    def test_data_em_dias(self):
        sumiu = _perfil(dias_desde_a_compra=40)

        assert regras.condicao_bate({'campo': 'ultima_compra', 'operador': 'ha_mais_de', 'valor': 30}, sumiu)
        assert not regras.condicao_bate({'campo': 'ultima_compra', 'operador': 'nos_ultimos', 'valor': 30}, sumiu)

    def test_quem_nunca_comprou_nao_bate_regra_de_compra(self):
        nunca = None

        assert not regras.condicao_bate({'campo': 'pedidos', 'operador': 'maior_que', 'valor': 0}, nunca)

    def test_produto_que_a_pessoa_ja_pediu(self):
        p = _perfil(produtos={'p1', 'p2'})

        assert regras.condicao_bate({'campo': 'produto', 'operador': 'ja_pediu', 'valor': ['p2']}, p)
        assert not regras.condicao_bate({'campo': 'produto', 'operador': 'nunca_pediu', 'valor': ['p2']}, p)
        assert regras.condicao_bate({'campo': 'produto', 'operador': 'nunca_pediu', 'valor': ['p9']}, p)


class TestGrupos:
    def test_condicoes_do_mesmo_grupo_somam_E(self):
        regra = {'grupos': [{'condicoes': [
            {'campo': 'pedidos', 'operador': 'maior_que', 'valor': 3},
            {'campo': 'bairro', 'operador': 'contem', 'valor': 'centro'},
        ]}]}

        assert regras.bate(regra, _perfil(pedidos=4, bairro='Centro'))
        assert not regras.bate(regra, _perfil(pedidos=4, bairro='Norte'))

    def test_grupos_diferentes_somam_OU(self):
        regra = {'grupos': [
            {'condicoes': [{'campo': 'pedidos', 'operador': 'maior_que', 'valor': 10}]},
            {'condicoes': [{'campo': 'bairro', 'operador': 'e_igual_a', 'valor': 'Centro'}]},
        ]}

        assert regras.bate(regra, _perfil(pedidos=1, bairro='Centro'))
        assert regras.bate(regra, _perfil(pedidos=20, bairro='Norte'))
        assert not regras.bate(regra, _perfil(pedidos=1, bairro='Norte'))

    def test_regra_vazia_aceita_todo_mundo(self):
        assert regras.bate({'grupos': []}, _perfil())
        assert regras.bate({}, _perfil())

    def test_condicao_incompleta_e_ignorada_em_vez_de_derrubar(self):
        """Tela em construção manda condição pela metade o tempo todo."""
        regra = {'grupos': [{'condicoes': [{'campo': 'pedidos', 'operador': 'maior_que'}]}]}

        assert regras.bate(regra, _perfil())


class TestExplicacao:
    def test_a_regra_vira_frase_para_o_lojista_conferir(self):
        regra = {'grupos': [{'condicoes': [
            {'campo': 'pedidos', 'operador': 'maior_que', 'valor': 3},
            {'campo': 'ultima_compra', 'operador': 'ha_mais_de', 'valor': 30},
        ]}]}

        frase = regras.em_portugues(regra)

        assert 'mais de 3 pedidos' in frase
        assert 'há mais de 30 dias' in frase
        assert ' e ' in frase
