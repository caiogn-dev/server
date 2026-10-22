"""Toda variável que o painel oferece é preenchida — ou some — em qualquer envio.

22/10: a Cê escreveu {website_url} na mensagem fora de horário e o cliente
recebeu as chaves cruas. O painel oferecia 20 variáveis; cada envio
preenchia um pedaço diferente delas.
"""
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.automation.variaveis import preencher, variaveis_da_loja


def _perfil(link='https://cardapidex.com.br/ce-saladas', horario=None):
    loja = SimpleNamespace(name='Cê Saladas', operating_hours=horario or {})
    return SimpleNamespace(
        company_name='Cê Saladas',
        link_do_cardapio=lambda: link,
        get_effective_store=lambda: loja,
    )


class VariaveisDaLojaTest(SimpleTestCase):
    def test_link_e_nome_vem_do_perfil(self):
        v = variaveis_da_loja(_perfil())
        self.assertEqual(v['website_url'], 'https://cardapidex.com.br/ce-saladas')
        self.assertEqual(v['menu_url'], 'https://cardapidex.com.br/ce-saladas')
        self.assertEqual(v['store_name'], 'Cê Saladas')


class PreencherTest(SimpleTestCase):
    def test_link_entra_mesmo_sem_estar_no_contexto_do_envio(self):
        texto = preencher('Olá {customer_name}! Peça: {website_url}', {'customer_name': 'Ana'}, _perfil())
        self.assertEqual(texto, 'Olá Ana! Peça: https://cardapidex.com.br/ce-saladas')

    def test_variavel_do_painel_sem_dado_some_em_vez_de_sair_crua(self):
        texto = preencher('Código: {pix_code}.', {}, _perfil())
        self.assertEqual(texto, 'Código: .')

    def test_contexto_vazio_nao_apaga_o_valor_da_loja(self):
        texto = preencher('{website_url}', {'website_url': ''}, _perfil())
        self.assertEqual(texto, 'https://cardapidex.com.br/ce-saladas')

    def test_chave_que_o_painel_nao_conhece_fica_para_o_dono_ver(self):
        self.assertEqual(preencher('{site}', {}, _perfil()), '{site}')

    def test_sem_perfil_nao_quebra(self):
        self.assertEqual(preencher('Oi {customer_name}', {'customer_name': 'Ana'}, None), 'Oi Ana')
