"""
Testes de segurança: str(exc) em respostas HTTP — ações Instagram e Messenger restantes.

PR #333 corrigiu connect() e send_message() do Instagram. Este módulo cobre as
8 ações remanescentes de InstagramAccountViewSet/InstagramMediaViewSet/
InstagramShoppingViewSet/InstagramLiveViewSet, mais 2 ações do Messenger
(MessengerAccountViewSet.sync e MessengerConversationViewSet.send_message).

Estratégia: análise estática (str(exc) não aparece na resposta) + teste
comportamental (exceção mapeada → mensagem genérica pt-BR, sem mensagem interna).
"""
import inspect
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.instagram.api import views as ig_views
from apps.messaging.api import views as msg_views

factory = APIRequestFactory()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _src(method):
    return inspect.getsource(method)


def _has_str_exc(method):
    src = _src(method)
    return "str(exc)" in src or "str(e)" in src or "str(error)" in src


def _mock_user(is_superuser=False):
    u = MagicMock()
    u.is_superuser = is_superuser
    u.is_authenticated = True
    return u


# ---------------------------------------------------------------------------
# Análise estática — Instagram
# ---------------------------------------------------------------------------

class TestInstagramStrExcStaticAnalysis(SimpleTestCase):
    """Garante que nenhuma das 8 ações remanescentes do Instagram expõe str(exc)."""

    def test_account_sync_nao_expoe_str_exc(self):
        self.assertFalse(
            _has_str_exc(ig_views.InstagramAccountViewSet.sync),
            "InstagramAccountViewSet.sync() expõe str(exc) na resposta HTTP",
        )

    def test_account_refresh_page_token_nao_expoe_str_exc(self):
        self.assertFalse(
            _has_str_exc(ig_views.InstagramAccountViewSet.refresh_page_token),
            "InstagramAccountViewSet.refresh_page_token() expõe str(exc)",
        )

    def test_account_insights_nao_expoe_str_exc(self):
        self.assertFalse(
            _has_str_exc(ig_views.InstagramAccountViewSet.insights),
            "InstagramAccountViewSet.insights() expõe str(exc)",
        )

    def test_media_publish_nao_expoe_str_exc(self):
        self.assertFalse(
            _has_str_exc(ig_views.InstagramMediaViewSet.publish),
            "InstagramMediaViewSet.publish() expõe str(exc)",
        )

    def test_media_insights_nao_expoe_str_exc(self):
        self.assertFalse(
            _has_str_exc(ig_views.InstagramMediaViewSet.insights),
            "InstagramMediaViewSet.insights() expõe str(exc)",
        )

    def test_media_comments_nao_expoe_str_exc(self):
        self.assertFalse(
            _has_str_exc(ig_views.InstagramMediaViewSet.comments),
            "InstagramMediaViewSet.comments() expõe str(exc)",
        )

    def test_shopping_tag_product_nao_expoe_str_exc(self):
        self.assertFalse(
            _has_str_exc(ig_views.InstagramShoppingViewSet.tag_product),
            "InstagramShoppingViewSet.tag_product() expõe str(exc)",
        )

    def test_live_start_nao_expoe_str_exc(self):
        self.assertFalse(
            _has_str_exc(ig_views.InstagramLiveViewSet.start),
            "InstagramLiveViewSet.start() expõe str(exc)",
        )


# ---------------------------------------------------------------------------
# Análise estática — Messenger
# ---------------------------------------------------------------------------

class TestMessengerStrExcStaticAnalysis(SimpleTestCase):
    """Garante que as 2 ações do Messenger não expõem str(exc)."""

    def test_account_sync_nao_expoe_str_exc(self):
        self.assertFalse(
            _has_str_exc(msg_views.MessengerAccountViewSet.sync),
            "MessengerAccountViewSet.sync() expõe str(exc) na resposta HTTP",
        )

    def test_conversation_send_message_nao_expoe_str_exc(self):
        self.assertFalse(
            _has_str_exc(msg_views.MessengerConversationViewSet.send_message),
            "MessengerConversationViewSet.send_message() expõe str(exc)",
        )


