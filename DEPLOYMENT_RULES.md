# ⚠️ DEPLOYMENT RULES - NUNCA QUEBRAR

## CRITICAL RULES

### 1. BANCO DE DADOS - NUNCA DELETAR VOLUMES
❌ ERRADO: `docker compose down -v`
❌ ERRADO: `docker volume rm server2_postgres_data`

✅ CORRETO: `docker compose down` (mantém volumes)
✅ CORRETO: `docker compose up -d --build` (rebuild sem deletar dados)

### 2. BRANCHES
- `main` = PRODUÇÃO (painel.cardapidex.com.br)
- `development` = STAGING/TESTE
- `feature/*` = FEATURES (merge → development → main)

NUNCA fazer mudanças direto em `main`!

### 3. REBUILD (Sem perder banco)
```bash
# Correto - mantém banco de dados
docker compose down
docker compose up -d --build

# Alternativa mais rápida
docker compose up -d --build  # Reinicia se já existe
```

### 4. RESET COMPLETO (Se realmente precisar)
⚠️ Isso DELETA o banco - só se absolutamente necessário:
```bash
docker compose down -v
docker compose up -d --build
# Depois: recrie as lojas, usuários, etc
```

## LOJAS PADRÃO (Para recrear se necessário)
- `ce-saladas` @ -10.1707379, -48.3090628
- `kero-kero` @ -10.1707379, -48.3090628  
- `pastita` @ -10.1707379, -48.3090628

## SUPERUSER PADRÃO
- Email: admin@cardapidex.com.br
- Senha: admin123456
