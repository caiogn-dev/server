"""InstagramAPI.BASE_URL deve vir de settings, não de string fixa no código.

Depois de e71f2752 (chore: versão única da Graph API), BASE_URL passou a ler
settings.META_GRAPH_URL em vez de 'https://graph.facebook.com/v22.0'. Isso é
correto — a versão da API deve ser configurável.

O risco é: BASE_URL é avaliado no corpo da classe, quando o módulo é importado.
Se META_GRAPH_URL não existir nas settings do ambiente de teste (test_serializer),
django.setup() falha com AttributeError antes de qualquer teste rodar.

Estes testes inspecionam diretamente o módulo test_serializer (não as settings
ativas, que herdam base.py e já têm META_GRAPH_URL). Assim a cobertura resiste
a removê-la de test_serializer sem tocar base.py.
"""
import importlib

from django.conf import settings
from django.test import SimpleTestCase


class TestSerializerSettingsTest(SimpleTestCase):
    """Verifica META_GRAPH_URL no módulo test_serializer diretamente."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ts = importlib.import_module('config.settings.test_serializer')

    def test_meta_graph_url_definida_em_test_serializer(self):
        """META_GRAPH_URL deve existir em test_serializer — senão django.setup() falha."""
        self.assertTrue(
            hasattr(self.ts, 'META_GRAPH_URL'),
            "META_GRAPH_URL ausente em config/settings/test_serializer.py; "
            "qualquer test que usa esse settings falha em django.setup().",
        )

    def test_meta_graph_version_definida_em_test_serializer(self):
        """META_GRAPH_VERSION deve existir em test_serializer para compor META_GRAPH_URL."""
        self.assertTrue(
            hasattr(self.ts, 'META_GRAPH_VERSION'),
            "META_GRAPH_VERSION ausente em config/settings/test_serializer.py.",
        )

    def test_meta_graph_url_contem_graph_facebook(self):
        """A URL em test_serializer deve apontar para graph.facebook.com."""
        url = getattr(self.ts, 'META_GRAPH_URL', '')
        self.assertIn(
            'graph.facebook.com',
            url,
            f"META_GRAPH_URL='{url}' não aponta para graph.facebook.com.",
        )

    def test_meta_graph_url_usa_version_do_mesmo_modulo(self):
        """META_GRAPH_URL deve conter META_GRAPH_VERSION do mesmo módulo."""
        version = getattr(self.ts, 'META_GRAPH_VERSION', '')
        url = getattr(self.ts, 'META_GRAPH_URL', '')
        self.assertIn(
            version,
            url,
            f"META_GRAPH_URL='{url}' não contém META_GRAPH_VERSION='{version}'.",
        )


class InstagramAPIBaseUrlTest(SimpleTestCase):
    """BASE_URL de InstagramAPI deve ser consistente com as settings ativas."""

    def test_base_url_bate_com_settings_ativas(self):
        """BASE_URL deve refletir settings.META_GRAPH_URL (seja qual for o módulo ativo)."""
        from apps.instagram.services.instagram_api import InstagramAPI
        self.assertEqual(
            InstagramAPI.BASE_URL,
            settings.META_GRAPH_URL,
        )

    def test_base_url_aponta_para_graph_facebook(self):
        from apps.instagram.services.instagram_api import InstagramAPI
        self.assertIn('graph.facebook.com', InstagramAPI.BASE_URL)
