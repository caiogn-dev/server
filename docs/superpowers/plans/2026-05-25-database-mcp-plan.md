# Database MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `/home/graco/WORK/server2/mcp_database.py` — an MCP server with 26 tools giving Claude Code full read/write access to the Cardapidex PostgreSQL database, with SAFE_MODE write protection for production.

**Architecture:** Single file, identical bootstrap pattern to `mcp_whatsapp_bot.py` (Django setup → Server → helpers → list_tools → call_tool → implementations → main). SAFE_MODE controlled by `MCP_DB_SAFE_MODE` env var (default `true`). Tools split across 6 groups: PostgreSQL tables (6), Django schema (4), migrations (4), queries (3), integrity (4), business (5).

**Tech Stack:** Python 3.11, Django 4 ORM, `django.db.connection` for raw SQL, `mcp` SDK (already installed), `psycopg2` (already installed via Django).

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `/home/graco/WORK/server2/mcp_database.py` | Create | All 26 tools — single file like mcp_whatsapp_bot.py |
| `/home/graco/WORK/server2/tests/test_mcp_database.py` | Create | Unit tests for SAFE_MODE logic, masking, SQL guards |

---

## Task 1: Scaffold — bootstrap, SAFE_MODE, helpers, all 26 tool schemas, stubs

**Files:**
- Create: `mcp_database.py`
- Create: `tests/test_mcp_database.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mcp_database.py
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

import sys
_here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _here not in sys.path:
    sys.path.insert(0, _here)
django.setup()

import asyncio
import importlib
import unittest


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestScaffold(unittest.TestCase):
    def setUp(self):
        os.environ['MCP_DB_SAFE_MODE'] = 'true'
        import mcp_database
        importlib.reload(mcp_database)
        self.mod = mcp_database

    def test_26_tools_registered(self):
        tools = run(self.mod.list_tools())
        self.assertEqual(len(tools), 26)

    def test_tool_names(self):
        tools = run(self.mod.list_tools())
        names = {t.name for t in tools}
        expected = {
            'list_tables', 'table_schema', 'table_stats', 'explain_query',
            'table_indexes', 'compare_model_vs_table',
            'schema_overview', 'model_detail', 'find_field', 'relationship_graph',
            'migration_status', 'make_migrations', 'run_migrations', 'show_migration_sql',
            'count_records', 'sample_records', 'run_sql',
            'integrity_report', 'find_orphans', 'find_duplicates', 'check_nulls',
            'find_ghost_users', 'customer_identity_audit', 'stats_drift_check',
            'security_audit', 'pgvector_readiness',
        }
        self.assertEqual(names, expected)

    def test_unknown_tool_returns_error(self):
        result = run(self.mod.call_tool('nonexistent_tool', {}))
        self.assertIn('error', result[0].text)

    def test_mask_sensitive_redacts_in_safe_mode(self):
        record = {'name': 'João', 'api_key': 'secret123', 'email': 'a@b.com'}
        masked = self.mod._mask_sensitive(record)
        self.assertEqual(masked['api_key'], '***REDACTED***')
        self.assertEqual(masked['name'], 'João')

    def test_mask_sensitive_passthrough_when_safe_mode_off(self):
        os.environ['MCP_DB_SAFE_MODE'] = 'false'
        importlib.reload(self.mod)
        record = {'api_key': 'secret123'}
        masked = self.mod._mask_sensitive(record)
        self.assertEqual(masked['api_key'], 'secret123')

    def test_safe_mode_blocks_write_without_confirm(self):
        os.environ['MCP_DB_SAFE_MODE'] = 'true'
        importlib.reload(self.mod)
        result = run(self.mod.call_tool('run_sql', {'sql': 'UPDATE stores_store SET name=%s WHERE id=1', 'params': ['x']}))
        self.assertIn('error', result[0].text)
        self.assertIn('confirm', result[0].text)

    def test_safe_mode_blocks_drop_even_with_confirm(self):
        os.environ['MCP_DB_SAFE_MODE'] = 'true'
        importlib.reload(self.mod)
        result = run(self.mod.call_tool('run_sql', {'sql': 'DROP TABLE stores_store', 'confirm': True}))
        self.assertIn('error', result[0].text)
        self.assertIn('bloqueado', result[0].text)

    def test_make_migrations_requires_confirm_in_safe_mode(self):
        os.environ['MCP_DB_SAFE_MODE'] = 'true'
        importlib.reload(self.mod)
        result = run(self.mod.call_tool('make_migrations', {}))
        self.assertIn('error', result[0].text)
        self.assertIn('confirm', result[0].text)

    def test_run_migrations_requires_confirm_in_safe_mode(self):
        os.environ['MCP_DB_SAFE_MODE'] = 'true'
        importlib.reload(self.mod)
        result = run(self.mod.call_tool('run_migrations', {}))
        self.assertIn('error', result[0].text)
        self.assertIn('confirm', result[0].text)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/graco/WORK/server2
python tests/test_mcp_database.py
```

Expected: `ModuleNotFoundError: No module named 'mcp_database'`

- [ ] **Step 3: Create `mcp_database.py` with full scaffold**

