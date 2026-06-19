#!/bin/bash
# Ressincroniza TODAS as sequences do Postgres para MAX(coluna)+1.
# Seguro e idempotente — pode rodar a qualquer momento. OBRIGATÓRIO após
# restore de dump (senão o próximo INSERT/migrate dá "duplicate key" em loop).
set -euo pipefail

DB_CONTAINER="${DB_CONTAINER:-pastita_db}"
DB_USER="${DB_USER:-postgres}"
DB_NAME="${DB_NAME:-pastita}"

echo "[resync] ressincronizando sequences em ${DB_NAME}@${DB_CONTAINER}..."

docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 <<'SQL'
DO $$
DECLARE
    r RECORD;
    new_val BIGINT;
BEGIN
    -- pg_get_serial_sequence cobre serial E identity (o vínculo via pg_depend
    -- deptype='a' não casa no PG15).
    FOR r IN
        SELECT
            pg_get_serial_sequence(format('%I.%I', c.table_schema, c.table_name), c.column_name) AS seq,
            c.table_schema AS sch, c.table_name AS tbl, c.column_name AS col
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_schema = c.table_schema
         AND t.table_name = c.table_name
         AND t.table_type = 'BASE TABLE'
        WHERE c.table_schema NOT IN ('pg_catalog', 'information_schema')
          AND pg_get_serial_sequence(format('%I.%I', c.table_schema, c.table_name), c.column_name) IS NOT NULL
    LOOP
        EXECUTE format(
            'SELECT setval(%L, COALESCE((SELECT MAX(%I) FROM %I.%I), 0) + 1, false)',
            r.seq, r.col, r.sch, r.tbl
        ) INTO new_val;
        RAISE NOTICE 'seq % -> % (%.%)', r.seq, new_val, r.tbl, r.col;
    END LOOP;
END $$;
SQL

echo "[resync] concluído ✓"
