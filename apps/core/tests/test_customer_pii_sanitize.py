"""
Testes da sanitização de identidade-placeholder para exibição (LGPD / CLAUDE.md).

Placeholders internos ({phone}@pastita.local, cliente_..., desconhecido) não
podem ser exibidos como dados reais do cliente em respostas de API/mobile.
"""
from django.test import SimpleTestCase
from apps.core.services.customer_identity import CustomerIdentityService as C


class PublicEmailTestCase(SimpleTestCase):
    def test_placeholder_pastita_local_vira_none(self):
        self.assertIsNone(C.public_email('5511999999999@pastita.local'))

    def test_placeholder_cardapidex_local_vira_none(self):
        self.assertIsNone(C.public_email('5511999999999@cardapidex.local'))

    def test_anonimizado_vira_none(self):
        self.assertIsNone(C.public_email('removido_42@anonimizado.local'))

    def test_vazio_vira_none(self):
        self.assertIsNone(C.public_email(''))
        self.assertIsNone(C.public_email(None))

    def test_email_real_preservado(self):
        self.assertEqual(C.public_email('cliente@gmail.com'), 'cliente@gmail.com')


class PublicNameTestCase(SimpleTestCase):
    def test_cliente_prefixo_vira_none(self):
        self.assertIsNone(C.public_name('cliente_5511999999999'))

    def test_desconhecido_vira_none(self):
        self.assertIsNone(C.public_name('Desconhecido'))

    def test_vazio_vira_none(self):
        self.assertIsNone(C.public_name(''))
        self.assertIsNone(C.public_name(None))

    def test_nome_real_preservado(self):
        self.assertEqual(C.public_name('Maria Silva'), 'Maria Silva')