```python
#!/usr/bin/env python
"""
MCP Server — Database Inspector & Manager
==========================================

Fornece ao Claude Code acesso completo ao banco de dados do Cardapidex:
inspeção de schema, queries, migrations, análise de integridade e
ferramentas de domínio específicas do Cardapidex.

Ferramentas (26 no total):
  Grupo 0 — PostgreSQL Tables:  list_tables, table_schema, table_stats,
                                 explain_query, table_indexes, compare_model_vs_table
  Grupo 1 — Schema Django:      schema_overview, model_detail, find_field, relationship_graph
  Grupo 2 — Migrations:         migration_status, make_migrations, run_migrations, show_migration_sql
  Grupo 3 — Queries:            count_records, sample_records, run_sql
  Grupo 4 — Integridade:        integrity_report, find_orphans, find_duplicates, check_nulls
  Grupo 5 — Negócio:            find_ghost_users, customer_identity_audit, stats_drift_check,
                                 security_audit, pgvector_readiness

Registrar no Claude Code:
  claude mcp add database -- python /home/graco/WORK/server2/mcp_database.py

Produção (SAFE_MODE ativo por padrão):
  claude mcp add database-prod -- env MCP_DB_SAFE_MODE=true python /home/graco/WORK/server2/mcp_database.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import textwrap
from typing import Any

# ─── Bootstrap Django ─────────────────────────────────────────────────────────
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

import django
django.setup()

# ─── MCP SDK ─────────────────────────────────────────────────────────────────
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server('cardapidex-database')

# ─── SAFE_MODE ────────────────────────────────────────────────────────────────
# true  → writes require confirm=true; DROP/TRUNCATE/ALTER TABLE always blocked
# false → sem restrições (dev local)
SAFE_MODE = os.environ.get('MCP_DB_SAFE_MODE', 'true').lower() == 'true'

_SENSITIVE_KEYWORDS = (
    'token', 'key', 'secret', 'password', 'api_key',
    'access_token', 'refresh_token', 'encrypted',
)

_BLOCKED_STATEMENTS = ('DROP', 'TRUNCATE', 'ALTER TABLE')


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _j(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def _ok(data: Any) -> list[TextContent]:
    return [TextContent(type='text', text=_j(data))]


def _err(msg: str) -> list[TextContent]:
    return [TextContent(type='text', text=json.dumps({'error': msg}, ensure_ascii=False))]


def _mask_sensitive(record: dict) -> dict:
    """Replace sensitive field values with '***REDACTED***' when SAFE_MODE is on."""
    if not SAFE_MODE:
        return record
    return {
        k: '***REDACTED***' if any(kw in k.lower() for kw in _SENSITIVE_KEYWORDS) else v
        for k, v in record.items()
    }


# ══════════════════════════════════════════════════════════════════════════════
#  DEFINIÇÃO DAS FERRAMENTAS
# ══════════════════════════════════════════════════════════════════════════════

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        # ── Grupo 0: PostgreSQL Tables ──────────────────────────────────────
        Tool(
            name='list_tables',
            description='Lista todas as tabelas do banco com row_count, tamanho e se tem model Django.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'schema': {'type': 'string', 'default': 'public'},
                    'filter': {'type': 'string', 'description': 'Substring match no nome da tabela'},
                },
                'required': [],
            },
        ),
        Tool(
            name='table_schema',
            description='Estrutura completa de uma tabela: colunas, indexes, foreign keys, triggers.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'table_name': {'type': 'string'},
                },
                'required': ['table_name'],
            },
        ),
        Tool(
            name='table_stats',
            description='Estatísticas pg_stat_user_tables: linhas, tamanho, seq_scans, idx_scans, last_vacuum.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'table_name': {'type': 'string', 'description': 'Se vazio, retorna top 20 por tamanho'},
                },
                'required': [],
            },
        ),
        Tool(
            name='explain_query',
            description='EXPLAIN (ANALYZE opcional) de uma query SQL. analyze=false não executa.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'sql': {'type': 'string'},
                    'params': {'type': 'array', 'items': {}, 'default': []},
                    'analyze': {'type': 'boolean', 'default': False},
                },
                'required': ['sql'],
            },
        ),
        Tool(
            name='table_indexes',
            description='Todos os indexes de uma tabela com uso. Detecta FKs sem index.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'table_name': {'type': 'string'},
                },
                'required': ['table_name'],
            },
        ),
        Tool(
            name='compare_model_vs_table',
            description='Diff entre o Django model e a tabela real no PostgreSQL.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'model_name': {'type': 'string', 'description': 'Ex: StoreCustomer ou stores.StoreCustomer'},
                },
                'required': ['model_name'],
            },
        ),

        # ── Grupo 1: Schema Django ──────────────────────────────────────────
        Tool(
            name='schema_overview',
            description='Mapa completo de todos os apps → models → fields com row_count.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'app_filter': {'type': 'string', 'description': 'Ex: stores, users, automation'},
                },
                'required': [],
            },
        ),
        Tool(
            name='model_detail',
            description='Deep dive em um model: campos, FKs, reverse relations, unique_together, 3 samples.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'model_name': {'type': 'string'},
                },
                'required': ['model_name'],
            },
        ),
        Tool(
            name='find_field',
            description='Encontra todos os models com um campo de nome ou tipo específico.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'field_name': {'type': 'string', 'description': 'Ex: phone, unified_user_id'},
                    'field_type': {'type': 'string', 'description': 'Ex: JSONField, UUIDField, ForeignKey'},
                },
                'required': [],
            },
        ),
        Tool(
            name='relationship_graph',
            description='Grafo de dependências FK de um model (entrada e saída) até a profundidade N.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'model_name': {'type': 'string'},
                    'depth': {'type': 'integer', 'default': 2},
                },
                'required': ['model_name'],
            },
        ),

        # ── Grupo 2: Migrations ─────────────────────────────────────────────
        Tool(
            name='migration_status',
            description='Estado de todas as migrations: aplicadas e pendentes.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'app': {'type': 'string', 'description': 'Filtrar por app (opcional)'},
                },
                'required': [],
            },
        ),
        Tool(
            name='make_migrations',
            description='Cria novas migrations para mudanças de model. Requer confirm=true em SAFE_MODE.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'app': {'type': 'string'},
                    'name': {'type': 'string'},
                    'confirm': {'type': 'boolean', 'default': False},
                },
                'required': [],
            },
        ),
        Tool(
            name='run_migrations',
            description='Aplica migrations pendentes. Requer confirm=true em SAFE_MODE.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'app': {'type': 'string'},
                    'migration': {'type': 'string'},
                    'confirm': {'type': 'boolean', 'default': False},
                },
                'required': [],
            },
        ),
        Tool(
            name='show_migration_sql',
            description='SQL que seria executado por uma migration (dry-run via sqlmigrate).',
            inputSchema={
                'type': 'object',
                'properties': {
                    'app': {'type': 'string'},
                    'migration': {'type': 'string'},
                },
                'required': ['app', 'migration'],
            },
        ),

        # ── Grupo 3: Queries ────────────────────────────────────────────────
        Tool(
            name='count_records',
            description='Conta registros com filtro ORM opcional.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'model_name': {'type': 'string'},
                    'filter': {'type': 'object', 'description': 'ORM filter kwargs: {"is_active": true}'},
                },
                'required': ['model_name'],
            },
        ),
        Tool(
            name='sample_records',
            description='Retorna N registros de um model. Mascara campos sensíveis em SAFE_MODE.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'model_name': {'type': 'string'},
                    'limit': {'type': 'integer', 'default': 5},
                    'filter': {'type': 'object'},
                    'order_by': {'type': 'string', 'default': '-pk'},
                },
                'required': ['model_name'],
            },
        ),
        Tool(
            name='run_sql',
            description=textwrap.dedent("""\
                Executa SQL arbitrário. Em SAFE_MODE:
                  - writes (INSERT/UPDATE/DELETE) exigem confirm=true
                  - DROP, TRUNCATE, ALTER TABLE bloqueados sempre
                Timeout de 30s em writes e EXPLAIN ANALYZE.
            """),
            inputSchema={
                'type': 'object',
                'properties': {
                    'sql': {'type': 'string'},
                    'params': {'type': 'array', 'items': {}, 'default': []},
                    'confirm': {'type': 'boolean', 'default': False},
                },
                'required': ['sql'],
            },
        ),

        # ── Grupo 4: Integridade ────────────────────────────────────────────
        Tool(
            name='integrity_report',
            description='Relatório completo: FKs quebradas, nulls inesperados, por app ou tudo.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'app': {'type': 'string', 'description': 'Se vazio, verifica todos os apps'},
                },
                'required': [],
            },
        ),
        Tool(
            name='find_orphans',
            description='Registros com FK quebrada (referencia registro inexistente).',
            inputSchema={
                'type': 'object',
                'properties': {
                    'model_name': {'type': 'string'},
                    'field_name': {'type': 'string'},
                },
                'required': ['model_name', 'field_name'],
            },
        ),
        Tool(
            name='find_duplicates',
            description='Agrupa registros duplicados por combinação de campos.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'model_name': {'type': 'string'},
                    'fields': {'type': 'array', 'items': {'type': 'string'}},
                },
                'required': ['model_name', 'fields'],
            },
        ),
        Tool(
            name='check_nulls',
            description='Campos com nulls. Se model_name vazio, verifica todos os models.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'model_name': {'type': 'string'},
                },
                'required': [],
            },
        ),

        # ── Grupo 5: Negócio Cardapidex ─────────────────────────────────────
        Tool(
            name='find_ghost_users',
            description='auth.Users criados artificialmente para clientes WhatsApp (email @pastita.local ou username cliente_*).',
            inputSchema={
                'type': 'object',
                'properties': {
                    'limit': {'type': 'integer', 'default': 20},
                },
                'required': [],
            },
        ),
        Tool(
            name='customer_identity_audit',
            description='Análise completa do triângulo de identidade: auth.User + UnifiedUser + StoreCustomer.',
            inputSchema={'type': 'object', 'properties': {}, 'required': []},
        ),
        Tool(
            name='stats_drift_check',
            description='Detecta divergência entre total_orders/total_spent cacheados e a fonte real (StoreOrder).',
            inputSchema={
                'type': 'object',
                'properties': {
                    'store_slug': {'type': 'string'},
                    'limit': {'type': 'integer', 'default': 20},
                },
                'required': [],
            },
        ),
        Tool(
            name='security_audit',
            description='Encontra campos sensíveis (token, key, secret, password) armazenados sem criptografia.',
            inputSchema={'type': 'object', 'properties': {}, 'required': []},
        ),
        Tool(
            name='pgvector_readiness',
            description='Verifica disponibilidade do pgvector: extensão instalada, versão PG, package Python.',
            inputSchema={'type': 'object', 'properties': {}, 'required': []},
        ),
    ]


# ══════════════════════════════════════════════════════════════════════════════
#  DISPATCHER
# ══════════════════════════════════════════════════════════════════════════════

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        dispatch = {
            # Grupo 0
            'list_tables': _list_tables,
            'table_schema': _table_schema,
            'table_stats': _table_stats,
            'explain_query': _explain_query,
            'table_indexes': _table_indexes,
            'compare_model_vs_table': _compare_model_vs_table,
            # Grupo 1
            'schema_overview': _schema_overview,
            'model_detail': _model_detail,
            'find_field': _find_field,
            'relationship_graph': _relationship_graph,
            # Grupo 2
            'migration_status': _migration_status,
            'make_migrations': _make_migrations,
            'run_migrations': _run_migrations,
            'show_migration_sql': _show_migration_sql,
            # Grupo 3
            'count_records': _count_records,
            'sample_records': _sample_records,
            'run_sql': _run_sql,
            # Grupo 4
            'integrity_report': _integrity_report,
            'find_orphans': _find_orphans,
            'find_duplicates': _find_duplicates,
            'check_nulls': _check_nulls,
            # Grupo 5
            'find_ghost_users': _find_ghost_users,
            'customer_identity_audit': _customer_identity_audit,
            'stats_drift_check': _stats_drift_check,
            'security_audit': _security_audit,
            'pgvector_readiness': _pgvector_readiness,
        }
        fn = dispatch.get(name)
        if fn is None:
            return _err(f'Ferramenta desconhecida: {name}')
        return await fn(arguments)
    except Exception as exc:
        import traceback
        return _err(f'{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}')


# ══════════════════════════════════════════════════════════════════════════════
#  IMPLEMENTAÇÕES — GRUPO 0: PostgreSQL Tables (stubs → preenchidos na Task 2)
# ══════════════════════════════════════════════════════════════════════════════

async def _list_tables(args: dict) -> list[TextContent]:
    return _err('Not implemented yet — Task 2')

async def _table_schema(args: dict) -> list[TextContent]:
    return _err('Not implemented yet — Task 2')

async def _table_stats(args: dict) -> list[TextContent]:
    return _err('Not implemented yet — Task 2')

async def _explain_query(args: dict) -> list[TextContent]:
    return _err('Not implemented yet — Task 2')

async def _table_indexes(args: dict) -> list[TextContent]:
    return _err('Not implemented yet — Task 2')

async def _compare_model_vs_table(args: dict) -> list[TextContent]:
    return _err('Not implemented yet — Task 2')


# ══════════════════════════════════════════════════════════════════════════════
#  IMPLEMENTAÇÕES — GRUPO 1: Schema Django (stubs → preenchidos na Task 3)
# ══════════════════════════════════════════════════════════════════════════════

async def _schema_overview(args: dict) -> list[TextContent]:
    return _err('Not implemented yet — Task 3')

async def _model_detail(args: dict) -> list[TextContent]:
    return _err('Not implemented yet — Task 3')

async def _find_field(args: dict) -> list[TextContent]:
    return _err('Not implemented yet — Task 3')

async def _relationship_graph(args: dict) -> list[TextContent]:
    return _err('Not implemented yet — Task 3')


# ══════════════════════════════════════════════════════════════════════════════
#  IMPLEMENTAÇÕES — GRUPO 2: Migrations (stubs → preenchidos na Task 4)
# ══════════════════════════════════════════════════════════════════════════════

async def _migration_status(args: dict) -> list[TextContent]:
    return _err('Not implemented yet — Task 4')

async def _make_migrations(args: dict) -> list[TextContent]:
    if SAFE_MODE and not args.get('confirm'):
        return _err('SAFE_MODE ativo — forneça confirm=true para criar migrations')
    return _err('Not implemented yet — Task 4')

async def _run_migrations(args: dict) -> list[TextContent]:
    if SAFE_MODE and not args.get('confirm'):
        return _err('SAFE_MODE ativo — forneça confirm=true para aplicar migrations')
    return _err('Not implemented yet — Task 4')

async def _show_migration_sql(args: dict) -> list[TextContent]:
    return _err('Not implemented yet — Task 4')


# ══════════════════════════════════════════════════════════════════════════════
#  IMPLEMENTAÇÕES — GRUPO 3: Queries (stubs → preenchidos na Task 5)
# ══════════════════════════════════════════════════════════════════════════════

async def _count_records(args: dict) -> list[TextContent]:
    return _err('Not implemented yet — Task 5')

async def _sample_records(args: dict) -> list[TextContent]:
    return _err('Not implemented yet — Task 5')

async def _run_sql(args: dict) -> list[TextContent]:
    sql = args.get('sql', '')
    sql_upper = sql.strip().upper()
    is_write = any(sql_upper.startswith(kw) for kw in ('INSERT', 'UPDATE', 'DELETE'))

    for blocked in _BLOCKED_STATEMENTS:
        if blocked in sql_upper:
            return _err(f'SQL bloqueado: {blocked} não é permitido. Use migrations para mudanças de schema.')

    if SAFE_MODE and is_write and not args.get('confirm'):
        return _err(
            f'SAFE_MODE ativo — escrita requer confirm=true. '
            f'SQL detectado como write (começa com {sql_upper.split()[0] if sql_upper else "?"}).'
        )

    return _err('Not implemented yet — Task 5')


# ══════════════════════════════════════════════════════════════════════════════
#  IMPLEMENTAÇÕES — GRUPO 4: Integridade (stubs → preenchidos na Task 6)
# ══════════════════════════════════════════════════════════════════════════════

async def _integrity_report(args: dict) -> list[TextContent]:
    return _err('Not implemented yet — Task 6')

async def _find_orphans(args: dict) -> list[TextContent]:
    return _err('Not implemented yet — Task 6')

async def _find_duplicates(args: dict) -> list[TextContent]:
    return _err('Not implemented yet — Task 6')

async def _check_nulls(args: dict) -> list[TextContent]:
    return _err('Not implemented yet — Task 6')


# ══════════════════════════════════════════════════════════════════════════════
#  IMPLEMENTAÇÕES — GRUPO 5: Negócio (stubs → preenchidos na Task 7)
# ══════════════════════════════════════════════════════════════════════════════

async def _find_ghost_users(args: dict) -> list[TextContent]:
    return _err('Not implemented yet — Task 7')

async def _customer_identity_audit(args: dict) -> list[TextContent]:
    return _err('Not implemented yet — Task 7')

async def _stats_drift_check(args: dict) -> list[TextContent]:
    return _err('Not implemented yet — Task 7')

async def _security_audit(args: dict) -> list[TextContent]:
    return _err('Not implemented yet — Task 7')

async def _pgvector_readiness(args: dict) -> list[TextContent]:
    return _err('Not implemented yet — Task 7')


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == '__main__':
    asyncio.run(main())
```

