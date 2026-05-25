#!/usr/bin/env python
"""
MCP Server — Database Inspector (Cardapidex/Pastita)
=====================================================

Fornece ao Claude Code (e a qualquer cliente MCP) acesso seguro ao banco de
dados PostgreSQL do projeto: inspeção de schema, modelos Django, migrations,
queries, integridade referencial e auditoria de segurança.

Ferramentas disponíveis (26 no total):

  Group 0 — PostgreSQL Tables:
    list_tables              — lista tabelas do banco
    table_schema             — schema (colunas + tipos) de uma tabela
    table_stats              — estatísticas de tamanho e linhas
    explain_query            — EXPLAIN [ANALYZE] de um SQL
    table_indexes            — índices de uma tabela
    compare_model_vs_table   — diferença entre model Django e tabela real

  Group 1 — Schema Django:
    schema_overview          — todos os models instalados
    model_detail             — detalhes de um model
    find_field               — busca field por nome ou tipo
    relationship_graph       — grafo de relacionamentos a N níveis

  Group 2 — Migrations:
    migration_status         — estado das migrations por app
    make_migrations          — cria migrations (requer confirm em SAFE_MODE)
    run_migrations           — aplica migrations (requer confirm em SAFE_MODE)
    show_migration_sql       — SQL gerado por uma migration

  Group 3 — Queries:
    count_records            — contagem com filtro ORM
    sample_records           — amostragem de registros
    run_sql                  — executa SQL arbitrário (guards em SAFE_MODE)

  Group 4 — Integrity:
    integrity_report         — relatório de integridade por app
    find_orphans             — registros órfãos via FK
    find_duplicates          — duplicatas em campos escolhidos
    check_nulls              — campos NULL inesperados

  Group 5 — Negócio:
    find_ghost_users         — usuários sem pedidos/perfil relevante
    customer_identity_audit  — auditoria de identidade de clientes
    stats_drift_check        — deriva de métricas de loja
    security_audit           — auditoria de segurança geral
    pgvector_readiness       — verifica suporte a pgvector

Variáveis de ambiente:
  MCP_DB_SAFE_MODE   (padrão: true) — bloqueia writes sem confirm=true
  DJANGO_SETTINGS_MODULE             (padrão: config.settings.production)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from typing import Any

# ─── Bootstrap Django antes de importar qualquer model ───────────────────────
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

import django
django.setup()

# ─── Agora podemos importar o SDK MCP ────────────────────────────────────────
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server('cardapidex-database')

# ══════════════════════════════════════════════════════════════════════════════
#  SAFE_MODE — proteção contra operações destrutivas acidentais
# ══════════════════════════════════════════════════════════════════════════════

SAFE_MODE = os.environ.get('MCP_DB_SAFE_MODE', 'true').lower() == 'true'

_SENSITIVE_KEYWORDS = (
    'token', 'key', 'secret', 'password', 'api_key',
    'access_token', 'refresh_token', 'encrypted',
)

_BLOCKED_STATEMENTS = ('DROP', 'TRUNCATE', 'ALTER TABLE')

# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _j(data: Any) -> str:
    """Serializa para JSON indentado."""
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def _ok(data: Any) -> list[TextContent]:
    return [TextContent(type='text', text=_j(data))]


def _err(msg: str) -> list[TextContent]:
    return [TextContent(type='text', text=json.dumps({'error': msg}, ensure_ascii=False))]


def _mask_sensitive(record: dict) -> dict:
    """Retorna cópia do dict com valores de chaves sensíveis redacted (apenas em SAFE_MODE)."""
    if not SAFE_MODE:
        return record
    result = {}
    for k, v in record.items():
        key_lower = k.lower()
        if any(kw in key_lower for kw in _SENSITIVE_KEYWORDS):
            result[k] = '***REDACTED***'
        else:
            result[k] = v
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  DEFINIÇÃO DAS FERRAMENTAS (26 tools)
# ══════════════════════════════════════════════════════════════════════════════

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        # ── Group 0: PostgreSQL Tables ─────────────────────────────────────
        Tool(
            name='list_tables',
            description='Lista todas as tabelas do banco PostgreSQL com schema, tamanho e contagem de linhas.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'schema': {'type': 'string', 'description': 'Schema PostgreSQL (padrão: public)'},
                    'filter': {'type': 'string', 'description': 'Filtrar nomes de tabela por substring (opcional)'},
                },
                'required': [],
            },
        ),
        Tool(
            name='table_schema',
            description='Retorna o schema completo de uma tabela: colunas, tipos, nullable, default, constraints.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'table_name': {'type': 'string', 'description': 'Nome da tabela (ex: stores_store)'},
                },
                'required': ['table_name'],
            },
        ),
        Tool(
            name='table_stats',
            description='Estatísticas de uma ou todas as tabelas: tamanho em disco, n_live_tup, n_dead_tup, last_vacuum.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'table_name': {'type': 'string', 'description': 'Nome da tabela (opcional — todas se omitido)'},
                },
                'required': [],
            },
        ),
        Tool(
            name='explain_query',
            description='Executa EXPLAIN [ANALYZE] em um SQL e retorna o plano de execução.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'sql': {'type': 'string', 'description': 'SQL a ser analisado'},
                    'params': {'type': 'array', 'description': 'Parâmetros posicionais (opcional)', 'items': {}},
                    'analyze': {
                        'type': 'boolean',
                        'default': False,
                        'description': 'Se true, executa EXPLAIN ANALYZE (roda a query de verdade)',
                    },
                },
                'required': ['sql'],
            },
        ),
        Tool(
            name='table_indexes',
            description='Lista todos os índices de uma tabela: nome, colunas, tipo, tamanho.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'table_name': {'type': 'string', 'description': 'Nome da tabela'},
                },
                'required': ['table_name'],
            },
        ),
        Tool(
            name='compare_model_vs_table',
            description='Compara a definição do model Django com a tabela real no banco. Detecta campos adicionados sem migration.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'model_name': {
                        'type': 'string',
                        'description': 'Nome do model (ex: Store, CompanyProfile, AutoMessage)',
                    },
                },
                'required': ['model_name'],
            },
        ),

        # ── Group 1: Schema Django ─────────────────────────────────────────
        Tool(
            name='schema_overview',
            description='Lista todos os models Django instalados com app, tabela e contagem de campos.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'app_filter': {'type': 'string', 'description': 'Filtrar por app label (ex: stores, automation)'},
                },
                'required': [],
            },
        ),
        Tool(
            name='model_detail',
            description='Detalhes completos de um model Django: todos os fields, tipos, relações, Meta, indexes.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'model_name': {'type': 'string', 'description': 'Nome do model (ex: Store)'},
                },
                'required': ['model_name'],
            },
        ),
        Tool(
            name='find_field',
            description='Busca fields por nome ou tipo em todos os models instalados.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'field_name': {'type': 'string', 'description': 'Substring do nome do field (opcional)'},
                    'field_type': {'type': 'string', 'description': 'Tipo do field (ex: ForeignKey, JSONField) (opcional)'},
                },
                'required': [],
            },
        ),
        Tool(
            name='relationship_graph',
            description='Retorna o grafo de relacionamentos de um model até N níveis de profundidade.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'model_name': {'type': 'string', 'description': 'Model raiz do grafo'},
                    'depth': {'type': 'integer', 'default': 2, 'description': 'Profundidade máxima (padrão: 2)'},
                },
                'required': ['model_name'],
            },
        ),

        # ── Group 2: Migrations ────────────────────────────────────────────
        Tool(
            name='migration_status',
            description='Mostra o estado das migrations (aplicadas / pendentes) por app.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'app': {'type': 'string', 'description': 'App label (opcional — todas se omitido)'},
                },
                'required': [],
            },
        ),
        Tool(
            name='make_migrations',
            description=(
                'Executa makemigrations para detectar alterações nos models. '
                'Em SAFE_MODE requer confirm=true.'
            ),
            inputSchema={
                'type': 'object',
                'properties': {
                    'app': {'type': 'string', 'description': 'App label (opcional)'},
                    'name': {'type': 'string', 'description': 'Nome para a migration (opcional)'},
                    'confirm': {
                        'type': 'boolean',
                        'description': 'Confirmação explícita necessária em SAFE_MODE',
                    },
                },
                'required': [],
            },
        ),
        Tool(
            name='run_migrations',
            description=(
                'Aplica migrations pendentes ao banco. '
                'Em SAFE_MODE requer confirm=true.'
            ),
            inputSchema={
                'type': 'object',
                'properties': {
                    'app': {'type': 'string', 'description': 'App label (opcional)'},
                    'migration': {'type': 'string', 'description': 'Migration específica (opcional)'},
                    'confirm': {
                        'type': 'boolean',
                        'description': 'Confirmação explícita necessária em SAFE_MODE',
                    },
                },
                'required': [],
            },
        ),
        Tool(
            name='show_migration_sql',
            description='Mostra o SQL que seria executado por uma migration específica.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'app': {'type': 'string', 'description': 'App label (ex: stores)'},
                    'migration': {'type': 'string', 'description': 'Nome da migration (ex: 0042_auto)'},
                },
                'required': ['app', 'migration'],
            },
        ),

        # ── Group 3: Queries ───────────────────────────────────────────────
        Tool(
            name='count_records',
            description='Conta registros de um model com filtro ORM opcional.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'model_name': {'type': 'string', 'description': 'Nome do model'},
                    'filter': {
                        'type': 'object',
                        'description': 'Filtro kwargs estilo ORM (ex: {"is_active": true})',
                    },
                },
                'required': ['model_name'],
            },
        ),
        Tool(
            name='sample_records',
            description='Retorna uma amostra de registros de um model com filtro e ordenação.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'model_name': {'type': 'string', 'description': 'Nome do model'},
                    'limit': {'type': 'integer', 'default': 5, 'description': 'Número de registros (padrão: 5)'},
                    'filter': {'type': 'object', 'description': 'Filtro ORM opcional'},
                    'order_by': {
                        'type': 'string',
                        'default': '-pk',
                        'description': 'Campo de ordenação (padrão: -pk)',
                    },
                },
                'required': ['model_name'],
            },
        ),
        Tool(
            name='run_sql',
            description=(
                'Executa SQL arbitrário. '
                'Em SAFE_MODE: writes (INSERT/UPDATE/DELETE) requerem confirm=true; '
                'DROP/TRUNCATE/ALTER TABLE são sempre bloqueados.'
            ),
            inputSchema={
                'type': 'object',
                'properties': {
                    'sql': {'type': 'string', 'description': 'SQL a executar'},
                    'params': {'type': 'array', 'description': 'Parâmetros posicionais', 'items': {}},
                    'confirm': {
                        'type': 'boolean',
                        'description': 'Confirmação para writes em SAFE_MODE',
                    },
                },
                'required': ['sql'],
            },
        ),

        # ── Group 4: Integrity ─────────────────────────────────────────────
        Tool(
            name='integrity_report',
            description='Relatório de integridade referencial de um app ou de todo o projeto.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'app': {'type': 'string', 'description': 'App label (opcional — todas se omitido)'},
                },
                'required': [],
            },
        ),
        Tool(
            name='find_orphans',
            description='Encontra registros órfãos: linhas cujo FK aponta para um id inexistente.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'model_name': {'type': 'string', 'description': 'Model que contém a FK'},
                    'field_name': {'type': 'string', 'description': 'Nome do campo FK'},
                },
                'required': ['model_name', 'field_name'],
            },
        ),
        Tool(
            name='find_duplicates',
            description='Encontra duplicatas em uma combinação de campos de um model.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'model_name': {'type': 'string', 'description': 'Nome do model'},
                    'fields': {
                        'type': 'array',
                        'items': {'type': 'string'},
                        'description': 'Lista de campos para checar unicidade',
                    },
                },
                'required': ['model_name', 'fields'],
            },
        ),
        Tool(
            name='check_nulls',
            description='Verifica campos com valores NULL em models de um app ou em todos.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'model_name': {'type': 'string', 'description': 'Model específico (opcional — todos se omitido)'},
                },
                'required': [],
            },
        ),

        # ── Group 5: Negócio ───────────────────────────────────────────────
        Tool(
            name='find_ghost_users',
            description='Encontra usuários sem pedidos, sem perfil relevante ou com email placeholder @pastita.local.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'limit': {'type': 'integer', 'default': 20, 'description': 'Máximo de registros (padrão: 20)'},
                },
                'required': [],
            },
        ),
        Tool(
            name='customer_identity_audit',
            description='Auditoria de identidade de clientes: usuários com nome placeholder, email fictício ou duplicata.',
            inputSchema={
                'type': 'object',
                'properties': {},
                'required': [],
            },
        ),
        Tool(
            name='stats_drift_check',
            description='Verifica deriva de métricas de uma loja: pedidos, receita, ticket médio vs período anterior.',
            inputSchema={
                'type': 'object',
                'properties': {
                    'store_slug': {'type': 'string', 'description': 'Slug da loja (opcional — todas se omitido)'},
                    'limit': {'type': 'integer', 'default': 20, 'description': 'Número de lojas (padrão: 20)'},
                },
                'required': [],
            },
        ),
        Tool(
            name='security_audit',
            description='Auditoria de segurança: tokens expostos, senhas em texto, API keys sem criptografia.',
            inputSchema={
                'type': 'object',
                'properties': {},
                'required': [],
            },
        ),
        Tool(
            name='pgvector_readiness',
            description='Verifica se a extensão pgvector está instalada e lista tabelas com colunas vector.',
            inputSchema={
                'type': 'object',
                'properties': {},
                'required': [],
            },
        ),
    ]


# ══════════════════════════════════════════════════════════════════════════════
#  DISPATCH
# ══════════════════════════════════════════════════════════════════════════════

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        _dispatch = {
            # Group 0
            'list_tables': _list_tables,
            'table_schema': _table_schema,
            'table_stats': _table_stats,
            'explain_query': _explain_query,
            'table_indexes': _table_indexes,
            'compare_model_vs_table': _compare_model_vs_table,
            # Group 1
            'schema_overview': _schema_overview,
            'model_detail': _model_detail,
            'find_field': _find_field,
            'relationship_graph': _relationship_graph,
            # Group 2
            'migration_status': _migration_status,
            'make_migrations': _make_migrations,
            'run_migrations': _run_migrations,
            'show_migration_sql': _show_migration_sql,
            # Group 3
            'count_records': _count_records,
            'sample_records': _sample_records,
            'run_sql': _run_sql,
            # Group 4
            'integrity_report': _integrity_report,
            'find_orphans': _find_orphans,
            'find_duplicates': _find_duplicates,
            'check_nulls': _check_nulls,
            # Group 5
            'find_ghost_users': _find_ghost_users,
            'customer_identity_audit': _customer_identity_audit,
            'stats_drift_check': _stats_drift_check,
            'security_audit': _security_audit,
            'pgvector_readiness': _pgvector_readiness,
        }
        if name not in _dispatch:
            return _err(f'Ferramenta desconhecida: {name}')
        return await _dispatch[name](arguments)
    except Exception as exc:
        return _err(f'{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}')


# ══════════════════════════════════════════════════════════════════════════════
#  STUBS — Group 0: PostgreSQL Tables
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
#  STUBS — Group 1: Schema Django
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
#  STUBS — Group 2: Migrations
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
#  STUBS — Group 3: Queries
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
            return _err(
                f'SQL bloqueado: {blocked} não é permitido. '
                'Use migrations para mudanças de schema.'
            )
    if SAFE_MODE and is_write and not args.get('confirm'):
        return _err(
            f'SAFE_MODE ativo — escrita requer confirm=true. '
            f'SQL detectado como write (começa com {sql_upper.split()[0] if sql_upper else "?"}).'
        )
    return _err('Not implemented yet — Task 5')


# ══════════════════════════════════════════════════════════════════════════════
#  STUBS — Group 4: Integrity
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
#  STUBS — Group 5: Negócio
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
