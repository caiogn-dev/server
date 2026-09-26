"""Endereço de Palmas digitado no WhatsApp: a quadra manda, não a alameda.

25/09, Cê Saladas: a cliente digitou "Na 307 norte Al 19 lote 53 sala 03".
O bot mandou o texto cru ao Google, que devolveu **Alameda 19, 53 — Plano
Diretor SUL** (14,1 km, R$ 19,30). O endereço real é na 307 NORTE (Arno,
~5 km, R$ 13,00). Reproduzido em 26/09: a mesma consulta normalizada —
"Quadra 307 Norte, Alameda 19, 53, Palmas - TO" — devolve o lugar certo.

Duas regras:
1. Quando o texto tem quadra + setor, a consulta ao geocodificador é montada
   com eles explícitos (Quadra N Setor, Alameda X, número).
2. O resultado precisa BATER com o setor digitado. Norte que volta como
   "Plano Diretor Sul" é resultado errado, não endereço — o bot pede de
   novo (ou a localização), em vez de cobrar frete de outra cidade.
"""
from django.test import SimpleTestCase

from apps.stores.services.endereco_de_palmas import (
    consulta_para_geocodificar,
    resultado_bate_com_o_setor,
)

TEXTO = 'Na 307 norte Al 19 lote 53 sala 03'


class ConsultaTest(SimpleTestCase):
    def test_monta_a_consulta_com_quadra_setor_alameda_e_numero(self):
        self.assertEqual(
            consulta_para_geocodificar(TEXTO),
            'Quadra 307 Norte, Alameda 19, 53, Palmas - TO',
        )

    def test_aceita_as_grafias_da_rua(self):
        for texto in ('307 Norte Alameda 19 lote 53', 'q 307 n al 19 lt 53', 'ARNO 307 norte, al. 19, lote 53'):
            self.assertEqual(consulta_para_geocodificar(texto), 'Quadra 307 Norte, Alameda 19, 53, Palmas - TO', texto)

    def test_sul_e_avenida(self):
        self.assertEqual(
            consulta_para_geocodificar('Quadra 304 Sul, Alameda 2, Lote 5'),
            'Quadra 304 Sul, Alameda 2, 5, Palmas - TO',
        )
        self.assertEqual(
            consulta_para_geocodificar('ARSE 72 rua 4 casa 3'),
            'Quadra 72 Sul, Rua 4, 3, Palmas - TO',
        )

    def test_sem_quadra_e_setor_devolve_o_texto_como_veio(self):
        self.assertEqual(consulta_para_geocodificar('Rua das Flores, 120, Taquaralto'), 'Rua das Flores, 120, Taquaralto')
        self.assertEqual(consulta_para_geocodificar('307 norte'), '307 norte')  # sem rua nem número: nada para montar


class SetorTest(SimpleTestCase):
    def test_norte_que_volta_sul_nao_bate(self):
        geo = {'formatted_address': 'Alameda 19, 53 - 03 - Plano Diretor Sul, Palmas - TO, Brasil'}
        self.assertFalse(resultado_bate_com_o_setor(TEXTO, geo))

    def test_norte_que_volta_norte_bate(self):
        geo = {'formatted_address': 'Q. 307 Norte Alameda 19, 53 - Arno, Palmas - TO, 77001-392, Brasil'}
        self.assertTrue(resultado_bate_com_o_setor(TEXTO, geo))

    def test_sem_setor_digitado_nao_ha_o_que_conferir(self):
        self.assertTrue(resultado_bate_com_o_setor('Rua das Flores 120', {'formatted_address': 'qualquer coisa Sul'}))