- [ ] **Step 4: Run tests**

```bash
cd /home/graco/WORK/server2
python tests/test_mcp_database.py -v
```

Expected: All 9 tests PASS. The SAFE_MODE tests pass because `_run_sql`, `_make_migrations`, `_run_migrations` already have the guard logic in the stubs.

- [ ] **Step 5: Commit**

```bash
cd /home/graco/WORK/server2
git add mcp_database.py tests/test_mcp_database.py
git commit -m "mcp_database: scaffold com 26 tools, SAFE_MODE e testes"
```

---

## Task 2: Grupo 0 — PostgreSQL table tools (6 ferramentas)

**Files:**
- Modify: `mcp_database.py` — replace 6 stubs in Grupo 0

- [ ] **Step 1: Write failing integration test**

Add to `tests/test_mcp_database.py`:

```python
class TestGroup0PostgreSQL(django.test.TestCase):
    def setUp(self):
        os.environ['MCP_DB_SAFE_MODE'] = 'true'
        import mcp_database
        importlib.reload(mcp_database)
        self.mod = mcp_database

    def test_list_tables_returns_list(self):
        result = run(self.mod.call_tool('list_tables', {}))
        data = json.loads(result[0].text)
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    def test_list_tables_has_expected_keys(self):
        result = run(self.mod.call_tool('list_tables', {}))
        data = json.loads(result[0].text)
        first = data[0]
        self.assertIn('table_name', first)
        self.assertIn('row_count', first)
        self.assertIn('has_django_model', first)

    def test_list_tables_filter(self):
        result = run(self.mod.call_tool('list_tables', {'filter': 'stores_store'}))
        data = json.loads(result[0].text)
        self.assertTrue(all('stores_store' in t['table_name'] for t in data))

    def test_table_schema_returns_columns(self):
        result = run(self.mod.call_tool('table_schema', {'table_name': 'stores_store'}))
        data = json.loads(result[0].text)
        self.assertIn('columns', data)
        self.assertIn('indexes', data)
        self.assertIn('constraints', data)
        self.assertGreater(len(data['columns']), 0)

    def test_table_stats_top20(self):
        result = run(self.mod.call_tool('table_stats', {}))
        data = json.loads(result[0].text)
        self.assertIsInstance(data, list)

    def test_table_indexes_returns_structure(self):
        result = run(self.mod.call_tool('table_indexes', {'table_name': 'stores_store'}))
        data = json.loads(result[0].text)
        self.assertIn('indexes', data)
        self.assertIn('missing_fk_indexes', data)

    def test_compare_model_vs_table_ok(self):
        result = run(self.mod.call_tool('compare_model_vs_table', {'model_name': 'Store'}))
        data = json.loads(result[0].text)
        self.assertIn('in_model_not_in_table', data)
        self.assertIn('in_table_not_in_model', data)

    def test_compare_model_vs_table_unknown(self):
        result = run(self.mod.call_tool('compare_model_vs_table', {'model_name': 'NonExistentModel'}))
        data = json.loads(result[0].text)
        self.assertIn('error', data)
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /home/graco/WORK/server2
python -m pytest tests/test_mcp_database.py::TestGroup0PostgreSQL -v
```

Expected: All fail with `AssertionError` (`'error'` in response because stubs return "Not implemented yet").

- [ ] **Step 3: Implement the 6 Group 0 functions**

Replace the 6 stub functions in `mcp_database.py` Grupo 0 section:

