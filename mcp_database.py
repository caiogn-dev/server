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
import re
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
                    'field_name': {'type': 'string', 'description': 'Nome exato do campo (opcional)'},
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
#  Group 0: PostgreSQL Tables
# ══════════════════════════════════════════════════════════════════════════════

async def _list_tables(args: dict) -> list[TextContent]:
    from django.db import connection
    from django.apps import apps
    from asgiref.sync import sync_to_async

    schema = args.get('schema', 'public')
    filter_str = args.get('filter', '')

    model_table_map = {
        model._meta.db_table: f'{model._meta.app_label}.{model.__name__}'
        for model in apps.get_models()
    }

    def _fetch():
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
            return cursor.fetchall()

    rows = await sync_to_async(_fetch)()

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
    from asgiref.sync import sync_to_async

    table_name = args['table_name']

    def _fetch():
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
            if not columns:
                return None, None, None, None  # signal not found

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
                JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum AND a.attnum > 0
                WHERE t.relname = %s AND t.relkind = 'r'
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

        return columns, indexes, constraints, triggers

    columns, indexes, constraints, triggers = await sync_to_async(_fetch)()
    if columns is None:
        return _err(f'Tabela não encontrada: {table_name}')

    return _ok({
        'table': table_name,
        'columns': columns,
        'indexes': indexes,
        'constraints': constraints,
        'triggers': triggers,
    })


async def _table_stats(args: dict) -> list[TextContent]:
    from django.db import connection
    from asgiref.sync import sync_to_async

    table_name = args.get('table_name')

    def _fetch():
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
            return cursor.fetchall()

    rows = await sync_to_async(_fetch)()

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
    from asgiref.sync import sync_to_async

    sql = args['sql']
    params = args.get('params', [])
    analyze = bool(args.get('analyze', False))

    _EXPLAIN_BLOCKED = re.compile(
        r'\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|COPY|CALL)\b',
        re.IGNORECASE,
    )
    if _EXPLAIN_BLOCKED.search(sql):
        return _err('SQL contém statement não permitido em explain_query')

    def _fetch():
        with connection.cursor() as cursor:
            if analyze:
                cursor.execute("SET statement_timeout = '30s'")
            cursor.execute(f"EXPLAIN {'ANALYZE ' if analyze else ''}(FORMAT JSON) {sql}", params)
            result = cursor.fetchone()[0]
            if analyze:
                cursor.execute("SET statement_timeout = DEFAULT")
            return result

    plan = await sync_to_async(_fetch)()

    plan_text = json.dumps(plan, default=str)
    warnings = []
    if 'Seq Scan' in plan_text:
        warnings.append('Seq Scan detectado — considere adicionar um index')

    return _ok({'plan': plan, 'warnings': warnings, 'analyze_used': analyze})


async def _table_indexes(args: dict) -> list[TextContent]:
    from django.db import connection
    from asgiref.sync import sync_to_async

    table_name = args['table_name']

    def _fetch():
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

        return indexes, fk_cols

    indexes, fk_cols = await sync_to_async(_fetch)()

    indexed_leading = {idx['columns'][0] for idx in indexes if idx['columns']}
    missing_fk_indexes = [f'{col} — FK sem index!' for col in fk_cols if col not in indexed_leading]

    return _ok({'table': table_name, 'indexes': indexes, 'missing_fk_indexes': missing_fk_indexes})


