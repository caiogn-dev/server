"""Regressão de segurança: switch_to_human sem verificação de acesso cross-tenant.

Bug: ConversationViewSet.switch_to_human (views.py) aceita agent_id sem
verificar se o agente tem acesso à conta da conversa, ao contrário de
assign_agent que já possui essa verificação (is_superuser + accessible_whatsapp_account_ids).

Ataque:
  - Usuário autenticado (tenant A) obtém id de usuário de tenant B
  - POST /conversations/{id}/switch_to_human/ {"agent_id": <id_do_tenant_B>}
  - Conversa do tenant A é atribuída ao usuário do tenant B
  - Usuário do tenant B passa a ver histórico/PII de clientes do tenant A
  - is_superuser=False nunca passa pelo guard → atribuição silenciosa cross-tenant

Correção: copiar a verificação que já existe em assign_agent.
Convenção: is_staff não concede acesso cross-tenant; apenas is_superuser.
"""
import ast
import os
from pathlib import Path
from django.test import SimpleTestCase


VIEWS_PATH = Path(__file__).resolve().parents[1] / 'api' / 'views.py'


def _extract_method_source(path: Path, class_name: str, method_name: str) -> str:
    """Extrai o texto-fonte de um método via AST sem importar o módulo."""
    source = path.read_text()
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
                    start = item.lineno - 1
                    end = item.end_lineno
                    return '\n'.join(lines[start:end])
    raise ValueError(f'{class_name}.{method_name} não encontrado em {path}')


class SwitchToHumanCrossTenantSourceTest(SimpleTestCase):
    """Verifica estaticamente que switch_to_human valida acesso cross-tenant."""

    def setUp(self):
        self.src = _extract_method_source(VIEWS_PATH, 'ConversationViewSet', 'switch_to_human')

    def test_usa_is_superuser_como_bypass(self):
        """switch_to_human deve verificar agent.is_superuser antes de bypassar checagem."""
        self.assertIn(
            'is_superuser',
            self.src,
            "switch_to_human não verifica agent.is_superuser — qualquer "
            "usuário autenticado pode atribuir uma conversa a um agente de "
            "outro tenant (IDOR: exposição de PII de clientes).",
        )

    def test_usa_accessible_whatsapp_account_ids(self):
        """switch_to_human deve usar accessible_whatsapp_account_ids para validar o agente."""
        self.assertIn(
            'accessible_whatsapp_account_ids',
            self.src,
            "switch_to_human não chama accessible_whatsapp_account_ids — "
            "agentes de outros tenants podem ser atribuídos sem verificação.",
        )

    def test_retorna_403_quando_sem_acesso(self):
        """switch_to_human deve retornar HTTP 403 para agente de outro tenant."""
        self.assertIn(
            'HTTP_403_FORBIDDEN',
            self.src,
            "switch_to_human não retorna 403 para agente sem acesso à conta — "
            "a atribuição cross-tenant não é rejeitada.",
        )

    def test_nao_usa_agent_is_staff_como_bypass(self):
        """agent.is_staff não deve aparecer como condição de bypass cross-tenant."""
        self.assertNotIn(
            'agent.is_staff',
            self.src,
            "switch_to_human usa agent.is_staff como bypass de verificação cross-tenant — "
            "is_staff é apenas acesso ao /admin, não ao cross-tenant.",
        )