```python
async def _list_tables(args: dict) -> list[TextContent]:
    from django.db import connection
    from django.apps import apps

    schema = args.get('schema', 'public')
    filter_str = args.get('filter', '')

    model_table_map = {
        model._meta.db_table: f'{model._meta.app_label}.{model.__name__}'
        for model in apps.get_models()
    }

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                t.table_name,
                COALESCE(s.n_live_tup, 0) AS row_count,
                pg_size_pretty(pg_total_relation_size(quote_ident(t.table_name))) AS size_pretty
            FROM information_schema.tables t
            LEFT JOIN pg_stat_user_tables s ON s.relname = t.table_name
            WHERE t.table_schema = %s AND t.table_type = 'BASE TABLE'
            ORDER BY t.table_name
        """, [schema])
        rows = cursor.fetchall()

    result = []
    for table_name, row_count, size_pretty in rows:
        if filter_str and filter_str not in table_name:
            continue
        result.append({
            'table_name': table_name,
            'row_count': row_count,
            'size_pretty': size_pretty or '0 bytes',
            'has_django_model': table_name in model_table_map,
            'django_model': model_table_map.get(table_name),
        })

    return _ok(result)


async def _table_schema(args: dict) -> list[TextContent]:
    from django.db import connection

    table_name = args['table_name']

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
        """, [table_name])
        columns = [
            {'name': r[0], 'pg_type': r[1], 'nullable': r[2] == 'YES', 'default': r[3]}
            for r in cursor.fetchall()
        ]

        cursor.execute("""
            SELECT
                i.relname,
                ARRAY_AGG(a.attname ORDER BY k.n) AS cols,
                ix.indisunique,
                pg_get_expr(ix.indpred, ix.indrelid)
            FROM pg_class t
            JOIN pg_index ix ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN LATERAL unnest(ix.indkey) WITH ORDINALITY AS k(attnum, n) ON TRUE
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
            WHERE t.relname = %s AND t.relkind = 'r' AND a.attnum > 0
            GROUP BY i.relname, ix.indisunique, ix.indpred, ix.indrelid
            ORDER BY i.relname
        """, [table_name])
        indexes = [
            {'name': r[0], 'columns': r[1], 'unique': r[2], 'partial_where': r[3]}
            for r in cursor.fetchall()
        ]

        cursor.execute("""
            SELECT kcu.column_name, ccu.table_name, ccu.column_name, rc.delete_rule
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
            JOIN information_schema.referential_constraints rc
                ON tc.constraint_name = rc.constraint_name
            JOIN information_schema.constraint_column_usage ccu
                ON rc.unique_constraint_name = ccu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name = %s
        """, [table_name])
        constraints = [
            {'type': 'FK', 'column': r[0], 'references': f'{r[1]}({r[2]})', 'on_delete': r[3]}
            for r in cursor.fetchall()
        ]

        cursor.execute("""
            SELECT trigger_name, event_manipulation, action_timing
            FROM information_schema.triggers
            WHERE event_object_table = %s
        """, [table_name])
        triggers = [
            {'name': r[0], 'event': r[1], 'timing': r[2]}
            for r in cursor.fetchall()
        ]

    return _ok({
        'table': table_name,
        'columns': columns,
        'indexes': indexes,
        'constraints': constraints,
        'triggers': triggers,
    })


async def _table_stats(args: dict) -> list[TextContent]:
    from django.db import connection

    table_name = args.get('table_name')

    with connection.cursor() as cursor:
        if table_name:
            cursor.execute("""
                SELECT relname,
                    n_live_tup,
                    pg_size_pretty(pg_total_relation_size(quote_ident(relname))),
                    pg_size_pretty(pg_indexes_size(quote_ident(relname))),
                    seq_scan, idx_scan, last_vacuum, last_analyze
                FROM pg_stat_user_tables WHERE relname = %s
            """, [table_name])
        else:
            cursor.execute("""
                SELECT relname,
                    n_live_tup,
                    pg_size_pretty(pg_total_relation_size(quote_ident(relname))),
                    pg_size_pretty(pg_indexes_size(quote_ident(relname))),
                    seq_scan, idx_scan, last_vacuum, last_analyze
                FROM pg_stat_user_tables
                ORDER BY pg_total_relation_size(quote_ident(relname)) DESC
                LIMIT 20
            """)
        rows = cursor.fetchall()

    return _ok([
        {
            'table': r[0], 'rows_estimate': r[1] or 0,
            'total_size': r[2] or '0 bytes', 'index_size': r[3] or '0 bytes',
            'seq_scans': r[4] or 0, 'idx_scans': r[5] or 0,
            'last_vacuum': r[6], 'last_analyze': r[7],
        }
        for r in rows
    ])


async def _explain_query(args: dict) -> list[TextContent]:
    from django.db import connection

    sql = args['sql']
    params = args.get('params', [])
    analyze = bool(args.get('analyze', False))

    with connection.cursor() as cursor:
        if analyze:
            cursor.execute("SET LOCAL statement_timeout = '30s'")
        cursor.execute(f"EXPLAIN {'ANALYZE ' if analyze else ''}(FORMAT JSON) {sql}", params)
        plan = cursor.fetchone()[0]

    plan_text = json.dumps(plan, default=str)
    warnings = []
    if 'Seq Scan' in plan_text:
        warnings.append('Seq Scan detectado — considere adicionar um index')

    return _ok({'plan': plan, 'warnings': warnings, 'analyze_used': analyze})


async def _table_indexes(args: dict) -> list[TextContent]:
    from django.db import connection

    table_name = args['table_name']

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT i.relname,
                ARRAY_AGG(a.attname ORDER BY k.n) AS cols,
                am.amname,
                ix.indisunique,
                COALESCE(s.idx_scan, 0)
            FROM pg_class t
            JOIN pg_index ix ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_am am ON i.relam = am.oid
            JOIN LATERAL unnest(ix.indkey) WITH ORDINALITY AS k(attnum, n) ON TRUE
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum AND a.attnum > 0
            LEFT JOIN pg_stat_user_indexes s ON s.indexrelname = i.relname
            WHERE t.relname = %s AND t.relkind = 'r'
            GROUP BY i.relname, am.amname, ix.indisunique, s.idx_scan
            ORDER BY i.relname
        """, [table_name])
        indexes = [
            {'name': r[0], 'columns': r[1], 'type': r[2], 'unique': r[3], 'usage_count': r[4]}
            for r in cursor.fetchall()
        ]

        cursor.execute("""
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name = %s
        """, [table_name])
        fk_cols = {r[0] for r in cursor.fetchall()}

    indexed_leading = {idx['columns'][0] for idx in indexes if idx['columns']}
    missing_fk_indexes = [f'{col} — FK sem index!' for col in fk_cols if col not in indexed_leading]

    return _ok({'table': table_name, 'indexes': indexes, 'missing_fk_indexes': missing_fk_indexes})


async def _compare_model_vs_table(args: dict) -> list[TextContent]:
    from django.apps import apps
    from django.db import connection

    model_name = args['model_name']
    model = next(
        (m for m in apps.get_models()
         if m.__name__ == model_name or f'{m._meta.app_label}.{m.__name__}' == model_name),
        None
    )
    if not model:
        return _err(f'Model não encontrado: {model_name}')

    model_cols = {f.column: f for f in model._meta.get_fields() if hasattr(f, 'column')}

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
        """, [model._meta.db_table])
        db_cols = {r[0]: r[1] for r in cursor.fetchall()}

    _pg_map = {
        'UUIDField': 'uuid', 'CharField': 'character varying', 'TextField': 'text',
        'IntegerField': 'integer', 'BigIntegerField': 'bigint', 'BooleanField': 'boolean',
        'DateTimeField': 'timestamp with time zone', 'DateField': 'date',
        'DecimalField': 'numeric', 'FloatField': 'double precision',
        'JSONField': 'jsonb', 'EmailField': 'character varying', 'URLField': 'character varying',
        'PositiveSmallIntegerField': 'smallint', 'PositiveIntegerField': 'integer',
        'AutoField': 'integer', 'BigAutoField': 'bigint',
    }

    mismatches = []
    for col, field in model_cols.items():
        if col in db_cols:
            expected = _pg_map.get(type(field).__name__, '')
            if expected and expected != db_cols[col]:
                mismatches.append({
                    'field': col,
                    'model_type': type(field).__name__,
                    'pg_type': db_cols[col],
                    'expected_pg_type': expected,
                })

    return _ok({
        'model': model_name,
        'db_table': model._meta.db_table,
        'in_model_not_in_table': [c for c in model_cols if c not in db_cols],
        'in_table_not_in_model': [c for c in db_cols if c not in model_cols],
        'type_mismatches': mismatches,
        'status': 'DIVERGE' if (set(model_cols) - set(db_cols) or set(db_cols) - set(model_cols)) else 'OK',
    })
```

- [ ] **Step 4: Run tests**

```bash
cd /home/graco/WORK/server2
python -m pytest tests/test_mcp_database.py -v
```

Expected: All 9 scaffold tests + all 8 Group 0 integration tests PASS.

- [ ] **Step 5: Commit**

```bash
git add mcp_database.py tests/test_mcp_database.py
git commit -m "mcp_database: grupo 0 — 6 ferramentas PostgreSQL tables"
```

---

## Task 3: Grupo 1 — Django schema tools (4 ferramentas)

**Files:**
- Modify: `mcp_database.py` — replace 4 stubs in Grupo 1

- [ ] **Step 1: Write failing integration tests**

Add to `tests/test_mcp_database.py`:

```python
class TestGroup1DjangoSchema(django.test.TestCase):
    def setUp(self):
        os.environ['MCP_DB_SAFE_MODE'] = 'true'
        import mcp_database
        importlib.reload(mcp_database)
        self.mod = mcp_database

    def test_schema_overview_returns_apps(self):
        result = run(self.mod.call_tool('schema_overview', {}))
        data = json.loads(result[0].text)
        self.assertIsInstance(data, dict)
        self.assertIn('stores', data)

    def test_schema_overview_filter(self):
        result = run(self.mod.call_tool('schema_overview', {'app_filter': 'stores'}))
        data = json.loads(result[0].text)
        self.assertIn('stores', data)
        self.assertNotIn('automation', data)

    def test_model_detail_known_model(self):
        result = run(self.mod.call_tool('model_detail', {'model_name': 'Store'}))
        data = json.loads(result[0].text)
        self.assertIn('fields', data)
        self.assertIn('reverse_relations', data)
        self.assertIn('row_count', data)

    def test_model_detail_unknown(self):
        result = run(self.mod.call_tool('model_detail', {'model_name': 'GhostModel99'}))
        data = json.loads(result[0].text)
        self.assertIn('error', data)

    def test_find_field_by_name(self):
        result = run(self.mod.call_tool('find_field', {'field_name': 'slug'}))
        data = json.loads(result[0].text)
        self.assertGreater(data['count'], 0)
        self.assertTrue(all(r['field'] == 'slug' for r in data['results']))

    def test_find_field_by_type(self):
        result = run(self.mod.call_tool('find_field', {'field_type': 'JSONField'}))
        data = json.loads(result[0].text)
        self.assertGreater(data['count'], 0)

    def test_find_field_requires_at_least_one(self):
        result = run(self.mod.call_tool('find_field', {}))
        data = json.loads(result[0].text)
        self.assertIn('error', data)

    def test_relationship_graph_stores(self):
        result = run(self.mod.call_tool('relationship_graph', {'model_name': 'Store'}))
        data = json.loads(result[0].text)
        self.assertIn('graph', data)
        self.assertIn('Store', data['graph'])
```

