"""Ninguém pode grudar o DDI 55 por conta própria.

`normalize_phone_number` é a fonte única de verdade do telefone. Cada lugar
que reimplementou "se não começa com 55, gruda 55" é um lugar onde o número da
Layane (`34647520824`, Espanha) vira `5534647520824` — um telefone que não
existe. O envio falha com 131026 "Message undeliverable" e o cliente fica sem
resposta enquanto o painel mostra a mensagem como enviada.

Estes testes travam cada uma dessas cópias na forma canônica.
"""
from django.test import TestCase

ESPANHA = '34647520824'      # Layane
BRASIL = '63992429380'       # celular de Palmas, sem DDI
BRASIL_E164 = '5563992429380'


class OTPWhatsAppTests(TestCase):
    """O OTP de login não pode inventar DDI: o código vai para outro número."""

    def test_estrangeiro_mantem_o_proprio_ddi(self):
        from apps.core.auth.whatsapp_auth import WhatsAppAuthService
        self.assertEqual(WhatsAppAuthService._normalize_phone('+34 647 52 08 24'), ESPANHA)
        self.assertEqual(WhatsAppAuthService._normalize_phone(ESPANHA), ESPANHA)

    def test_brasileiro_continua_ganhando_o_55(self):
        from apps.core.auth.whatsapp_auth import WhatsAppAuthService
        self.assertEqual(WhatsAppAuthService._normalize_phone(BRASIL), BRASIL_E164)
        self.assertEqual(WhatsAppAuthService._normalize_phone(BRASIL_E164), BRASIL_E164)


class ProvedorWhatsAppTests(TestCase):
    """`format_recipient` decidia o país pelo TAMANHO — 11 dígitos = Brasil.

    Um celular espanhol completo tem exatamente 11 dígitos. A regra de tamanho
    o transformava em `+5534647520824`.
    """

    def _provider(self):
        from apps.messaging.providers.whatsapp_provider import WhatsAppProvider
        return WhatsAppProvider.__new__(WhatsAppProvider)

    def test_estrangeiro_de_onze_digitos_nao_vira_brasileiro(self):
        self.assertEqual(self._provider().format_recipient(ESPANHA), '+' + ESPANHA)

    def test_brasileiro_sem_ddi_ganha_55(self):
        self.assertEqual(self._provider().format_recipient(BRASIL), '+' + BRASIL_E164)

    def test_aceita_estrangeiro_como_destinatario_valido(self):
        provider = self._provider()
        self.assertTrue(provider.validate_recipient('+34 647 52 08 24'))
        self.assertTrue(provider.validate_recipient(ESPANHA))
        self.assertTrue(provider.validate_recipient(BRASIL))

    def test_lixo_continua_invalido(self):
        provider = self._provider()
        self.assertFalse(provider.validate_recipient(''))
        self.assertFalse(provider.validate_recipient('123'))


class EntregaUberTests(TestCase):
    """`'+55' if not x.startswith('+55') else '' + x` nunca fez o que parece.

    Precedência: o `else` devolve `'' + x`, mas o `if` devolve a string `'+55'`
    SOZINHA. Todo pedido sem `+55` mandava o telefone literal `+55` para a
    Uber — o entregador nunca conseguiu ligar para ninguém.
    """

    def test_telefone_do_cliente_chega_inteiro(self):
        from apps.orders.services.uber_delivery import _telefone_e164
        self.assertEqual(_telefone_e164(BRASIL), '+' + BRASIL_E164)
        self.assertEqual(_telefone_e164('+55 63 99242-9380'), '+' + BRASIL_E164)
        self.assertEqual(_telefone_e164(ESPANHA), '+' + ESPANHA)

    def test_nunca_devolve_so_o_ddi(self):
        from apps.orders.services.uber_delivery import _telefone_e164
        self.assertNotEqual(_telefone_e164(BRASIL), '+55')
