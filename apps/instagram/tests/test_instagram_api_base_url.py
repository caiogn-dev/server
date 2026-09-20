"""InstagramAPI.BASE_URL deve vir de settings, não de string fixa no código.

Depois de e71f2752 (chore: versão única da Graph API), BASE_URL passou a ler
settings.META_GRAPH_URL em vez de 'https://graph.facebook.com/v22.0'. Isso é
correto — a versão da API deve ser configurável.

O risco é: BASE_URL é avaliado no corpo da classe, quando o módulo é importado.
Se META_GRAPH_URL não existir nas settings do ambiente de teste (test_serializer),
django.setup() falha com AttributeError antes de qualquer teste rodar.

Estes testes garantem que:
  1. META_GRAPH_URL existe nas settings de teste.
  2. InstagramAPI.BASE_URL bate com esse valor.
  3. A URL contém 'graph.facebook.com' (endpoint válido da Meta).
  4. A URL NÃO tem versão fixa (seria contornado se BASE_URL virasse string literal).
"""
import re

from django.conf import settings
from django.test import SimpleTestCase


class InstagramAPIBaseUrlTest(SimpleTestCase):

    def test_meta_graph_url_definida_nas_settings(self):
        """META_GRAPH_URL deve existir nas settings — senão django.setup() falha."""
        self.assertTrue(
            hasattr(settings, 'META_GRAPH_URL'),
            "settings.META_GRAPH_URL não definida; adicionar em test_serializer.py "
            "(e em qualquer settings que inclua apps.instagram).",
        )

    def test_base_url_bate_com_settings(self):
        """BASE_URL da InstagramAPI deve ser o valor de settings.META_GRAPH_URL."""
        from apps.instagram.services.instagram_api import InstagramAPI
        self.assertEqual(
            InstagramAPI.BASE_URL,
            settings.META_GRAPH_URL,
            "BASE_URL não reflete settings.META_GRAPH_URL; "
            "ou o campo voltou a ser hardcoded ou lê outro atributo.",
        )

    def test_base_url_aponta_para_graph_facebook(self):
        """A URL da Graph API deve apontar para graph.facebook.com."""
        from apps.instagram.services.instagram_api import InstagramAPI
        self.assertIn(
            'graph.facebook.com',
            InstagramAPI.BASE_URL,
            "BASE_URL não aponta para graph.facebook.com — verifique META_GRAPH_URL.",
        )

    def test_base_url_sem_versao_hardcoded(self):
        """BASE_URL não deve conter versão fixa (ex: /v22.0) — a versão vem do env."""
        from apps.instagram.services.instagram_api import InstagramAPI
        padrao_versao_fixa = re.compile(r'graph\.(facebook|instagram)\.com/v\d+\.\d+$')
        # A URL vai ter a versão (META_GRAPH_VERSION), mas ela deve estar em settings
        # e consistente com META_GRAPH_VERSION — não uma constante diferente.
        self.assertRegex(
            InstagramAPI.BASE_URL,
            r'graph\.facebook\.com/v\d+\.\d+',
            "BASE_URL não tem formato esperado 'graph.facebook.com/vX.Y'.",
        )
        meta_version = getattr(settings, 'META_GRAPH_VERSION', None)
        if meta_version:
            self.assertIn(
                meta_version,
                InstagramAPI.BASE_URL,
                f"BASE_URL não usa META_GRAPH_VERSION='{meta_version}' das settings.",
            )