- [ ] **Step 2: Confirm failure**

```bash
python -m pytest tests/test_mcp_database.py::TestGroup1DjangoSchema -v
```

Expected: All fail (stubs return "Not implemented yet").

- [ ] **Step 3: Implement the 4 Group 1 functions**

Replace the Grupo 1 stubs in `mcp_database.py`:

```python
async def _schema_overview(args: dict) -> list[TextContent]:
    from django.apps import apps
    from django.db import connection

    app_filter = args.get('app_filter', '')
    result = {}

    for model in apps.get_models():
        app_label = model._meta.app_label
        if app_filter and app_filter != app_label:
            continue

        try:
            with connection.cursor() as cursor:
                cursor.execute(f'SELECT COUNT(*) FROM "{model._meta.db_table}"')
                row_count = cursor.fetchone()[0]
        except Exception:
            row_count = '?'

        fields_summary = [
            f'{f.name}: {type(f).__name__}'
            for f in model._meta.get_fields() if hasattr(f, 'column')
        ]
        fks = [
            f'{f.name} → {f.related_model.__name__}'
            for f in model._meta.get_fields()
            if hasattr(f, 'related_model') and f.related_model and hasattr(f, 'column')
        ]

        result.setdefault(app_label, []).append({
            'model': model.__name__,
            'db_table': model._meta.db_table,
            'fields_count': len(fields_summary),
            'fields': fields_summary,
            'foreign_keys': fks,
            'row_count': row_count,
        })

    return _ok(result)


async def _model_detail(args: dict) -> list[TextContent]:
    from django.apps import apps
    from django.db import connection

    model_name = args['model_name']
    model = next(
        (m for m in apps.get_models()
         if m.__name__ == model_name or f'{m._meta.app_label}.{m.__name__}' == model_name),
        None
    )
    if not model:
        return _err(f'Model não encontrado: {model_name}')

    fields = []
    for f in model._meta.get_fields():
        if not hasattr(f, 'column'):
            continue
        info = {
            'name': f.name, 'column': f.column, 'type': type(f).__name__,
            'null': getattr(f, 'null', False), 'blank': getattr(f, 'blank', False),
            'unique': getattr(f, 'unique', False),
        }
        if getattr(f, 'max_length', None):
            info['max_length'] = f.max_length
        if getattr(f, 'related_model', None):
            info['related_to'] = f.related_model.__name__
            rf = getattr(f, 'remote_field', None)
            info['on_delete'] = str(getattr(rf, 'on_delete', '')) if rf else ''
        fields.append(info)

    reverse_relations = [
        {'from_model': rel.related_model.__name__, 'field': rel.field.name, 'on_delete': str(rel.on_delete)}
        for rel in model._meta.related_objects
    ]

    try:
        with connection.cursor() as cursor:
            cursor.execute(f'SELECT COUNT(*) FROM "{model._meta.db_table}"')
            row_count = cursor.fetchone()[0]
    except Exception:
        row_count = '?'

    sample = []
    try:
        for obj in model.objects.all()[:3]:
            record = {
                f.name: getattr(obj, f.name, None)
                for f in model._meta.get_fields() if hasattr(f, 'column')
            }
            sample.append(_mask_sensitive(record))
    except Exception as exc:
        sample = [{'error': str(exc)}]

    return _ok({
        'model': model_name, 'app': model._meta.app_label,
        'db_table': model._meta.db_table, 'row_count': row_count,
        'fields': fields, 'reverse_relations': reverse_relations,
        'unique_together': [list(u) for u in model._meta.unique_together],
        'indexes': [str(i) for i in model._meta.indexes],
        'sample_records': sample,
    })


async def _find_field(args: dict) -> list[TextContent]:
    from django.apps import apps

    field_name = args.get('field_name', '')
    field_type = args.get('field_type', '')

    if not field_name and not field_type:
        return _err('Forneça field_name ou field_type (pelo menos um)')

    result = []
    for model in apps.get_models():
        for f in model._meta.get_fields():
            if not hasattr(f, 'column'):
                continue
            name_match = field_name and field_name.lower() in f.name.lower()
            type_match = field_type and type(f).__name__ == field_type
            if (field_name and not field_type and name_match) or \
               (field_type and not field_name and type_match) or \
               (field_name and field_type and (name_match or type_match)):
                result.append({
                    'app': model._meta.app_label, 'model': model.__name__,
                    'field': f.name, 'type': type(f).__name__, 'column': f.column,
                })

    return _ok({'count': len(result), 'results': result})


async def _relationship_graph(args: dict) -> list[TextContent]:
    from django.apps import apps

    model_name = args['model_name']
    depth = int(args.get('depth', 2))

    model = next(
        (m for m in apps.get_models()
         if m.__name__ == model_name or f'{m._meta.app_label}.{m.__name__}' == model_name),
        None
    )
    if not model:
        return _err(f'Model não encontrado: {model_name}')

    lines = [model_name]

    def _out(m, prefix, d):
        if d > depth:
            return
        for f in m._meta.get_fields():
            if hasattr(f, 'related_model') and f.related_model and hasattr(f, 'column'):
                rf = getattr(f, 'remote_field', None)
                on_del = str(getattr(rf, 'on_delete', '')) if rf else ''
                lines.append(f'{prefix}→ {f.related_model.__name__} (FK, {on_del})')
                if d < depth:
                    _out(f.related_model, prefix + '  ', d + 1)

    def _in(m, prefix):
        for rel in m._meta.related_objects:
            lines.append(f'{prefix}← {rel.related_model.__name__}.{rel.field.name} ({rel.on_delete})')

    _out(model, '├── ', 1)
    _in(model, '└── ')

    return _ok({'graph': '\n'.join(lines)})
```

- [ ] **Step 4: Run all tests**

```bash
cd /home/graco/WORK/server2
python -m pytest tests/test_mcp_database.py -v
```

Expected: All tests PASS (scaffold + Group 0 + Group 1).

- [ ] **Step 5: Commit**

```bash
git add mcp_database.py tests/test_mcp_database.py
git commit -m "mcp_database: grupo 1 — schema_overview, model_detail, find_field, relationship_graph"
```

---

## Task 4: Grupo 2 — Migration tools (4 ferramentas)

**Files:**
- Modify: `mcp_database.py` — replace 4 stubs in Grupo 2

- [ ] **Step 1: Write failing integration tests**

Add to `tests/test_mcp_database.py`:

```python
class TestGroup2Migrations(django.test.TestCase):
    def setUp(self):
        os.environ['MCP_DB_SAFE_MODE'] = 'true'
        import mcp_database
        importlib.reload(mcp_database)
        self.mod = mcp_database

    def test_migration_status_returns_list(self):
        result = run(self.mod.call_tool('migration_status', {}))
        data = json.loads(result[0].text)
        self.assertIn('migrations', data)
        self.assertGreater(data['total'], 0)

    def test_migration_status_filter_app(self):
        result = run(self.mod.call_tool('migration_status', {'app': 'stores'}))
        data = json.loads(result[0].text)
        self.assertTrue(all(m['app'] == 'stores' for m in data['migrations']))

    def test_show_migration_sql_returns_sql(self):
        result = run(self.mod.call_tool('show_migration_sql', {'app': 'stores', 'migration': '0001_initial'}))
        data = json.loads(result[0].text)
        self.assertIn('sql', data)

    def test_make_migrations_blocked_without_confirm_in_safe_mode(self):
        result = run(self.mod.call_tool('make_migrations', {}))
        data = json.loads(result[0].text)
        self.assertIn('error', data)

    def test_make_migrations_allowed_with_confirm_in_safe_mode(self):
        result = run(self.mod.call_tool('make_migrations', {'confirm': True}))
        data = json.loads(result[0].text)
        # Should succeed (no changes expected in clean state)
        self.assertNotIn('Not implemented', data.get('error', ''))
```

- [ ] **Step 2: Confirm failure**

```bash
python -m pytest tests/test_mcp_database.py::TestGroup2Migrations -v
```

Expected: `migration_status`, `show_migration_sql` fail; SAFE_MODE tests already pass.

- [ ] **Step 3: Implement the 4 Group 2 functions**

Replace Grupo 2 stubs in `mcp_database.py`:

