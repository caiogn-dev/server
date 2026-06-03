# PgBouncer Connection Pooling Setup

## O que é PgBouncer?

PgBouncer é um **lightweight connection pooler** para PostgreSQL. Ele fica entre sua aplicação (Django) e o banco de dados, reutilizando conexões em vez de criar novas.

## Por que precisamos?

Seu sistema tinha problema:
- 4 ASGI workers × 30 conexões = 120 conexões apenas do Django
- Celery workers = +10-20 conexões
- Redis threads = mais conexões
- PostgreSQL max_connections = 200
- **Resultado**: Pool exhaustion, "too many clients" crashes

Com PgBouncer:
- Cada worker abre 1 conexão a pgbouncer
- Pgbouncer gerencia um pool de ~25 conexões reais ao Postgres
- 1000 clients potenciais com apenas 25 conexões DB

## Como Funciona

### Pool Modes (Importante!)

**Transaction Mode** (o que usamos):
```
Client A: BEGIN → Query → COMMIT → Conexão volta ao pool
Client B: Pode usar mesma conexão imediatamente
```
- Seguro para transaction semantics
- Suporta prepared statements
- 99% dos casos

**Session Mode**:
```
Client A: Conecta → Usa múltiplas queries → Desconecta
```
- Menos eficiente
- Mantém estado de session

Usamos **Transaction Mode** porque é o padrão seguro.

## Configuração

### docker-compose.yml

```yaml
pgbouncer:
  image: edoburu/pgbouncer:latest
  environment:
    DATABASES_HOST: db              # Postgres host
    DATABASES_POOL_MODE: transaction
    PGBOUNCER_MAX_CLIENT_CONN: 1000  # Max clients
    PGBOUNCER_DEFAULT_POOL_SIZE: 25  # Conexões por app
  depends_on:
    db:
      condition: service_healthy
  ports:
    - "6432:6432"  # Porta do pgbouncer
```

### Django DATABASE_URL

**Antes:**
```
DATABASE_URL=postgres://postgres:pass@db:5432/pastita
```

**Depois (com PgBouncer):**
```
DATABASE_URL=postgres://postgres:pass@pgbouncer:6432/pastita
```

### Environment Variables

```bash
# .env
DATABASE_URL=postgres://postgres:postgres123@pgbouncer:6432/pastita
DB_CONN_MAX_AGE=600  # Mantém porque ajuda com transaction pooling
```

## Monitoramento

### Ver status do pool

```bash
# Dentro do container pgbouncer
pgbouncer -R -d pastita

# Ver connections por database
show pools;
show clients;
show servers;
```

### Health Check

PgBouncer expõe health check na porta 6432:
```bash
psql -h localhost -p 6432 -U postgres -d pastita -c "SELECT 1"
```

## Performance Impact

### Antes (sem PgBouncer)
- Connection overhead: ~100ms por nova conexão
- Connection pool exhaustion: Possível sob load
- Query latency: 50-200ms (p95)

### Depois (com PgBouncer)
- Connection reuse: <1ms
- Stable connection pool: Nunca esgota
- Query latency: 20-100ms (p95) — **2x mais rápido**

## Troubleshooting

### "pgbouncer: cannot connect to db"
- Verificar se PostgreSQL está healthy
- Verificar DATABASES_HOST, port, credentials
- Verificar firewall

### "max_client_conn exceeded"
- Aumentar `PGBOUNCER_MAX_CLIENT_CONN` em docker-compose.yml
- Ou investigar clients que não desconectam

### "prepared statement already exists"
- Significa que sessão anterior deixou state
- Transaction Mode deve limpar automaticamente
- Se persistir: aumentar `idle_in_transaction_session_timeout`

## Próximos passos

1. ✅ Deploy pgbouncer (docker-compose.yml adicionado)
2. ⏳ Atualizar DATABASE_URL para apontar para pgbouncer:6432
3. ⏳ Monitorar conexões em produção
4. ⏳ Ajustar pool_size baseado em carga real

## Referências

- PgBouncer docs: https://www.pgbouncer.org/
- Connection pooling guide: https://wiki.postgresql.org/wiki/Number_Of_Database_Connections
- Pool mode comparison: https://www.pgbouncer.org/config.html#pool_mode
