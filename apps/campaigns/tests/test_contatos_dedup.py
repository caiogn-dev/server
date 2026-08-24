"""Regressão: a lista de contatos do sistema contava a mesma pessoa duas vezes.

`SystemContactsView` juntava conversas + pedidos + inscritos + sessões e
deduplicava pela STRING CRUA do telefone. Só que o mesmo cliente aparece
gravado em formatos diferentes conforme a origem:

    pedido      -> '63984289103'      (sem DDI, COM o nono dígito)
    conversa    -> '556384289103'     (com DDI, SEM o nono dígito — wa_id antigo)

Resultado: a Cê Saladas mostrava ~292 "clientes" quando só 58 telefones
distintos já tinham feito pedido. Pior, o número sem o `55` é enviado assim
para a Meta e falha.

Correção: chavear pelo telefone normalizado (E.164 sem '+') e, no encontro de
duplicatas, manter a origem mais forte (quem comprou vale mais que quem só
conversou) e o primeiro nome não vazio.
"""
from django.test import SimpleTestCase

from apps.campaigns.services.contatos import (
    PRIORIDADE_DE_ORIGEM,
    chave_do_telefone,
    contatos_para_resposta,
    mesclar_contato,
)


class ChaveDoTelefoneTests(SimpleTestCase):
    def test_mesmo_numero_em_formatos_diferentes_gera_a_mesma_chave(self):
        self.assertEqual(
            chave_do_telefone('63984289103'),
            chave_do_telefone('556384289103'),
        )

    def test_mascara_e_ddi_com_mais_nao_atrapalham(self):
        self.assertEqual(
            chave_do_telefone('+55 (63) 98428-9103'),
            chave_do_telefone('556384289103'),
        )

    def test_chave_nao_serve_para_envio_e_por_isso_colapsa_o_nono(self):
        self.assertEqual(chave_do_telefone('63984289103'), '556384289103')

    def test_numero_estrangeiro_nao_ganha_ddi_55(self):
        # wa_id da Espanha: colar '55' na frente inventa um número inexistente
        self.assertEqual(chave_do_telefone('34647520824'), '34647520824')

    def test_telefone_vazio_nao_gera_chave(self):
        self.assertEqual(chave_do_telefone(''), '')
        self.assertEqual(chave_do_telefone(None), '')


class MesclarContatoTests(SimpleTestCase):
    def test_duas_origens_do_mesmo_numero_viram_um_contato_so(self):
        contatos = {}
        mesclar_contato(contatos, '556384289103', 'Ana', 'conversation')
        mesclar_contato(contatos, '63984289103', 'Ana Paula', 'order')

        self.assertEqual(len(contatos), 1)

    def test_telefone_exposto_sai_normalizado_com_ddi(self):
        contatos = {}
        mesclar_contato(contatos, '63984289103', 'Ana', 'order')

        (contato,) = contatos.values()
        self.assertEqual(contato['phone'], '5563984289103')

    def test_wa_id_da_conversa_vence_o_telefone_do_pedido_no_envio(self):
        contatos = {}
        mesclar_contato(contatos, '63984289103', 'Ana', 'order')
        mesclar_contato(contatos, '556384289103', 'Ana', 'conversation')

        (contato,) = contatos.values()
        self.assertEqual(contato['phone'], '556384289103')

    def test_wa_id_ja_registrado_nao_e_trocado_por_outro_formato(self):
        contatos = {}
        mesclar_contato(contatos, '556384289103', 'Ana', 'conversation')
        mesclar_contato(contatos, '63984289103', 'Ana', 'order')

        (contato,) = contatos.values()
        self.assertEqual(contato['phone'], '556384289103')

    def test_comprador_vence_quem_so_conversou(self):
        contatos = {}
        mesclar_contato(contatos, '556384289103', 'Ana', 'conversation')
        mesclar_contato(contatos, '63984289103', 'Ana', 'order')

        (contato,) = contatos.values()
        self.assertEqual(contato['source'], 'order')

    def test_origem_mais_fraca_nao_rebaixa_a_mais_forte(self):
        contatos = {}
        mesclar_contato(contatos, '63984289103', 'Ana', 'order')
        mesclar_contato(contatos, '556384289103', 'Ana', 'conversation')

        (contato,) = contatos.values()
        self.assertEqual(contato['source'], 'order')

    def test_nome_vazio_e_preenchido_pela_outra_origem(self):
        contatos = {}
        mesclar_contato(contatos, '556384289103', '', 'conversation')
        mesclar_contato(contatos, '63984289103', 'Ana Paula', 'order')

        (contato,) = contatos.values()
        self.assertEqual(contato['name'], 'Ana Paula')

    def test_nome_existente_nao_e_sobrescrito(self):
        contatos = {}
        mesclar_contato(contatos, '556384289103', 'Ana', 'conversation')
        mesclar_contato(contatos, '63984289103', 'ANA PAULA DA SILVA', 'order')

        (contato,) = contatos.values()
        self.assertEqual(contato['name'], 'Ana')

    def test_telefone_vazio_e_ignorado(self):
        contatos = {}
        mesclar_contato(contatos, '', 'Sem telefone', 'order')

        self.assertEqual(contatos, {})

    def test_comprador_tem_prioridade_maior_que_conversa(self):
        self.assertGreater(
            PRIORIDADE_DE_ORIGEM['order'],
            PRIORIDADE_DE_ORIGEM['conversation'],
        )


class ContatosParaRespostaTests(SimpleTestCase):
    def test_campo_interno_de_controle_nao_vaza_na_api(self):
        contatos = {}
        mesclar_contato(contatos, '556384289103', 'Ana', 'conversation')

        (contato,) = contatos_para_resposta(contatos, 10)
        self.assertEqual(set(contato), {'phone', 'name', 'source'})

    def test_limite_e_respeitado(self):
        contatos = {}
        for i in range(5):
            mesclar_contato(contatos, f'5563984289{100 + i}', '', 'order')

        self.assertEqual(len(contatos_para_resposta(contatos, 3)), 3)