```python
async def _migration_status(args: dict) -> list[TextContent]:
    from django.db.migrations.executor import MigrationExecutor
    from django.db import connection

    app_filter = args.get('app', '')
    executor = MigrationExecutor(connection)
    applied = set(executor.loader.applied_migrations)

    result = []
    for (app, name) in sorted(executor.loader.disk_migrations.keys()):
        if app_filter and app_filter != app:
            continue
        result.append({'app': app, 'name': name, 'applied': (app, name) in applied})

    pending = [m for m in result if not m['applied']]
    return _ok({
        'total': len(result),
        'applied': len(result) - len(pending),
        'pending': len(pending),
        'pending_list': pending,
        'migrations': result,
    })


async def _make_migrations(args: dict) -> list[TextContent]:
    if SAFE_MODE and not args.get('confirm'):
        return _err('SAFE_MODE ativo — forneça confirm=true para criar migrations')

    from django.core.management import call_command
    from io import StringIO

    out = StringIO()
    kwargs = {'stdout': out, 'verbosity': 1}
    if args.get('app'):
        kwargs['app_label'] = args['app']
    if args.get('name'):
        kwargs['name'] = args['name']

    call_command('makemigrations', **kwargs)
    output = out.getvalue()
    return _ok({'output': output, 'created': 'No changes detected' not in output})


async def _run_migrations(args: dict) -> list[TextContent]:
    if SAFE_MODE and not args.get('confirm'):
        return _err('SAFE_MODE ativo — forneça confirm=true para aplicar migrations')

    from django.core.management import call_command
    from io import StringIO

    out = StringIO()
    call_args = []
    if args.get('app'):
        call_args.append(args['app'])
    if args.get('migration'):
        call_args.append(args['migration'])

    call_command('migrate', *call_args, stdout=out, verbosity=1)
    return _ok({'output': out.getvalue()})


async def _show_migration_sql(args: dict) -> list[TextContent]:
    from django.core.management import call_command
    from io import StringIO

    out = StringIO()
    call_command('sqlmigrate', args['app'], args['migration'], stdout=out)
    return _ok({'sql': out.getvalue(), 'app': args['app'], 'migration': args['migration']})
```

- [ ] **Step 4: Run all tests**

```bash
cd /home/graco/WORK/server2
python -m pytest tests/test_mcp_database.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add mcp_database.py tests/test_mcp_database.py
git commit -m "mcp_database: grupo 2 — migration_status, make/run_migrations, show_migration_sql"
```

---

## Task 5: Grupo 3 — Query tools + SAFE_MODE enforcement (3 ferramentas)

**Files:**
- Modify: `mcp_database.py` — replace 3 stubs in Grupo 3

- [ ] **Step 1: Write failing integration tests**

Add to `tests/test_mcp_database.py`:

```python
class TestGroup3Queries(django.test.TestCase):
    def setUp(self):
        os.environ['MCP_DB_SAFE_MODE'] = 'true'
        import mcp_database
        importlib.reload(mcp_database)
        self.mod = mcp_database

    def test_count_records_stores(self):
        result = run(self.mod.call_tool('count_records', {'model_name': 'Store'}))
        data = json.loads(result[0].text)
        self.assertIn('count', data)
        self.assertIsInstance(data['count'], int)

    def test_count_records_unknown_model(self):
        result = run(self.mod.call_tool('count_records', {'model_name': 'GhostXYZ'}))
        data = json.loads(result[0].text)
        self.assertIn('error', data)

    def test_sample_records_returns_list(self):
        result = run(self.mod.call_tool('sample_records', {'model_name': 'Store', 'limit': 2}))
        data = json.loads(result[0].text)
        self.assertIn('records', data)
        self.assertLessEqual(len(data['records']), 2)

    def test_sample_records_masks_sensitive_fields(self):
        # Agent model has api_key field
        from apps.agents.models import Agent
        if Agent.objects.exists():
            result = run(self.mod.call_tool('sample_records', {'model_name': 'Agent', 'limit': 1}))
            data = json.loads(result[0].text)
            for record in data['records']:
                if 'api_key' in record:
                    self.assertEqual(record['api_key'], '***REDACTED***')

    def test_run_sql_select(self):
        result = run(self.mod.call_tool('run_sql', {'sql': 'SELECT 1 AS n'}))
        data = json.loads(result[0].text)
        self.assertIn('rows', data)
        self.assertEqual(data['rows'][0]['n'], 1)

    def test_run_sql_write_requires_confirm(self):
        result = run(self.mod.call_tool('run_sql', {
            'sql': "UPDATE stores_store SET name='x' WHERE 1=0"
        }))
        data = json.loads(result[0].text)
        self.assertIn('error', data)
        self.assertIn('confirm', data['error'])

    def test_run_sql_drop_always_blocked(self):
        result = run(self.mod.call_tool('run_sql', {
            'sql': 'DROP TABLE stores_store', 'confirm': True
        }))
        data = json.loads(result[0].text)
        self.assertIn('error', data)
        self.assertIn('bloqueado', data['error'])

    def test_run_sql_truncate_always_blocked(self):
        result = run(self.mod.call_tool('run_sql', {
            'sql': 'TRUNCATE stores_store', 'confirm': True
        }))
        data = json.loads(result[0].text)
        self.assertIn('error', data)
```

- [ ] **Step 2: Confirm failure**

```bash
python -m pytest tests/test_mcp_database.py::TestGroup3Queries -v
```

Expected: `count_records`, `sample_records` fail; `run_sql` guard tests already pass.

- [ ] **Step 3: Implement the 3 Group 3 functions**

Replace Grupo 3 stubs in `mcp_database.py`:

```python
async def _count_records(args: dict) -> list[TextContent]:
    from django.apps import apps

    model_name = args['model_name']
    model = next(
        (m for m in apps.get_models()
         if m.__name__ == model_name or f'{m._meta.app_label}.{m.__name__}' == model_name),
        None
    )
    if not model:
        return _err(f'Model não encontrado: {model_name}')

    qs = model.objects.all()
    filter_args = args.get('filter', {})
    if filter_args:
        qs = qs.filter(**filter_args)

    return _ok({'model': model_name, 'count': qs.count(), 'filter_applied': filter_args})


async def _sample_records(args: dict) -> list[TextContent]:
    from django.apps import apps

    model_name = args['model_name']
    limit = int(args.get('limit', 5))
    filter_args = args.get('filter', {})
    order_by = args.get('order_by', '-pk')

    model = next(
        (m for m in apps.get_models()
         if m.__name__ == model_name or f'{m._meta.app_label}.{m.__name__}' == model_name),
        None
    )
    if not model:
        return _err(f'Model não encontrado: {model_name}')

    qs = model.objects.all()
    if filter_args:
        qs = qs.filter(**filter_args)
    try:
        qs = qs.order_by(order_by)
    except Exception:
        pass

    records = []
    for obj in qs[:limit]:
        record = {
            f.name: getattr(obj, f.name, None)
            for f in model._meta.get_fields() if hasattr(f, 'column')
        }
        records.append(_mask_sensitive(record))

    return _ok({'model': model_name, 'count': len(records), 'records': records})


async def _run_sql(args: dict) -> list[TextContent]:
    from django.db import connection

    sql = args['sql']
    params = args.get('params', [])
    confirm = bool(args.get('confirm', False))
    sql_upper = sql.strip().upper()
    is_write = any(sql_upper.startswith(kw) for kw in ('INSERT', 'UPDATE', 'DELETE'))

    for blocked in _BLOCKED_STATEMENTS:
        if blocked in sql_upper:
            return _err(f'SQL bloqueado: {blocked} não é permitido. Use migrations para mudanças de schema.')

    if SAFE_MODE and is_write and not confirm:
        return _err(
            f'SAFE_MODE ativo — escrita requer confirm=true. '
            f'SQL detectado como write (começa com {sql_upper.split()[0] if sql_upper else "?"}).'
        )

    with connection.cursor() as cursor:
        if is_write:
            cursor.execute("SET LOCAL statement_timeout = '30s'")
        cursor.execute(sql, params)

        if sql_upper.startswith('SELECT') or sql_upper.startswith('WITH'):
            cols = [d[0] for d in cursor.description]
            rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
            return _ok({'rows': rows, 'count': len(rows)})
        else:
            return _ok({'rows_affected': cursor.rowcount})
```

- [ ] **Step 4: Run all tests**

```bash
cd /home/graco/WORK/server2
python -m pytest tests/test_mcp_database.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add mcp_database.py tests/test_mcp_database.py
git commit -m "mcp_database: grupo 3 — count_records, sample_records, run_sql com SAFE_MODE"
```

---

## Task 6: Grupo 4 — Integrity tools (4 ferramentas)

**Files:**
- Modify: `mcp_database.py` — replace 4 stubs in Grupo 4

- [ ] **Step 1: Write failing integration tests**

Add to `tests/test_mcp_database.py`:

