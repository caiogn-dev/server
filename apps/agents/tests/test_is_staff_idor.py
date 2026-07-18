"""Regressão de segurança: is_staff bypassa escopo de tenant em apps.agents.

Bugs corrigidos:
1. _accessible_agents (views.py:33) — is_staff vê TODOS os agentes IA de
   todos os tenants (IDOR de leitura cross-tenant).
2. _enforce_account_scope (views.py:70) — is_staff pode criar/editar agentes
   associados a contas de outros tenants sem bloqueio (IDOR de escrita).

Testes usam leitura de fonte direta (sem importar o módulo) para evitar
dependência transitiva de langchain_core não instalado no container de CI.

Convenção do projeto: is_staff = acesso ao Django /admin.
Apenas is_superuser tem acesso cross-tenant irrestrito.
"""
import os
import re
from django.test import SimpleTestCase

_VIEWS_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'views.py'
)


def _read_views_source():
    with open(_VIEWS_PATH, 'r', encoding='utf-8') as f:
        return f.read()


def _extract_function(source, name):
    """Extrai o bloco de uma função/método por indentação."""
    lines = source.splitlines()
    start = None
    base_indent = None
    block = []
    for i, line in enumerate(lines):
        if start is None:
            if re.search(rf'def {re.escape(name)}\s*\(', line):
                start = i
                base_indent = len(line) - len(line.lstrip())
                block.append(line)
        else:
            if line.strip() == '':
                block.append(line)
                continue
            indent = len(line) - len(line.lstrip())
            if indent <= base_indent and line.strip():
                break
            block.append(line)
    return '\n'.join(block)


class AccessibleAgentsSourceTest(SimpleTestCase):
    """Verifica via fonte que _accessible_agents não usa is_staff como bypass."""

    def _func_source(self):
        return _extract_function(_read_views_source(), '_accessible_agents')

    def test_nao_usa_is_staff_como_bypass(self):
        source = self._func_source()
        self.assertNotIn('or user.is_staff', source,
            "_accessible_agents usa 'or user.is_staff' como bypass cross-tenant — "
            "is_staff NÃO deve dar acesso irrestrito (só is_superuser)")

    def test_usa_is_superuser(self):
        source = self._func_source()
        self.assertIn('is_superuser', source,
            "_accessible_agents deve verificar is_superuser")

    def test_linha_de_bypass_usa_apenas_superuser(self):
        """A condição de retorno antecipado usa apenas is_superuser."""
        source = self._func_source()
        # Encontra a linha de retorno antecipado (if user.is_superuser...: return)
        match = re.search(r'if\s+user\.is_superuser\b[^:]*:', source)
        self.assertIsNotNone(match,
            "Não encontrou padrão 'if user.is_superuser...:' em _accessible_agents")
        # A condição não deve incluir is_staff
        condition = match.group(0)
        self.assertNotIn('is_staff', condition,
            f"Condição de bypass inclui is_staff: {condition!r}")


class EnforceAccountScopeSourceTest(SimpleTestCase):
    """Verifica via fonte que _enforce_account_scope não usa is_staff como bypass."""

    def _func_source(self):
        return _extract_function(_read_views_source(), '_enforce_account_scope')

    def test_nao_usa_is_staff_como_bypass(self):
        source = self._func_source()
        # Verifica especificamente o padrão de bypass (não comentários)
        self.assertNotIn('or self.request.user.is_staff', source,
            "_enforce_account_scope usa 'or self.request.user.is_staff' como bypass — "
            "is_staff NÃO deve bypassar verificação de conta (só is_superuser)")

    def test_usa_is_superuser(self):
        source = self._func_source()
        self.assertIn('is_superuser', source,
            "_enforce_account_scope deve verificar is_superuser")

    def test_linha_de_bypass_usa_apenas_superuser(self):
        """O early return usa apenas is_superuser."""
        source = self._func_source()
        match = re.search(r'if\s+self\.request\.user\.is_superuser\b[^:]*:', source)
        self.assertIsNotNone(match,
            "Não encontrou padrão 'if self.request.user.is_superuser...:' "
            "em _enforce_account_scope")
        condition = match.group(0)
        self.assertNotIn('is_staff', condition,
            f"Condição de bypass inclui is_staff: {condition!r}")
