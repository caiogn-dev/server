"""
Regressão: ThrottledWebSocketConsumer.verify_account_access NÃO deve usar
is_staff como bypass cross-tenant na lógica de retorno.

Convenção do projeto: is_staff = acesso ao /admin Django, sem privilégio
cross-tenant. Apenas is_superuser tem acesso irrestrito.

O fallback da base é chamado quando um consumer subclasse não sobrescreve
verify_account_access. Com is_staff no fallback, qualquer usuário do /admin
acessaria qualquer conta WA/Instagram via WebSocket — IDOR cross-tenant
por omissão de override.

Todos os testes são SimpleTestCase (análise estática + instância mínima sem
banco/Redis/channels).
"""
import ast
import asyncio
import unittest
from pathlib import Path
from unittest.mock import MagicMock

BASE_CONSUMER_PATH = Path(__file__).parent.parent / "base_consumer.py"


def _get_method_return_sources(source: str, method_name: str) -> list:
    """Retorna as strings de código de todos os nós Return dentro do método."""
    tree = ast.parse(source)
    returns = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == method_name:
                for child in ast.walk(node):
                    if isinstance(child, ast.Return) and child.value is not None:
                        seg = ast.get_source_segment(source, child.value) or ""
                        returns.append(seg)
    return returns


class BaseConsumerIsStaffFallbackStaticTest(unittest.TestCase):
    """Análise estática: lógica de retorno do fallback usa apenas is_superuser."""

    @classmethod
    def setUpClass(cls):
        cls.source = BASE_CONSUMER_PATH.read_text()

    def test_verify_account_access_retorno_nao_usa_is_staff(self):
        """As expressões de retorno de verify_account_access não devem conter is_staff."""
        returns = _get_method_return_sources(self.source, "verify_account_access")
        self.assertTrue(returns, "Nenhum nó Return encontrado em verify_account_access.")
        for ret in returns:
            self.assertNotIn(
                "is_staff",
                ret,
                f"Retorno '{ret}' contém is_staff — IDOR cross-tenant via WebSocket "
                f"quando subclasse não sobrescreve o método.",
            )

    def test_verify_account_access_retorno_usa_is_superuser(self):
        """Ao menos um retorno deve mencionar is_superuser (bypass legítimo)."""
        returns = _get_method_return_sources(self.source, "verify_account_access")
        has_superuser = any("is_superuser" in ret for ret in returns)
        self.assertTrue(
            has_superuser,
            "Nenhum retorno de verify_account_access menciona is_superuser — "
            "bypass para administradores do sistema está ausente.",
        )

    def test_classe_correta_existe(self):
        """ThrottledWebSocketConsumer deve estar definida no módulo."""
        self.assertIn(
            "class ThrottledWebSocketConsumer",
            self.source,
            "Classe ThrottledWebSocketConsumer não encontrada em base_consumer.py.",
        )


class BaseConsumerIsStaffFallbackBehaviorTest(unittest.TestCase):
    """Testa o comportamento de ThrottledWebSocketConsumer.verify_account_access."""

    def setUp(self):
        from apps.core.base_consumer import ThrottledWebSocketConsumer
        self.consumer = ThrottledWebSocketConsumer.__new__(ThrottledWebSocketConsumer)

    def _run(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def _make_user(self, is_staff=False, is_superuser=False):
        user = MagicMock()
        user.is_staff = is_staff
        user.is_superuser = is_superuser
        return user

    def test_is_staff_sem_is_superuser_negado(self):
        """is_staff=True, is_superuser=False → acesso negado (P2: não é bypass)."""
        self.consumer.user = self._make_user(is_staff=True, is_superuser=False)
        result = self._run(self.consumer.verify_account_access("qualquer-account-id"))
        self.assertFalse(
            result,
            "verify_account_access retornou True para is_staff=True, "
            "is_superuser=False — IDOR cross-tenant via WebSocket se "
            "subclasse não sobrescrever o método.",
        )

    def test_is_superuser_permitido(self):
        """is_superuser=True → acesso permitido."""
        self.consumer.user = self._make_user(is_staff=False, is_superuser=True)
        result = self._run(self.consumer.verify_account_access("qualquer-account-id"))
        self.assertTrue(result, "is_superuser=True deveria ter acesso permitido.")

    def test_usuario_sem_flags_negado(self):
        """Usuário normal (is_staff=False, is_superuser=False) → negado."""
        self.consumer.user = self._make_user(is_staff=False, is_superuser=False)
        result = self._run(self.consumer.verify_account_access("qualquer-account-id"))
        self.assertFalse(result, "Usuário normal não deveria ter acesso no fallback base.")

    def test_is_staff_e_is_superuser_permitido(self):
        """is_staff=True E is_superuser=True → permitido (is_superuser prevalece)."""
        self.consumer.user = self._make_user(is_staff=True, is_superuser=True)
        result = self._run(self.consumer.verify_account_access("qualquer-account-id"))
        self.assertTrue(result, "Superuser deve ter acesso mesmo que is_staff também seja True.")

    def test_user_none_negado(self):
        """user=None → sempre negado (ausência de usuário autenticado)."""
        self.consumer.user = None
        result = self._run(self.consumer.verify_account_access("qualquer-account-id"))
        self.assertFalse(result, "Sem usuário autenticado deveria ser negado.")

    def test_account_id_vazio_negado(self):
        """account_id vazio → sempre negado."""
        self.consumer.user = self._make_user(is_superuser=True)
        result = self._run(self.consumer.verify_account_access(""))
        self.assertFalse(result, "account_id vazio deveria ser negado mesmo para superuser.")
