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


def _sem_comentarios(fonte: str) -> str:
    """Código sem comentários.

    Um assert de "não contém is_superuser" na fonte crua quebra quando o
    comentário EXPLICA que não há bypass de superuser — que é justamente o que
    se quer documentar. O alvo é o código, não o texto sobre ele.
    """
    linhas = []
    for linha in fonte.splitlines():
        sem = linha.split('#', 1)[0]
        if sem.strip():
            linhas.append(sem)
    return '\n'.join(linhas)


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

    def test_nao_tem_bypass_de_conta(self):
        """16/set: superuser deixou de ser chave-mestra. Acesso vem de vínculo.

        Nem is_staff nem is_superuser: `_accessible_agents` escopa todo mundo
        pelas contas do vínculo.
        """
        source = _sem_comentarios(self._func_source())
        self.assertNotIn('is_superuser', source)
        self.assertNotIn('is_staff', source)

    def test_escopa_por_conta_acessivel(self):
        """Âncora: sem isto, "não tem bypass" passaria num arquivo vazio."""
        self.assertIn('accessible_whatsapp_account_ids', self._func_source())


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

    def test_nao_tem_bypass_de_conta(self):
        """16/set: superuser deixou de ser chave-mestra. Acesso vem de vínculo."""
        source = _sem_comentarios(self._func_source())
        self.assertNotIn('is_superuser', source)
        self.assertNotIn('is_staff', source)

    def test_escopa_por_conta_acessivel(self):
        """Âncora: sem isto, "não tem bypass" passaria num arquivo vazio."""
        self.assertIn('accessible_whatsapp_account_ids', self._func_source())


class AccessibleAgentsFallbackTest(SimpleTestCase):
    """Regressão (auditoria 17/jul, crítico nº1): usuário sem conta WhatsApp
    NÃO pode cair num fallback que devolve todos os agentes ativos — isso
    expunha conversations/history/process/clear_memory cross-tenant.

    Leitura de fonte (sem importar o módulo) pelo mesmo motivo dos demais
    testes deste arquivo: langchain_core indisponível no container de CI.
    """

    def test_nao_existe_retorno_irrestrito(self):
        """Todo caminho tem que passar por .filter().

        Antes isto era verificado exigindo `queryset.none()` literal no código.
        Passou a haver um caminho legítimo a mais (lojista dono da loja sem
        conta WhatsApp vinculada), então a garantia migrou para a propriedade:
        nenhum `return queryset` cru — e desde 16/set não há mais early
        return de superuser nenhum.
        O isolamento real é provado em
        test_agent_write_response_contract.py::test_usuario_de_outro_tenant_nao_ve_o_agente.
        """
        source = _read_views_source()
        func = _extract_function(source, '_accessible_agents')

        self.assertNotIn('fall back to all active agents', func,
                         'fallback perigoso (todos os agentes) não pode voltar')

        retornos = re.findall(r'^\s*return\s+(.+)$', func, flags=re.MULTILINE)
        # O primeiro é o early return do superuser; os demais têm que ser filtrados.
        for expr in retornos[1:]:
            self.assertTrue(
                '.filter(' in expr or '.none()' in expr,
                f'retorno sem escopo de tenant em _accessible_agents: {expr!r}',
            )
