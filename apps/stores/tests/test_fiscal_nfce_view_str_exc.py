"""
Regressão de segurança: info-disclosure via str(exc) nas actions emit_nfce e
cancel_nfce de StoreOrderViewSet [P1].

Problema:
  - emit_nfce: `except FiscalNotConfigured as exc: return Response({'error': str(exc)}, 400)`
    → mensagens como 'focus_token ausente na config fiscal da loja' ou
      f'Provider fiscal desconhecido: {provider_key}' revelam estrutura interna de configuração.
  - cancel_nfce: `except (ValueError, FiscalNotConfigured) as exc: return Response({'error': str(exc)}, 400)`
    → ValueError pode conter qualquer mensagem do provedor; também sem logger (erros silenciosos).

Fix esperado:
  - Ambas as actions devem retornar mensagens genéricas em pt-BR.
  - cancel_nfce deve registrar no logger antes de responder.
  - str(exc) deve aparecer apenas nos logs internos, não em Response.

Todos os testes são SimpleTestCase (sem DB/Docker). Análise estática + mocks.
"""
import ast
import os
import re
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ORDER_VIEWS_PATH = os.path.join(BASE, "stores", "api", "views", "order_views.py")


def _source():
    with open(ORDER_VIEWS_PATH, encoding="utf-8") as f:
        return f.read()


def _extract_method(src, class_name, method_name):
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return ast.get_source_segment(src, item) or ""
    return ""


class TestEmitNfceNoStrExc(unittest.TestCase):
    """emit_nfce não deve retornar str(exc) no corpo HTTP [P1]."""

    def setUp(self):
        self.src = _source()

    def test_emit_nfce_nao_retorna_str_exc_na_resposta(self):
        """emit_nfce deve usar mensagem genérica para FiscalNotConfigured."""
        body = _extract_method(self.src, "StoreOrderViewSet", "emit_nfce")
        self.assertTrue(body, "método emit_nfce não encontrado em StoreOrderViewSet")

        # Padrão de leak: Response({'error': str(exc)}) no except FiscalNotConfigured
        # Após o fix: str(exc) deve aparecer apenas no logger, não em Response(...)
        leak_pattern = re.compile(r"return\s+Response\s*\(\s*\{[^}]*str\s*\(\s*exc\s*\)", re.DOTALL)
        self.assertIsNone(
            leak_pattern.search(body),
            "emit_nfce retorna str(exc) em Response — info-disclosure: "
            "mensagens como 'focus_token ausente' ou 'Provider desconhecido: <key>' vazam.",
        )

    def test_emit_nfce_mantem_logger(self):
        """emit_nfce deve preservar o logger interno para auditoria."""
        body = _extract_method(self.src, "StoreOrderViewSet", "emit_nfce")
        self.assertTrue(body, "método emit_nfce não encontrado")
        has_logger = any(p in body for p in ("logger.warning", "logger.error", "logger.exception"))
        self.assertTrue(has_logger, "emit_nfce não registra FiscalNotConfigured no logger")

    def test_emit_nfce_responde_400_com_mensagem_fixa(self):
        """emit_nfce deve retornar HTTP 400 com mensagem sem detalhes internos."""
        body = _extract_method(self.src, "StoreOrderViewSet", "emit_nfce")
        self.assertTrue(body, "método emit_nfce não encontrado")
        # Deve existir um Response com HTTP 400 no except FiscalNotConfigured
        self.assertIn("HTTP_400_BAD_REQUEST", body, "emit_nfce não retorna 400 em FiscalNotConfigured")
        # Não deve retornar str(exc) em nenhuma Response
        self.assertNotIn("Response({'error': str(exc)})", body)
        self.assertNotIn('Response({"error": str(exc)})', body)


class TestCancelNfceNoStrExc(unittest.TestCase):
    """cancel_nfce não deve retornar str(exc) no corpo HTTP [P1]."""

    def setUp(self):
        self.src = _source()

    def test_cancel_nfce_nao_retorna_str_exc_na_resposta(self):
        """cancel_nfce deve usar mensagem genérica para ValueError/FiscalNotConfigured."""
        body = _extract_method(self.src, "StoreOrderViewSet", "cancel_nfce")
        self.assertTrue(body, "método cancel_nfce não encontrado em StoreOrderViewSet")

        leak_pattern = re.compile(r"return\s+Response\s*\(\s*\{[^}]*str\s*\(\s*exc\s*\)", re.DOTALL)
        self.assertIsNone(
            leak_pattern.search(body),
            "cancel_nfce retorna str(exc) em Response — ValueError pode conter "
            "mensagens arbitrárias do provedor fiscal (token, endpoint interno, etc.).",
        )

    def test_cancel_nfce_adiciona_logger_para_excecoes_de_validacao(self):
        """cancel_nfce deve registrar ValueError/FiscalNotConfigured no logger."""
        body = _extract_method(self.src, "StoreOrderViewSet", "cancel_nfce")
        self.assertTrue(body, "método cancel_nfce não encontrado")
        has_logger = any(p in body for p in ("logger.warning", "logger.error", "logger.exception"))
        self.assertTrue(
            has_logger,
            "cancel_nfce não registra ValueError/FiscalNotConfigured no logger — "
            "erros de cancelamento ficam invisíveis em produção.",
        )

    def test_cancel_nfce_responde_400_com_mensagem_fixa(self):
        """cancel_nfce deve retornar HTTP 400 com mensagem sem detalhes internos."""
        body = _extract_method(self.src, "StoreOrderViewSet", "cancel_nfce")
        self.assertTrue(body, "método cancel_nfce não encontrado")
        self.assertIn("HTTP_400_BAD_REQUEST", body)
        # Nenhum str(exc) em Response
        self.assertNotIn("str(exc)", body.split("HTTP_502_BAD_GATEWAY")[0]
                         if "HTTP_502_BAD_GATEWAY" in body else body)

    def test_cancel_nfce_mantem_502_para_excecoes_genericas(self):
        """cancel_nfce deve manter o bloco except Exception → 502 genérico."""
        body = _extract_method(self.src, "StoreOrderViewSet", "cancel_nfce")
        self.assertTrue(body, "método cancel_nfce não encontrado")
        self.assertIn("HTTP_502_BAD_GATEWAY", body,
                      "cancel_nfce perdeu o bloco genérico 502 — regressão no tratamento de erros")


if __name__ == "__main__":
    unittest.main()
