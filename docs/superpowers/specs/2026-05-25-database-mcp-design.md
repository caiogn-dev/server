# Database MCP Server — Design Spec

**Data:** 2026-05-25
**Projeto:** server2 (Cardapidex backend)
**Arquivo alvo:** `/home/graco/WORK/server2/mcp_database.py`

---

## Objetivo

Criar um MCP server (`mcp_database.py`) que dá ao Claude Code acesso completo ao banco de dados do server2 — inspeção de schema, queries, migrations, análise de integridade e ferramentas de domínio específicas do Cardapidex.

Serve como ferramenta principal para conduzir o refactor do banco (sub-projetos A, B, D) com segurança e visibilidade total.

---

## Arquitetura

### Localização

```
/home/graco/WORK/server2/
├── mcp_whatsapp_bot.py      ← existente
└── mcp_database.py          ← novo (este spec)
```

### Bootstrap

Idêntico ao `mcp_whatsapp_bot.py` — Django setup antes de qualquer import de model:

```python
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
import django
django.setup()

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server('cardapidex-database')
```

### Modo Produção Seguro

Controlado por variável de ambiente:

```python
SAFE_MODE = os.environ.get('MCP_DB_SAFE_MODE', 'true').lower() == 'true'
```

Comportamento em `SAFE_MODE=true`:
- Qualquer write (INSERT/UPDATE/DELETE via `run_sql`) exige `confirm=true` no payload
- `DROP`, `TRUNCATE`, `ALTER TABLE` bloqueados mesmo com `confirm=true`
- `make_migrations` e `run_migrations` exigem `confirm=true`
- `sample_records` mascara campos sensíveis: `*token*`, `*key*`, `*secret*`, `*password*`

Comportamento em `SAFE_MODE=false` (dev):
- Sem restrições de confirmação
- Sem mascaramento de campos

### Registro no Claude Code

```bash
# Dev (sem restrições)
claude mcp add database -- python /home/graco/WORK/server2/mcp_database.py

# Produção (seguro por padrão)
claude mcp add database-prod -- env MCP_DB_SAFE_MODE=true python /home/graco/WORK/server2/mcp_database.py
```

---

## Ferramentas — 26 no total, 6 grupos

### Grupo 0: PostgreSQL Tables (6 ferramentas)

Acesso direto ao PostgreSQL via `django.db.connection` — independente do Django ORM.

#### `list_tables`
Lista todas as tabelas reais no banco (incluindo tabelas fora do Django).

**Input:**
```json
{
  "schema": "public",         // opcional, default "public"
  "filter": "store_"          // opcional, substring match no nome
}
```

**Output:**
```json
[{
  "table_name": "store_customers",
  "row_count": 142,
  "size_pretty": "2.3 MB",
  "has_django_model": true,
  "django_model": "stores.StoreCustomer"
}]
```

#### `table_schema`
Estrutura completa da tabela no PostgreSQL.

**Input:** `table_name (str)`

**Output:**
```json
{
  "columns": [{"name": "id", "pg_type": "uuid", "nullable": false, "default": "gen_random_uuid()"}],
  "indexes": [{"name": "...", "columns": [...], "unique": true, "partial_where": null}],
  "constraints": [{"type": "FK", "column": "store_id", "references": "stores(id)", "on_delete": "CASCADE"}],
  "triggers": []
}
```

#### `table_stats`
Estatísticas de uso do PostgreSQL (`pg_stat_user_tables`).

**Input:** `table_name? (str)` — se vazio, top 20 por tamanho

**Output:**
```json
[{
  "table": "store_orders",
  "rows_estimate": 8420,
  "total_size": "45 MB",
  "index_size": "12 MB",
  "seq_scans": 3,
  "idx_scans": 12847,
  "last_vacuum": "2026-05-24T03:00:00Z",
  "last_analyze": "2026-05-24T03:00:00Z"
}]
```

#### `explain_query`
EXPLAIN (ANALYZE opcional) de uma query.

**Input:**
```json
{
  "sql": "SELECT * FROM store_orders WHERE store_id = $1",
  "params": ["uuid-here"],
  "analyze": false  // false = só EXPLAIN sem executar, true = EXPLAIN ANALYZE
}
```

**Output:** Plano de execução formatado + warnings de seq scan em tabelas grandes.

#### `table_indexes`
Todos os indexes de uma tabela com estatísticas de uso.

**Input:** `table_name (str)`

**Output:**
```json
{
  "indexes": [{"name": "customer_phone_idx", "columns": ["phone"], "type": "btree", "unique": false, "usage_count": 4821}],
  "missing_fk_indexes": ["unified_user_id — FK sem index!"]
}
```

Inclui análise automática de FKs sem index correspondente.

#### `compare_model_vs_table`
Diff entre o Django model e a tabela real no banco.

**Input:** `model_name (str)`

