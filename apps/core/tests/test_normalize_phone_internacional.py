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


class DDIExplicitoTests(TestCase):
    """Com '+' na frente, o DDI é uma AFIRMAÇÃO do cliente — nunca um palpite.

    A heurística de tamanho não alcança estes: um celular espanhol digitado
    como '+34 647 52 08 24' tem 9 dígitos locais, e um português '+351 912
    345 678' tem 9 também. Ambos caem fora da peneira 10-11 e, pior, o
    checkout barrava com "Celular inválido" antes mesmo de chegar aqui.
    """

    def test_espanha_com_mais_e_espacos(self):
        self.assertEqual(normalize_phone_number('+34 647 52 08 24'), '34647520824')

    def test_portugal_com_mais(self):
        self.assertEqual(normalize_phone_number('+351 912 345 678'), '351912345678')

    def test_eua_com_mais_e_formatacao(self):
        self.assertEqual(normalize_phone_number('+1 (555) 404-4637'), '15554044637')

    def test_argentina_com_mais(self):
        self.assertEqual(normalize_phone_number('+54 9 11 2345-6789'), '5491123456789')

    def test_brasil_com_mais_continua_brasil(self):
        self.assertEqual(normalize_phone_number('+55 63 99250-9193'), '5563992509193')


class TamanhoForaDaPeneiraTests(TestCase):
    """Estrangeiro que NÃO tem 10 ou 11 dígitos.

    A heurística só olhava para 10-11 dígitos, então estes já passavam
    intactos por acidente. O teste existe para travar o comportamento: quando
    a normalização passar a usar libphonenumber, eles precisam continuar
    iguais em vez de virar outra coisa.
    """

    def test_alemanha_treze_digitos(self):
        self.assertEqual(normalize_phone_number('4915112345678'), '4915112345678')

    def test_reino_unido_doze_digitos(self):
        self.assertEqual(normalize_phone_number('+44 7911 123456'), '447911123456')


class VarianteDeTelefoneTests(TestCase):
    """O nono dígito é uma regra BRASILEIRA e só pode valer no Brasil.

    `phone_variants` gera o par com/sem o nono dígito para casar o wa_id do
    WhatsApp com o que o formulário gravou. Aplicada a um número estrangeiro,
    ela inventa telefones que não existem — e um lookup por `campo__in`
    dessas variantes pode casar com o cliente ERRADO.
    """

    def test_brasileiro_gera_par_com_e_sem_nono(self):
        from apps.core.utils import phone_variants
        variantes = phone_variants('5563992429380')
        self.assertIn('5563992429380', variantes)
        self.assertIn('556392429380', variantes)

    def test_espanhol_nao_ganha_variante_de_nono_digito(self):
        from apps.core.utils import phone_variants
        variantes = phone_variants('34647520824')
        self.assertEqual(
            {v.lstrip('+') for v in variantes},
            {'34647520824'},
            'variante inventada para número estrangeiro',
        )


class ExibicaoTests(TestCase):
    """Estrangeiro não pode ser exibido com a máscara de DDD brasileiro."""

    def test_brasileiro_mantem_formato_local(self):
        from apps.core.utils import format_phone_for_display
        self.assertEqual(format_phone_for_display('5563992509193'), '+55 (63) 99250-9193')

    def test_espanhol_nao_finge_ser_ddd_brasileiro(self):
        from apps.core.utils import format_phone_for_display
        exibido = format_phone_for_display('34647520824')
        self.assertNotIn('(34)', exibido)
        self.assertTrue(exibido.startswith('+34'), exibido)
