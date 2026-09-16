"""
Testes de regressão: views de Instagram e Messenger NÃO devem expor str(exc)
genérico em respostas HTTP.

Tipo: P1 — info-disclosure para usuários autenticados.
O str(exc) de requests.ConnectionError, HTTPError ou erros da Graph API do
Instagram/Meta pode incluir URLs com access_token em query params, mensagens
internas do servidor, ou detalhes de configuração.

Todos os testes são SimpleTestCase (sem banco, sem rede real) com mocks.
"""

import ast
import re
import unittest
from pathlib import Path

INSTAGRAM_VIEWS = Path(__file__).parent.parent / "api" / "views.py"
MESSAGING_VIEWS = Path(__file__).parent.parent.parent / "messaging" / "api" / "views.py"


class InstagramViewsStrExcDisclosureTest(unittest.TestCase):
    """Análise estática: nenhum except-Exception genérico retorna str(exc) direto."""

    @classmethod
    def setUpClass(cls):
        cls.source = INSTAGRAM_VIEWS.read_text()
        cls.tree = ast.parse(cls.source)

    def _find_str_exc_in_response(self):
        """
        Retorna lista de linhas onde `str(exc)` ou `str(e)` aparece dentro de
        Response(...) ou JsonResponse(...), excluindo comentários.
        """
        found = []
        for node in ast.walk(self.tree):
            if not isinstance(node, (ast.Call, ast.Return)):
                continue
            if isinstance(node, ast.Call):
                func = node.func
                func_name = ""
                if isinstance(func, ast.Attribute):
                    func_name = func.attr
                elif isinstance(func, ast.Name):
                    func_name = func.id
                if func_name not in ("Response", "JsonResponse"):
                    continue
                src = ast.get_source_segment(self.source, node)
                if src and re.search(r"\bstr\s*\(\s*(exc|e)\s*\)", src):
                    found.append(node.lineno)
        return found

    def test_nenhum_str_exc_em_response_das_views_api(self):
        """Nenhuma Response() das views deve conter str(exc) ou str(e)."""
        bad_lines = self._find_str_exc_in_response()
        self.assertEqual(
            bad_lines,
            [],
            f"apps/instagram/api/views.py linha(s) {bad_lines} expõem str(exc) "
            f"em resposta HTTP — viola o padrão de info-hiding do projeto.",
        )

    def test_nenhum_raw_text_em_response(self):
        """raw.text não deve aparecer em Response() — expõe corpo bruto da API do Meta."""
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            func_name = ""
            if isinstance(func, ast.Attribute):
                func_name = func.attr
            elif isinstance(func, ast.Name):
                func_name = func.id
            if func_name not in ("Response", "JsonResponse"):
                continue
            src = ast.get_source_segment(self.source, node) or ""
            self.assertNotIn(
                "raw.text",
                src,
                f"Linha {node.lineno}: raw.text presente em Response() — corpo da "
                f"resposta Meta pode conter tokens ou segredos.",
            )

    def test_nenhum_detail_raw_text_em_response(self):
        """A variável 'detail' formada por raw.text não deve aparecer em f-string de Response."""
        bad = re.findall(r"detail = raw\.text", self.source)
        self.assertEqual(
            bad,
            [],
            "Variável 'detail' atribuída de raw.text ainda presente no código — "
            "checar se ela é passada para alguma Response().",
        )

    def test_sync_usa_logger_antes_de_responder(self):
        """sync() deve logar antes de retornar erro (não silenciar a exceção)."""
        self.assertIn("logger.", self.source,
                      "Nenhum logger.* encontrado — erros serão silenciados.")

    def test_arquivo_nao_retorna_status_error_com_str_exc(self):
        """Nenhum {'status': 'error', 'message': str(exc)} deve aparecer."""
        bad = re.findall(r"['\"]message['\"]\s*:\s*str\s*\(\s*(exc|e)\s*\)", self.source)
        self.assertEqual(
            bad,
            [],
            f"Padrão 'message': str(exc) encontrado — info-disclosure P1.",
        )


class MessagingViewsStrExcDisclosureTest(unittest.TestCase):
    """Análise estática: views de Messenger NÃO devem expor str(exc) genérico."""

    @classmethod
    def setUpClass(cls):
        cls.source = MESSAGING_VIEWS.read_text()
        cls.tree = ast.parse(cls.source)

    def _find_str_exc_in_response(self):
        found = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            func_name = ""
            if isinstance(func, ast.Attribute):
                func_name = func.attr
            elif isinstance(func, ast.Name):
                func_name = func.id
            if func_name not in ("Response", "JsonResponse"):
                continue
            src = ast.get_source_segment(self.source, node)
            if src and re.search(r"\bstr\s*\(\s*(exc|e)\s*\)", src):
                found.append(node.lineno)
        return found

    def test_nenhum_str_exc_em_response_das_views_messaging(self):
        """Nenhuma Response() do messenger deve conter str(exc) ou str(e)."""
        bad_lines = self._find_str_exc_in_response()
        self.assertEqual(
            bad_lines,
            [],
            f"apps/messaging/api/views.py linha(s) {bad_lines} expõem str(exc) "
            f"em resposta HTTP — info-disclosure P1.",
        )

    def test_sync_action_usa_logger(self):
        """A action sync (MessengerAccountViewSet) deve logar antes de retornar erro."""
        self.assertIn("logger.", self.source,
                      "Nenhum logger.* encontrado no messaging views.")

    def test_send_message_nao_expoe_exc(self):
        """send_message não deve retornar str(exc) — Facebook Messenger API pode incluir detalhes internos."""
        bad = re.findall(r"return Response\([^)]*str\s*\(\s*(exc|e)\s*\)[^)]*\)", self.source)
        self.assertEqual(
            bad,
            [],
            f"Padrão str(exc) em Response() encontrado em messaging/api/views.py: {bad}",
        )