**Output:**
```json
{
  "in_model_not_in_table": ["new_field_not_migrated"],
  "in_table_not_in_model": ["legacy_column_forgotten"],
  "type_mismatches": [{"field": "metadata", "model_type": "JSONField", "pg_type": "text"}]
}
```

---

### Grupo 1: Schema Django (4 ferramentas)

#### `schema_overview`
Mapa completo de todos os apps instalados → models → fields.

**Input:** `app_filter? (str)` — ex: `"stores"`, `"users"`

**Output:** Dict app → [models com fields resumidos, FKs, db_table, row_count]

#### `model_detail`
Deep dive em um model específico.

**Input:** `model_name (str)` — ex: `"StoreCustomer"`, `"UnifiedUser"`

**Output:**
- Todos os campos com tipos Django + constraints
- FKs (para onde aponta + on_delete)
- Reverse relations (quem aponta para este model)
- unique_together, indexes
- Contagem de registros atual
- 3 registros de sample (com mascaramento em SAFE_MODE)

#### `find_field`
Encontra todos os models que têm um campo com nome ou tipo específico.

**Input:** `field_name? (str)`, `field_type? (str)` — pelo menos um obrigatório

Exemplos: `field_name="phone"` retorna todos os models com campo `phone`. `field_type="JSONField"` lista todos os JSONFields do projeto.

**Output:** `[{"app": "stores", "model": "StoreCustomer", "field": "phone", "type": "CharField"}]`

#### `relationship_graph`
Grafo de dependências de um model (quem depende de quem).

**Input:** `model_name (str)`, `depth? (int, default=2)`

**Output:** Árvore de texto mostrando FKs de entrada e saída até a profundidade solicitada.

```
StoreCustomer
├── → Store (FK, CASCADE)
├── → UnifiedUser (FK, SET_NULL) [opcional]
├── → auth.User (FK, CASCADE) [legado]
├── ← StoreOrder.customer (SET_NULL)
└── ← StoreCustomerAddress.customer (CASCADE)
```

---

### Grupo 2: Migrations (4 ferramentas)

#### `migration_status`
Estado de todas as migrations aplicadas/pendentes.

**Input:** `app? (str)`

**Output:** `[{"app": "stores", "name": "0042_...", "applied": true, "applied_at": "2026-03-10"}]`

#### `make_migrations`
Cria novas migrations para mudanças de model.

**Input:** `app? (str)`, `name? (str)`, `confirm (bool)` — obrigatório em SAFE_MODE

**Output:** Lista de migration files criados ou `"No changes detected"`.

Em SAFE_MODE sem `confirm=true` → erro descritivo com instrução de uso.

#### `run_migrations`
Aplica migrations pendentes.

**Input:** `app? (str)`, `migration? (str)`, `confirm (bool)` — obrigatório em SAFE_MODE

**Output:** Log linha a linha das migrations aplicadas.

#### `show_migration_sql`
SQL que seria executado por uma migration (dry-run, sem executar).

**Input:** `app (str)`, `migration (str)`

**Output:** SQL completo gerado pelo Django (`sqlmigrate`).

---

### Grupo 3: Queries (3 ferramentas)

#### `count_records`
Conta registros com filtro opcional.

**Input:** `model_name (str)`, `filter? (dict)` — ex: `{"is_active": true, "store__slug": "ce-saladas"}`

**Output:** `{"count": 142, "model": "StoreCustomer", "filter_applied": {...}}`

#### `sample_records`
Retorna N registros de um model.

**Input:** `model_name (str)`, `limit? (int, default=5)`, `filter? (dict)`, `order_by? (str)`

**Output:** Lista de dicts serializados. Em SAFE_MODE, campos contendo `token`, `key`, `secret`, `password`, `api_key` são substituídos por `"***"`.

#### `run_sql`
Executa SQL arbitrário.

**Input:**
```json
{
  "sql": "UPDATE store_customers SET unified_user_id = ... WHERE ...",
  "params": [],
  "confirm": true  // obrigatório para writes em SAFE_MODE
}
```

**Output:**
- SELECT: `{"rows": [...], "count": N}`
- INSERT/UPDATE/DELETE: `{"rows_affected": N}`

**Bloqueios em SAFE_MODE:**
- `confirm` não fornecido ou `false` em writes → erro
- SQL contendo `DROP`, `TRUNCATE`, `ALTER TABLE` → erro mesmo com `confirm=true`

---

### Grupo 4: Integridade (4 ferramentas)

#### `integrity_report`
Relatório completo de problemas de dados no banco.

**Input:** `app? (str)` — se vazio, verifica tudo

**Output:**
```json
{
  "broken_fks": [{"model": "StoreCustomer", "field": "unified_user_id", "broken_count": 0}],
  "unexpected_nulls": [{"model": "StoreCustomer", "field": "phone", "null_count": 23}],
  "deprecated_fields_with_data": [{"model": "StoreCustomer", "field": "addresses", "non_empty_count": 89}],
  "duplicate_groups": [...],
  "summary": {"total_issues": 3, "critical": 1, "warnings": 2}
}
```