```python
class TestGroup4Integrity(django.test.TestCase):
    def setUp(self):
        os.environ['MCP_DB_SAFE_MODE'] = 'true'
        import mcp_database
        importlib.reload(mcp_database)
        self.mod = mcp_database

    def test_integrity_report_returns_structure(self):
        result = run(self.mod.call_tool('integrity_report', {}))
        data = json.loads(result[0].text)
        self.assertIn('broken_fks', data)
        self.assertIn('unexpected_nulls', data)
        self.assertIn('summary', data)

    def test_integrity_report_filter_app(self):
        result = run(self.mod.call_tool('integrity_report', {'app': 'stores'}))
        data = json.loads(result[0].text)
        self.assertIn('summary', data)

    def test_find_orphans_no_store_fk(self):
        # In a clean test DB there should be no orphans
        result = run(self.mod.call_tool('find_orphans', {
            'model_name': 'StoreProduct', 'field_name': 'store'
        }))
        data = json.loads(result[0].text)
        self.assertIn('broken_count', data)
        self.assertEqual(data['broken_count'], 0)

    def test_find_orphans_unknown_model(self):
        result = run(self.mod.call_tool('find_orphans', {
            'model_name': 'Ghost', 'field_name': 'foo'
        }))
        data = json.loads(result[0].text)
        self.assertIn('error', data)

    def test_find_duplicates_returns_structure(self):
        result = run(self.mod.call_tool('find_duplicates', {
            'model_name': 'Store', 'fields': ['slug']
        }))
        data = json.loads(result[0].text)
        self.assertIn('duplicates', data)

    def test_check_nulls_returns_findings(self):
        result = run(self.mod.call_tool('check_nulls', {}))
        data = json.loads(result[0].text)
        self.assertIn('findings', data)
        self.assertIn('total_findings', data)
```

- [ ] **Step 2: Confirm failure**

```bash
python -m pytest tests/test_mcp_database.py::TestGroup4Integrity -v
```

Expected: All fail (stubs).

- [ ] **Step 3: Implement the 4 Group 4 functions**

Replace Grupo 4 stubs in `mcp_database.py`:

```python
async def _integrity_report(args: dict) -> list[TextContent]:
    from django.apps import apps
    from django.db import connection

    app_filter = args.get('app', '')
    broken_fks = []
    unexpected_nulls = []

    for model in apps.get_models():
        if app_filter and model._meta.app_label != app_filter:
            continue

        for f in model._meta.get_fields():
            if not (hasattr(f, 'related_model') and f.related_model and hasattr(f, 'column')):
                continue
            if not getattr(f, 'null', False):
                continue
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM "{model._meta.db_table}" t
                        WHERE t."{f.column}" IS NOT NULL
                        AND NOT EXISTS (
                            SELECT 1 FROM "{f.related_model._meta.db_table}" r
                            WHERE r.id = t."{f.column}"
                        )
                    """)
                    broken = cursor.fetchone()[0]
                if broken > 0:
                    broken_fks.append({'model': model.__name__, 'field': f.name, 'broken_count': broken})
            except Exception:
                pass

        for f in model._meta.get_fields():
            if not hasattr(f, 'column'):
                continue
            if getattr(f, 'null', True) and getattr(f, 'blank', True):
                continue
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f'SELECT COUNT(*) FROM "{model._meta.db_table}" WHERE "{f.column}" IS NULL'
                    )
                    null_count = cursor.fetchone()[0]
                if null_count > 0:
                    unexpected_nulls.append({'model': model.__name__, 'field': f.name, 'null_count': null_count})
            except Exception:
                pass

    return _ok({
        'broken_fks': broken_fks,
        'unexpected_nulls': unexpected_nulls,
        'summary': {
            'total_issues': len(broken_fks) + len(unexpected_nulls),
            'critical': len(broken_fks),
            'warnings': len(unexpected_nulls),
        },
    })


async def _find_orphans(args: dict) -> list[TextContent]:
    from django.apps import apps
    from django.db import connection

    model_name = args['model_name']
    field_name = args['field_name']

    model = next(
        (m for m in apps.get_models()
         if m.__name__ == model_name or f'{m._meta.app_label}.{m.__name__}' == model_name),
        None
    )
    if not model:
        return _err(f'Model não encontrado: {model_name}')

    field = next(
        (f for f in model._meta.get_fields()
         if f.name == field_name and hasattr(f, 'related_model') and f.related_model),
        None
    )
    if not field:
        return _err(f'Campo FK não encontrado: {field_name} em {model_name}')

    related_table = field.related_model._meta.db_table
    pk_col = field.related_model._meta.pk.column

    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT COUNT(*), ARRAY_AGG(t.id::text)
            FROM "{model._meta.db_table}" t
            LEFT JOIN "{related_table}" r ON r.{pk_col} = t."{field.column}"
            WHERE t."{field.column}" IS NOT NULL AND r.{pk_col} IS NULL
        """)
        row = cursor.fetchone()
        broken_count = row[0] or 0
        sample_ids = (row[1] or [])[:10]

    return _ok({
        'model': model_name, 'field': field_name,
        'references': related_table, 'broken_count': broken_count, 'sample_ids': sample_ids,
    })


async def _find_duplicates(args: dict) -> list[TextContent]:
    from django.apps import apps
    from django.db import connection

    model_name = args['model_name']
    fields = args['fields']

    model = next(
        (m for m in apps.get_models()
         if m.__name__ == model_name or f'{m._meta.app_label}.{m.__name__}' == model_name),
        None
    )
    if not model:
        return _err(f'Model não encontrado: {model_name}')

    field_map = {f.name: f.column for f in model._meta.get_fields() if hasattr(f, 'column')}
    col_names = [field_map.get(fname, fname) for fname in fields]
    cols_sql = ', '.join(f'"{c}"' for c in col_names)

    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT {cols_sql}, COUNT(*) AS cnt, ARRAY_AGG(id::text) AS ids
            FROM "{model._meta.db_table}"
            GROUP BY {cols_sql}
            HAVING COUNT(*) > 1
            ORDER BY cnt DESC
            LIMIT 50
        """)
        rows = cursor.fetchall()

    result = [
        {'values': dict(zip(fields, row[:len(fields)])), 'count': row[len(fields)], 'ids': row[len(fields)+1] or []}
        for row in rows
    ]
    return _ok({'model': model_name, 'fields': fields, 'duplicates': result, 'total_groups': len(result)})


async def _check_nulls(args: dict) -> list[TextContent]:
    from django.apps import apps
    from django.db import connection

    model_name = args.get('model_name')
    models_to_check = []

    if model_name:
        m = next(
            (m for m in apps.get_models()
             if m.__name__ == model_name or f'{m._meta.app_label}.{m.__name__}' == model_name),
            None
        )
        if not m:
            return _err(f'Model não encontrado: {model_name}')
        models_to_check = [m]
    else:
        models_to_check = list(apps.get_models())

    findings = []
    for model in models_to_check:
        for f in model._meta.get_fields():
            if not hasattr(f, 'column'):
                continue
            if not (getattr(f, 'null', False) or getattr(f, 'blank', False)):
                continue
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f'SELECT COUNT(*) FROM "{model._meta.db_table}" WHERE "{f.column}" IS NULL'
                    )
                    null_count = cursor.fetchone()[0]
                if null_count > 0:
                    findings.append({
                        'model': model.__name__, 'field': f.name,
                        'blank_count': null_count, 'field_type': type(f).__name__,
                        'severity': 'info' if getattr(f, 'null', False) else 'warning',
                    })
            except Exception:
                pass

    return _ok({'total_findings': len(findings), 'findings': findings})
```

- [ ] **Step 4: Run all tests**

```bash
cd /home/graco/WORK/server2
python -m pytest tests/test_mcp_database.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add mcp_database.py tests/test_mcp_database.py
git commit -m "mcp_database: grupo 4 — integrity_report, find_orphans, find_duplicates, check_nulls"
```

---

## Task 7: Grupo 5 — Business tools (5 ferramentas)

**Files:**
- Modify: `mcp_database.py` — replace 5 stubs in Grupo 5

- [ ] **Step 1: Write failing integration tests**

Add to `tests/test_mcp_database.py`:

```python
class TestGroup5Business(django.test.TestCase):
    def setUp(self):
        os.environ['MCP_DB_SAFE_MODE'] = 'true'
        import mcp_database
        importlib.reload(mcp_database)
        self.mod = mcp_database

    def test_find_ghost_users_structure(self):
        result = run(self.mod.call_tool('find_ghost_users', {}))
        data = json.loads(result[0].text)
        self.assertIn('total_ghost_users', data)
        self.assertIn('sample', data)
        self.assertIn('recommendation', data)

    def test_customer_identity_audit_structure(self):
        result = run(self.mod.call_tool('customer_identity_audit', {}))
        data = json.loads(result[0].text)
        self.assertIn('total_auth_users', data)
        self.assertIn('ghost_users_total', data)
        self.assertIn('recommendation', data)

    def test_stats_drift_check_structure(self):
        result = run(self.mod.call_tool('stats_drift_check', {}))
        data = json.loads(result[0].text)
        self.assertIn('drift_count', data)
        self.assertIn('customers_with_drift', data)

    def test_security_audit_structure(self):
        result = run(self.mod.call_tool('security_audit', {}))
        data = json.loads(result[0].text)
        self.assertIn('plaintext_secrets', data)
        self.assertIn('critical_count', data)

    def test_pgvector_readiness_structure(self):
        result = run(self.mod.call_tool('pgvector_readiness', {}))
        data = json.loads(result[0].text)
        self.assertIn('extension_installed', data)
        self.assertIn('pg_version', data)
        self.assertIn('ready', data)
        self.assertIsInstance(data['extension_installed'], bool)
```

- [ ] **Step 2: Confirm failure**

```bash
python -m pytest tests/test_mcp_database.py::TestGroup5Business -v
```

Expected: All fail (stubs).

