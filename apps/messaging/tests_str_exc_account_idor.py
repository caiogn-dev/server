"""
Testes de regressão para:
1. info-disclosure via str(exc) em MessengerAccountViewSet.sync e
   MessengerConversationViewSet.send_message
2. IDOR de escrita via campo 'account' gravável em MessengerConversationSerializer

Todos são SimpleTestCase (sem DB/Docker). Análise estática do código-fonte.
"""
import ast
import os
import re
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEWS_PATH = os.path.join(BASE, "messaging", "api", "views.py")
SERIALIZERS_PATH = os.path.join(BASE, "messaging", "api", "serializers.py")


def _source(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _extract_method(src, class_name, method_name):
    """Retorna o source AST de um método dentro de uma classe."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return ast.get_source_segment(src, item) or ""
    return ""


class TestMessengerStrExcDisclosure(unittest.TestCase):
    """str(exc) exposto em resposta HTTP é info-disclosure [P1]."""

    def setUp(self):
        self.src = _source(VIEWS_PATH)

    def test_sync_nao_retorna_str_exc_na_resposta(self):
        """MessengerAccountViewSet.sync não deve retornar str(exc) em Response."""
        body = _extract_method(self.src, "MessengerAccountViewSet", "sync")
        self.assertTrue(body, "método sync não encontrado em MessengerAccountViewSet")
        # Padrão de leak: Response({"error": str(exc)})
        self.assertNotIn(
            'str(exc)',
            body,
            "sync retorna str(exc) em Response — info-disclosure detectado",
        )

    def test_send_message_nao_retorna_str_exc(self):
        """MessengerConversationViewSet.send_message não deve retornar str(exc)."""
        body = _extract_method(self.src, "MessengerConversationViewSet", "send_message")
        self.assertTrue(body, "método send_message não encontrado em MessengerConversationViewSet")
        self.assertNotIn(
            'str(exc)',
            body,
            "send_message retorna str(exc) — info-disclosure detectado",
        )

    def test_sync_usa_logger(self):
        """sync deve registrar a exceção em log (não silenciar)."""
        body = _extract_method(self.src, "MessengerAccountViewSet", "sync")
        self.assertTrue(body, "método sync não encontrado")
        has_logger = any(pat in body for pat in (
            "logger.exception", "logger.error", "logger.warning",
        ))
        self.assertTrue(has_logger, "sync não registra a exceção no logger")

    def test_send_message_usa_logger(self):
        """send_message deve registrar a exceção em log."""
        body = _extract_method(self.src, "MessengerConversationViewSet", "send_message")
        self.assertTrue(body, "método send_message não encontrado")
        has_logger = any(pat in body for pat in (
            "logger.exception", "logger.error", "logger.warning",
        ))
        self.assertTrue(has_logger, "send_message não registra a exceção no logger")

    def test_sync_responde_com_mensagem_generica(self):
        """sync deve retornar mensagem genérica sem detalhes internos em erro."""
        body = _extract_method(self.src, "MessengerAccountViewSet", "sync")
        self.assertTrue(body, "método sync não encontrado")
        # Deve ter alguma Response de erro
        self.assertIn("Response", body, "sync não retorna Response de erro")
        # Não deve ter str(exc) em nenhuma Response de erro
        self.assertNotIn('str(exc)', body, "sync expõe str(exc)")

    def test_send_message_responde_com_mensagem_generica(self):
        """send_message deve retornar mensagem genérica sem detalhes da exceção."""
        body = _extract_method(self.src, "MessengerConversationViewSet", "send_message")
        self.assertTrue(body, "método send_message não encontrado")
        self.assertNotIn('str(exc)', body, "send_message expõe str(exc)")


class TestMessengerConversationSerializerAccountReadOnly(unittest.TestCase):
    """account deve ser read_only em MessengerConversationSerializer [P1 IDOR write]."""

    def setUp(self):
        self.src = _source(SERIALIZERS_PATH)

    def test_account_em_read_only_fields(self):
        """MessengerConversationSerializer.read_only_fields deve incluir 'account'."""
        tree = ast.parse(self.src)
        serializer_node = None
        for node in ast.walk(tree):
            if (isinstance(node, ast.ClassDef)
                    and node.name == "MessengerConversationSerializer"):
                serializer_node = node
                break
        self.assertIsNotNone(serializer_node, "MessengerConversationSerializer não encontrado")

        for item in ast.walk(serializer_node):
            if isinstance(item, ast.ClassDef) and item.name == "Meta":
                for stmt in item.body:
                    if isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if (isinstance(target, ast.Name)
                                    and target.id == "read_only_fields"):
                                val = stmt.value
                                elements = []
                                if isinstance(val, (ast.List, ast.Tuple)):
                                    elements = [
                                        elt.value if isinstance(elt, ast.Constant) else ""
                                        for elt in val.elts
                                    ]
                                self.assertIn(
                                    "account",
                                    elements,
                                    f"account não está em read_only_fields (atual: {elements}) "
                                    "— IDOR de escrita cross-tenant possível",
                                )
                                return
        self.fail("read_only_fields não encontrado em MessengerConversationSerializer.Meta")

    def test_account_nao_sobrescritivel_via_patch(self):
        """account não deve aparecer como campo gravável isolado (fora de read_only_fields)."""
        # Verifica que a única aparição de 'account' em read_only_fields é a correta
        tree = ast.parse(self.src)
        for node in ast.walk(tree):
            if (isinstance(node, ast.ClassDef)
                    and node.name == "MessengerConversationSerializer"):
                for meta in ast.walk(node):
                    if isinstance(meta, ast.ClassDef) and meta.name == "Meta":
                        for stmt in meta.body:
                            if (isinstance(stmt, ast.Assign)
                                    and any(
                                        isinstance(t, ast.Name) and t.id == "read_only_fields"
                                        for t in stmt.targets
                                    )):
                                val = stmt.value
                                if isinstance(val, (ast.List, ast.Tuple)):
                                    elems = [
                                        e.value for e in val.elts
                                        if isinstance(e, ast.Constant)
                                    ]
                                    self.assertIn("account", elems)
                                    return
        self.fail("Meta.read_only_fields não encontrada em MessengerConversationSerializer")


class TestMessengerConversationViewSetPerformCreate(unittest.TestCase):
    """perform_create deve validar tenant antes de criar conversa [IDOR create fix]."""

    def setUp(self):
        self.src = _source(VIEWS_PATH)

    def test_perform_create_existe_no_viewset(self):
        """MessengerConversationViewSet deve ter perform_create."""
        body = _extract_method(self.src, "MessengerConversationViewSet", "perform_create")
        self.assertTrue(body, "perform_create não encontrado em MessengerConversationViewSet")

    def test_perform_create_valida_account_id(self):
        """perform_create deve exigir account na criação."""
        body = _extract_method(self.src, "MessengerConversationViewSet", "perform_create")
        self.assertIn("account", body, "perform_create não valida campo account")

    def test_perform_create_filtra_por_user(self):
        """perform_create deve filtrar a conta pelo user autenticado (não é_superuser)."""
        body = _extract_method(self.src, "MessengerConversationViewSet", "perform_create")
        self.assertTrue(body, "perform_create não encontrado")
        # Deve checar is_superuser para decidir escopo
        self.assertIn("is_superuser", body, "perform_create não verifica is_superuser para escopo")
        # Deve filtrar por user do request
        self.assertIn("user", body, "perform_create não filtra conta pelo user do request")

    def test_perform_create_injeta_account_no_save(self):
        """perform_create deve injetar account no serializer.save()."""
        body = _extract_method(self.src, "MessengerConversationViewSet", "perform_create")
        self.assertTrue(body, "perform_create não encontrado")
        self.assertIn("serializer.save(", body, "perform_create não chama serializer.save")
        self.assertIn("account=account", body, "perform_create não injeta account no save")


if __name__ == "__main__":
    unittest.main()