#### `find_orphans`
Registros com FK quebrada (referência a registro inexistente).

**Input:** `model_name (str)`, `field_name (str)`

**Output:** `{"broken_count": 0, "sample_ids": []}` — usa SQL de JOIN para detectar.

#### `find_duplicates`
Agrupa registros duplicados por combinação de campos.

**Input:** `model_name (str)`, `fields (list[str])` — ex: `["store_id", "phone"]`

**Output:**
```json
[{"values": {"store_id": "uuid", "phone": "5511..."}, "count": 3, "ids": ["...", "...", "..."]}]
```

#### `check_nulls`
Campos com nulls/blanks inesperados.

**Input:** `model_name? (str)` — se vazio, verifica todos os models

**Output:** `[{"model": "StoreCustomer", "field": "phone", "blank_count": 23, "severity": "warning"}]`

---

### Grupo 5: Negócio Cardapidex (5 ferramentas)

#### `find_ghost_users`
auth.Users criados artificialmente para clientes WhatsApp.

**Input:** `limit? (int, default=20)`

**Detecção:** email contém `@pastita.local` OU username começa com `cliente_`

**Output:**
```json
{
  "total_ghost_users": 847,
  "sample": [{"id": 1, "email": "cliente_5511...@pastita.local", "store_customers": 2}],
  "recommendation": "Estes usuários podem ser migrados para UnifiedUser e removidos do auth.User"
}
```

#### `customer_identity_audit`
Análise completa do estado atual do triângulo de identidade.

**Input:** nenhum

**Output:**
```json
{
  "store_customers_without_unified_user": 234,
  "unified_users_without_django_user": 1205,
  "user_profiles_with_duplicate_phone": 12,
  "customers_with_multiple_records_same_store": 3,
  "ghost_users_total": 847,
  "migration_completion": "27%",
  "recommendation": "..."
}
```

#### `stats_drift_check`
Detecta divergência entre stats cacheados e a fonte real.

**Input:** `store_slug? (str)`, `limit? (int, default=20)`

**Lógica:** Para cada StoreCustomer, recalcula `total_orders` e `total_spent` a partir dos StoreOrders reais e compara com os valores cacheados.

**Output:**
```json
[{
  "customer_id": "uuid",
  "customer_email": "joao@...",
  "cached_total_orders": 5,
  "real_total_orders": 8,
  "cached_total_spent": "150.00",
  "real_total_spent": "230.00",
  "drift_detected": true
}]
```

#### `security_audit`
Encontra campos sensíveis armazenados sem criptografia.

**Input:** nenhum

**Output:**
```json
{
  "plaintext_secrets": [
    {"model": "Agent", "field": "api_key", "records_with_data": 4, "severity": "CRITICAL"},
    {"model": "MessengerAccount", "field": "page_access_token", "records_with_data": 2, "severity": "CRITICAL"}
  ],
  "recommendation": "Migrar para EncryptedCharField — ver apps/core/fields.py para o padrão existente"
}
```

#### `pgvector_readiness`
Verifica disponibilidade do pgvector para o sub-projeto D.

**Input:** nenhum

**Output:**
```json
{
  "extension_installed": false,
  "pg_version": "16.2",
  "install_command": "CREATE EXTENSION IF NOT EXISTS vector;",
  "existing_vector_columns": [],
  "django_package": "pgvector não instalado — pip install pgvector",
  "ready": false
}
```

---

## Segurança e Edge Cases

### Mascaramento de dados sensíveis

Em SAFE_MODE, `sample_records` aplica mascaramento automático em campos cujo nome contém:
`token`, `key`, `secret`, `password`, `api_key`, `access_token`, `refresh_token`, `encrypted`

Valor mascarado: `"***REDACTED***"`

### Timeout em queries longas

`run_sql` e `explain_query` com `analyze=true` executam com statement timeout de 30s:
```sql
SET LOCAL statement_timeout = '30s';
```

### Serialização

Todos os outputs usam `json.dumps(..., default=str)` — UUIDs, datetimes, Decimals são convertidos para string automaticamente.

---

## Dependências

```
mcp          # já instalado (mcp_whatsapp_bot.py usa)
django       # já instalado
psycopg2     # já instalado (backend PostgreSQL do Django)
```

Sem novas dependências.

---

## Testes manuais (pós-implementação)

```bash
# 1. Registrar
claude mcp add database -- python /home/graco/WORK/server2/mcp_database.py

# 2. Verificar lista de tools
# (no Claude Code: /mcp e verificar "database" listado)

# 3. Smoke tests via Claude Code
# "use the database MCP to run schema_overview for the stores app"
# "use the database MCP to run customer_identity_audit"
# "use the database MCP to find all JSONFields in the project"
# "use the database MCP to check pgvector_readiness"
```