async def _compare_model_vs_table(args: dict) -> list[TextContent]:
    from django.apps import apps
    from django.db import connection
    from asgiref.sync import sync_to_async

    model_name = args['model_name']
    model = next(
        (m for m in apps.get_models()
         if m.__name__ == model_name or f'{m._meta.app_label}.{m.__name__}' == model_name),
        None
    )
    if not model:
        return _err(f'Model não encontrado: {model_name}')

    model_cols = {f.column: f for f in model._meta.get_fields() if hasattr(f, 'column')}

    def _fetch():
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
            """, [model._meta.db_table])
            return {r[0]: r[1] for r in cursor.fetchall()}

    db_cols = await sync_to_async(_fetch)()

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
        'status': 'DIVERGE' if (set(model_cols) - set(db_cols) or set(db_cols) - set(model_cols) or mismatches) else 'OK',
    })


# ══════════════════════════════════════════════════════════════════════════════
#  Group 1: Schema Django
# ══════════════════════════════════════════════════════════════════════════════

async def _schema_overview(args: dict) -> list[TextContent]:
    from django.apps import apps
    from django.db import connection
    from asgiref.sync import sync_to_async

    app_filter = args.get('app_filter', '')
    result = {}

    for model in apps.get_models():
        app_label = model._meta.app_label
        if app_filter and app_filter != app_label:
            continue

        def _count(m=model):
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f'SELECT COUNT(*) FROM "{m._meta.db_table}"')
                    return cursor.fetchone()[0]
            except Exception:
                return '?'

        row_count = await sync_to_async(_count)()

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
    from asgiref.sync import sync_to_async

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

    def _fetch_count_and_sample():
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

        return row_count, sample

    row_count, sample = await sync_to_async(_fetch_count_and_sample)()

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
            name_match = field_name and field_name.lower() == f.name.lower()
            type_match = field_type and type(f).__name__ == field_type
            if (field_name and not field_type and name_match) or \
               (field_type and not field_name and type_match) or \
               (field_name and field_type and name_match and type_match):
                result.append({
                    'app': model._meta.app_label, 'model': model.__name__,
                    'field': f.name, 'type': type(f).__name__, 'column': f.column,
                })

    return _ok({'count': len(result), 'results': result})


async def _relationship_graph(args: dict) -> list[TextContent]:
    from django.apps import apps

    model_name = args['model_name']
    depth = min(int(args.get('depth', 2)), 5)

    model = next(
        (m for m in apps.get_models()
         if m.__name__ == model_name or f'{m._meta.app_label}.{m.__name__}' == model_name),
        None
    )
    if not model:
        return _err(f'Model não encontrado: {model_name}')

    lines = [model_name]

    def _out(m, prefix, d, visited=None):
        if visited is None:
            visited = set()
        if d > depth or m in visited:
            return
        branch_visited = visited | {m}
        for f in m._meta.get_fields():
            if hasattr(f, 'related_model') and f.related_model and hasattr(f, 'column'):
                rf = getattr(f, 'remote_field', None)
                on_del = str(getattr(rf, 'on_delete', '')) if rf else ''
                lines.append(f'{prefix}→ {f.related_model.__name__} (FK, {on_del})')
                if d < depth:
                    _out(f.related_model, prefix + '  ', d + 1, branch_visited)

    def _in(m, prefix):
        for rel in m._meta.related_objects:
            lines.append(f'{prefix}← {rel.related_model.__name__}.{rel.field.name} ({rel.on_delete})')

    _out(model, '├── ', 1)
    _in(model, '└── ')

    return _ok({'graph': '\n'.join(lines)})


# ══════════════════════════════════════════════════════════════════════════════
#  STUBS — Group 2: Migrations
# ══════════════════════════════════════════════════════════════════════════════

async def _migration_status(args: dict) -> list[TextContent]:
    from django.db.migrations.executor import MigrationExecutor
    from django.db import connection
    from asgiref.sync import sync_to_async

    app_filter = args.get('app', '')

    def _fetch():
        executor = MigrationExecutor(connection)
        applied = set(executor.loader.applied_migrations)
        result = []
        for (app, name) in sorted(executor.loader.disk_migrations.keys()):
            if app_filter and app_filter != app:
                continue
            result.append({'app': app, 'name': name, 'applied': (app, name) in applied})
        return result

    result = await sync_to_async(_fetch)()
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
    from asgiref.sync import sync_to_async
    from io import StringIO

    def _run():
        out = StringIO()
        kwargs = {'stdout': out, 'verbosity': 1}
        if args.get('app'):
            kwargs['app_label'] = args['app']
        if args.get('name'):
            kwargs['name'] = args['name']
        call_command('makemigrations', **kwargs)
        return out.getvalue()

    try:
        output = await sync_to_async(_run)()
    except Exception as exc:
        return _err(f'makemigrations falhou: {exc}')
    return _ok({'output': output, 'created': 'No changes detected' not in output})


async def _run_migrations(args: dict) -> list[TextContent]:
    if SAFE_MODE and not args.get('confirm'):
        return _err('SAFE_MODE ativo — forneça confirm=true para aplicar migrations')

    from django.core.management import call_command
    from asgiref.sync import sync_to_async
    from io import StringIO

    def _run():
        out = StringIO()
        call_args = []
        if args.get('app'):
            call_args.append(args['app'])
        if args.get('migration'):
            call_args.append(args['migration'])
        call_command('migrate', *call_args, stdout=out, verbosity=1)
        return out.getvalue()

    try:
        output = await sync_to_async(_run)()
    except Exception as exc:
        return _err(f'migrate falhou: {exc}')
    return _ok({'output': output})


async def _show_migration_sql(args: dict) -> list[TextContent]:
    from django.core.management import call_command
    from asgiref.sync import sync_to_async
    from io import StringIO

    def _run():
        out = StringIO()
        call_command('sqlmigrate', args['app'], args['migration'], stdout=out)
        return out.getvalue()

    try:
        sql = await sync_to_async(_run)()
    except Exception as exc:
        return _err(f'sqlmigrate falhou: {exc}')
    return _ok({'sql': sql, 'app': args['app'], 'migration': args['migration']})


# ══════════════════════════════════════════════════════════════════════════════
#  Group 3: Queries
# ══════════════════════════════════════════════════════════════════════════════

async def _count_records(args: dict) -> list[TextContent]:
    from django.apps import apps
    from asgiref.sync import sync_to_async

    model_name = args['model_name']
    model = next(
        (m for m in apps.get_models()
         if m.__name__ == model_name or f'{m._meta.app_label}.{m.__name__}' == model_name),
        None
    )
    if not model:
        return _err(f'Model não encontrado: {model_name}')

    filter_args = args.get('filter', {})

    def _fetch():
        qs = model.objects.all()
        if filter_args:
            qs = qs.filter(**filter_args)
        return qs.count()

    count = await sync_to_async(_fetch)()
    return _ok({'model': model_name, 'count': count, 'filter_applied': filter_args})


async def _sample_records(args: dict) -> list[TextContent]:
    from django.apps import apps
    from asgiref.sync import sync_to_async

    model_name = args['model_name']
    limit = min(int(args.get('limit', 5)), 200)
    filter_args = args.get('filter', {})
    order_by = args.get('order_by', '-pk')

    model = next(
        (m for m in apps.get_models()
         if m.__name__ == model_name or f'{m._meta.app_label}.{m.__name__}' == model_name),
        None
    )
    if not model:
        return _err(f'Model não encontrado: {model_name}')

    def _fetch():
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
        return records

    records = await sync_to_async(_fetch)()
    return _ok({'model': model_name, 'count': len(records), 'records': records})


async def _run_sql(args: dict) -> list[TextContent]:
    from django.db import connection
    from asgiref.sync import sync_to_async

    sql = args.get('sql', '')
    params = args.get('params', [])
    confirm = bool(args.get('confirm', False))
    sql_upper = sql.strip().upper()
    is_write = any(sql_upper.startswith(kw) for kw in ('INSERT', 'UPDATE', 'DELETE'))

    _DDL_BLOCKED = re.compile(
        r'\b(DROP|TRUNCATE|ALTER\s+TABLE)\b',
        re.IGNORECASE,
    )
    if _DDL_BLOCKED.search(sql):
        match = _DDL_BLOCKED.search(sql).group(0)
        return _err(f'SQL bloqueado: {match} não é permitido. Use migrations para mudanças de schema.')

    _RUN_SQL_DANGEROUS = re.compile(
        r'\b(CREATE|GRANT|REVOKE|COPY|CALL)\b',
        re.IGNORECASE,
    )
    if SAFE_MODE and _RUN_SQL_DANGEROUS.search(sql):
        return _err('SQL contém statement não permitido em SAFE_MODE: CREATE/GRANT/REVOKE/COPY/CALL')

    if SAFE_MODE and is_write and not confirm:
        return _err(
            f'SAFE_MODE ativo — escrita requer confirm=true. '
            f'SQL detectado como write (começa com {sql_upper.split()[0] if sql_upper else "?"}).'
        )

    def _execute():
        with connection.cursor() as cursor:
            if is_write:
                cursor.execute("SET statement_timeout = '30s'")
            try:
                cursor.execute(sql, params)
            finally:
                if is_write:
                    cursor.execute("SET statement_timeout = DEFAULT")

            if sql_upper.startswith('SELECT') or sql_upper.startswith('WITH'):
                cols = [d[0] for d in cursor.description]
                rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
                return {'rows': rows, 'count': len(rows)}
            else:
                return {'rows_affected': cursor.rowcount}

    try:
        result = await sync_to_async(_execute)()
    except Exception as exc:
        return _err(f'SQL falhou: {exc}')

    return _ok(result)


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
