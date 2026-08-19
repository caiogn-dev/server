"""normalize_phone_number não pode transformar estrangeiro em brasileiro.

A regra era "sem 55 e até 11 dígitos → gruda 55". Um celular espanhol completo
(34 + 9 dígitos = 11) e um americano (1 + 10 = 11) passam nessa peneira e viram
números que não existem.

Custo real: a conversa da Layane (wa_id 34647520824, Espanha) virou
5534647520824. Toda resposta do inbox falhou com 131026 "Message undeliverable"
enquanto ela perguntava "vcs estão aceitando pedidos?". As respostas do BOT
chegavam, porque o bot usa o from_number da mensagem em vez do phone_number da
conversa.

O que separa: celular BR de 11 dígitos tem 9 na terceira posição (DDD + 9XXXXXXXX).
"""
from django.test import TestCase

from apps.core.utils import normalize_phone_number


class NumeroBrasileiroTests(TestCase):
    def test_celular_com_ddd_ganha_ddi(self):
        self.assertEqual(normalize_phone_number('63992509193'), '5563992509193')
        self.assertEqual(normalize_phone_number('11987654321'), '5511987654321')

    def test_fixo_com_ddd_ganha_ddi(self):
        self.assertEqual(normalize_phone_number('6332151234'), '556332151234')

    def test_formatado_continua_funcionando(self):
        self.assertEqual(normalize_phone_number('(63) 99250-9193'), '5563992509193')
        self.assertEqual(normalize_phone_number('+55 63 99250-9193'), '5563992509193')

    def test_ja_com_ddi_nao_duplica(self):
        self.assertEqual(normalize_phone_number('5563992509193'), '5563992509193')


class NumeroEstrangeiroTests(TestCase):
    def test_espanha_da_layane_nao_vira_brasileiro(self):
        self.assertEqual(normalize_phone_number('34647520824'), '34647520824')

    def test_eua_nao_vira_brasileiro(self):
        self.assertEqual(normalize_phone_number('15554044637'), '15554044637')

    def test_nenhum_estrangeiro_ganha_55(self):
        for numero in ['34647520824', '15554044637', '351912345678', '4915112345678']:
            self.assertFalse(
                normalize_phone_number(numero).startswith('55') and len(numero) == 11
                and numero[2] != '9',
                f'{numero} foi transformado em brasileiro',
            )