- [ ] **Step 3: Implement the 5 Group 5 functions**

Replace Grupo 5 stubs in `mcp_database.py`:

```python
async def _find_ghost_users(args: dict) -> list[TextContent]:
    from django.contrib.auth import get_user_model
    User = get_user_model()

    limit = int(args.get('limit', 20))

    ghost_qs = User.objects.filter(email__contains='@pastita.local') | \
               User.objects.filter(username__startswith='cliente_')
    total = ghost_qs.count()

    sample = []
    for user in ghost_qs.order_by('-date_joined')[:limit]:
        sc_count = 0
        try:
            from apps.stores.models import StoreCustomer
            sc_count = StoreCustomer.objects.filter(user=user).count()
        except Exception:
            pass
        sample.append({
            'id': user.id, 'email': user.email, 'username': user.username,
            'date_joined': user.date_joined, 'store_customers': sc_count,
        })

    return _ok({
        'total_ghost_users': total,
        'sample': sample,
        'recommendation': (
            'Estes usuários podem ser migrados para UnifiedUser e removidos do auth.User '
            'como parte do sub-projeto A (customer identity consolidation)'
        ),
    })


async def _customer_identity_audit(args: dict) -> list[TextContent]:
    from django.contrib.auth import get_user_model
    from django.db import connection
    User = get_user_model()

    result = {}
    result['total_auth_users'] = User.objects.count()

    ghost_count = User.objects.filter(email__contains='@pastita.local').count()
    ghost_count += User.objects.filter(username__startswith='cliente_').exclude(
        email__contains='@pastita.local'
    ).count()
    result['ghost_users_total'] = ghost_count

    try:
        from apps.stores.models import StoreCustomer
        sc_total = StoreCustomer.objects.count()
        sc_no_unified = StoreCustomer.objects.filter(unified_user__isnull=True).count()
        result['store_customers_total'] = sc_total
        result['store_customers_without_unified_user'] = sc_no_unified
    except Exception as exc:
        result['store_customers_error'] = str(exc)
        sc_total = 1
        sc_no_unified = 1

    try:
        from apps.users.models import UnifiedUser
        result['unified_users_total'] = UnifiedUser.objects.count()
        result['unified_users_without_django_user'] = UnifiedUser.objects.filter(user__isnull=True).count()
    except Exception as exc:
        result['unified_users_error'] = str(exc)

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM (
                    SELECT store_id, phone, COUNT(*) cnt
                    FROM stores_storecustomer
                    WHERE phone IS NOT NULL AND phone != ''
                    GROUP BY store_id, phone HAVING COUNT(*) > 1
                ) t
            """)
            result['customers_with_duplicate_phone_same_store'] = cursor.fetchone()[0]
    except Exception as exc:
        result['duplicate_phone_error'] = str(exc)

    sc_total_safe = result.get('store_customers_total', 1) or 1
    sc_migrated = sc_total_safe - result.get('store_customers_without_unified_user', sc_total_safe)
    result['migration_completion'] = f'{int(sc_migrated / sc_total_safe * 100)}%'
    result['recommendation'] = (
        'Sub-projeto A: (1) UnifiedUser canônico, (2) remover UserProfile redundante, '
        '(3) migrar StoreCustomer.user → unified_user, (4) deletar ghost auth.Users'
    )

    return _ok(result)


async def _stats_drift_check(args: dict) -> list[TextContent]:
    from django.db import connection

    store_slug = args.get('store_slug')
    limit = int(args.get('limit', 20))

    extra_join = ""
    params: list = []
    where_extra = ""

    if store_slug:
        extra_join = 'JOIN stores_store s ON sc.store_id = s.id'
        where_extra = 'AND s.slug = %s'
        params.append(store_slug)

    params.append(limit)

    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT
                sc.id::text,
                sc.total_orders AS cached_orders,
                sc.total_spent AS cached_spent,
                COUNT(so.id) AS real_orders,
                COALESCE(SUM(so.total), 0) AS real_spent,
                sc.phone, sc.email
            FROM stores_storecustomer sc
            {extra_join}
            LEFT JOIN stores_storeorder so ON so.customer_id = sc.id
                AND so.status NOT IN ('cancelled', 'rejected')
            WHERE TRUE {where_extra}
            GROUP BY sc.id, sc.total_orders, sc.total_spent, sc.phone, sc.email
            HAVING COUNT(so.id) != COALESCE(sc.total_orders, 0)
                OR COALESCE(SUM(so.total), 0) != COALESCE(sc.total_spent, 0)
            ORDER BY ABS(COUNT(so.id) - COALESCE(sc.total_orders, 0)) DESC
            LIMIT %s
        """, params)
        rows = cursor.fetchall()

    result = [
        {
            'customer_id': r[0], 'cached_total_orders': r[1], 'cached_total_spent': str(r[2]),
            'real_total_orders': r[3], 'real_total_spent': str(r[4]),
            'phone': r[5], 'email': r[6], 'drift_detected': True,
        }
        for r in rows
    ]

    return _ok({
        'drift_count': len(result),
        'customers_with_drift': result,
        'note': 'Apenas clientes com divergência são mostrados',
    })


async def _security_audit(args: dict) -> list[TextContent]:
    from django.apps import apps
    from django.db import connection

    sensitive_keywords = ('token', 'key', 'secret', 'password', 'api_key', 'access_token')
    findings = []

    for model in apps.get_models():
        for f in model._meta.get_fields():
            if not hasattr(f, 'column'):
                continue
            fname_lower = f.name.lower()
            if not any(kw in fname_lower for kw in sensitive_keywords):
                continue
            if 'encrypted' in type(f).__name__.lower():
                continue
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM "{model._meta.db_table}"
                        WHERE "{f.column}" IS NOT NULL AND CAST("{f.column}" AS TEXT) != ''
                    """)
                    records_with_data = cursor.fetchone()[0]

                findings.append({
                    'model': model.__name__, 'app': model._meta.app_label,
                    'field': f.name, 'field_type': type(f).__name__,
                    'records_with_data': records_with_data,
                    'severity': 'CRITICAL' if records_with_data > 0 else 'INFO',
                })
            except Exception:
                pass

    critical = [f for f in findings if f['severity'] == 'CRITICAL']
    return _ok({
        'plaintext_secrets': findings,
        'critical_count': len(critical),
        'recommendation': (
            'Migrar campos CRITICAL para EncryptedCharField — ver apps/core/fields.py'
            if critical else 'Nenhum campo crítico encontrado'
        ),
    })


async def _pgvector_readiness(args: dict) -> list[TextContent]:
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT version()")
        pg_version_str = cursor.fetchone()[0]
        pg_version = pg_version_str.split()[1] if pg_version_str else '?'

        cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        extension_installed = cursor.fetchone() is not None

        existing_vector_columns = []
        if extension_installed:
            cursor.execute("""
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE udt_name = 'vector'
            """)
            existing_vector_columns = [{'table': r[0], 'column': r[1]} for r in cursor.fetchall()]

    try:
        import pgvector
        django_package = f'pgvector instalado: {pgvector.__version__}'
    except ImportError:
        django_package = 'pgvector não instalado — pip install pgvector'

    return _ok({
        'extension_installed': extension_installed,
        'pg_version': pg_version,
        'install_command': 'CREATE EXTENSION IF NOT EXISTS vector;',
        'existing_vector_columns': existing_vector_columns,
        'django_package': django_package,
        'ready': extension_installed and 'não instalado' not in django_package,
    })
```

- [ ] **Step 4: Run all tests**

```bash
cd /home/graco/WORK/server2
python -m pytest tests/test_mcp_database.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add mcp_database.py tests/test_mcp_database.py
git commit -m "mcp_database: grupo 5 — ferramentas de negócio Cardapidex (5 ferramentas)"
```

---

## Task 8: Registrar no Claude Code + smoke test

**Files:**
- No code changes — registration and manual verification

- [ ] **Step 1: Verify the server starts cleanly**

```bash
cd /home/graco/WORK/server2
timeout 3 python mcp_database.py || true
```

Expected: No crash during Django startup. Process exits after 3s (waiting on stdin — that's correct MCP stdio behavior).

- [ ] **Step 2: Register as dev (without SAFE_MODE)**

```bash
claude mcp add database -- python /home/graco/WORK/server2/mcp_database.py
```

Expected: `Added MCP server "database"` (or similar confirmation).

- [ ] **Step 3: Verify listing**

```bash
claude mcp list
```

Expected: `database` appears in the list alongside `whatsapp-bot`.

- [ ] **Step 4: Run full test suite one last time**

```bash
cd /home/graco/WORK/server2
python -m pytest tests/test_mcp_database.py -v --tb=short
```

Expected: All tests PASS, 0 failures.

- [ ] **Step 5: Commit registration note**

```bash
git commit --allow-empty -m "mcp_database: registrado como 'database' no Claude Code"
```

---

## Smoke Test Prompts (pós-implementação)

Depois de registrar, verificar no Claude Code:

```
use the database MCP to run schema_overview for the stores app
use the database MCP to run customer_identity_audit
use the database MCP to find all JSONFields in the project
use the database MCP to check pgvector_readiness
use the database MCP to run table_stats and show me the top 5 largest tables
use the database MCP to find all models with a field named phone
```