# ---------------------------------------------------------------------------
# Testes comportamentais — Instagram (respostas genéricas)
# ---------------------------------------------------------------------------

class TestInstagramSyncBehavior(SimpleTestCase):
    """InstagramAccountViewSet.sync() deve retornar mensagem genérica em pt-BR."""

    def _call_sync(self, exc_message="Token inválido: Bearer abc123xyz"):
        mock_account = MagicMock()

        with (
            patch.object(ig_views.InstagramAccountViewSet, "get_object", return_value=mock_account),
            patch("apps.instagram.api.views.InstagramAPI") as MockAPI,
        ):
            # sync() chama api.get_account_info() diretamente (não usa GraphService)
            MockAPI.return_value.get_account_info.side_effect = Exception(exc_message)

            view = ig_views.InstagramAccountViewSet.as_view({"post": "sync"})
            request = factory.post("/fake/")
            request.user = _mock_user()
            response = view(request, pk=1)
            return response

    def test_sync_nao_retorna_mensagem_da_excecao(self):
        exc_msg = "GraphAPI error: Token Bearer abc123xyz invalid"
        resp = self._call_sync(exc_msg)
        self.assertEqual(resp.status_code, 400)
        body = str(resp.data)
        self.assertNotIn(exc_msg, body, "Mensagem interna da exceção vazou na resposta")
        self.assertNotIn("Bearer", body)
        self.assertNotIn("abc123xyz", body)

    def test_sync_retorna_mensagem_generica(self):
        resp = self._call_sync()
        self.assertEqual(resp.status_code, 400)
        self.assertIn("message", resp.data, "Resposta de erro deve ter campo 'message'")


class TestInstagramMediaPublishBehavior(SimpleTestCase):
    """InstagramMediaViewSet.publish() deve retornar mensagem genérica."""

    def _call_publish(self, exc_message="access_token=EAA...secreto"):
        mock_media = MagicMock()
        mock_media.account = MagicMock()

        with (
            patch.object(ig_views.InstagramMediaViewSet, "get_object", return_value=mock_media),
            patch("apps.instagram.api.views.InstagramAPI"),
            patch("apps.instagram.api.views.InstagramGraphService") as MockGraph,
        ):
            MockGraph.return_value.publish_media.side_effect = Exception(exc_message)

            view = ig_views.InstagramMediaViewSet.as_view({"post": "publish"})
            request = factory.post("/fake/")
            request.user = _mock_user()
            response = view(request, pk=1)
            return response

    def test_publish_nao_vaza_token_na_resposta(self):
        secret_token = "access_token=EAABsbCS123secreto"
        resp = self._call_publish(secret_token)
        self.assertEqual(resp.status_code, 400)
        body = str(resp.data)
        self.assertNotIn(secret_token, body)
        self.assertNotIn("EAABsbCS123secreto", body)


class TestMessengerSyncBehavior(SimpleTestCase):
    """MessengerAccountViewSet.sync() deve retornar mensagem genérica."""

    def _call_sync(self, exc_message="page_access_token=abc_secreto"):
        mock_account = MagicMock()
        mock_account.page_id = "12345"
        mock_account.page_name = "Loja Teste"

        with (
            patch.object(msg_views.MessengerAccountViewSet, "get_object", return_value=mock_account),
            patch("apps.messaging.api.views.MessengerService") as MockService,
        ):
            MockService.return_value.get.side_effect = Exception(exc_message)

            view = msg_views.MessengerAccountViewSet.as_view({"post": "sync"})
            request = factory.post("/fake/")
            request.user = _mock_user()
            response = view(request, pk=1)
            return response

    def test_sync_nao_vaza_token(self):
        exc_msg = "page_access_token=EAACsecretoToken123"
        resp = self._call_sync(exc_msg)
        self.assertEqual(resp.status_code, 400)
        body = str(resp.data)
        self.assertNotIn(exc_msg, body)
        self.assertNotIn("EAACsecretoToken123", body)

    def test_sync_retorna_mensagem_de_erro(self):
        resp = self._call_sync()
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.data)
