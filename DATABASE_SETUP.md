# 🚀 Guia de Configuração de Banco de Dados

Este projeto usa `DATABASE_URL` para configuração do banco de dados, compatível com diversos provedores.

## 📋 Configuração Atual

O projeto usa `dj-database-url` para parsing da URL do banco:

- **Desenvolvimento**: SQLite (padrão)
- **Produção**: PostgreSQL (Railway, Supabase, etc.)

## 🔧 Configuração via DATABASE_URL

### Formato da URL

```
postgresql://USER:PASSWORD@HOST:PORT/DATABASE
```

### Exemplos

**SQLite (desenvolvimento):**
```env
DATABASE_URL=sqlite:///db.sqlite3
```

**PostgreSQL (Supabase):**
```env
DATABASE_URL=postgresql://postgres:SUA_SENHA@db.SEU_PROJECT.supabase.co:5432/postgres
```

**PostgreSQL (Railway):**
```env
DATABASE_URL=postgresql://postgres:SENHA@HOST.railway.app:PORT/railway
```

## 📝 Configuração no .env

```env
# Desenvolvimento (SQLite)
DEBUG=True
DATABASE_URL=sqlite:///db.sqlite3

# Produção (PostgreSQL)
DEBUG=False
DATABASE_URL=postgresql://user:password@host:5432/database
```

## 🚀 Supabase Setup

1. Crie projeto em https://supabase.com/
2. Vá em **Settings** → **Database**
3. Copie a **Connection String** (URI)
4. Cole no `.env` como `DATABASE_URL`

## 🔄 Migrations

```bash
# Criar migrations
python manage.py makemigrations

# Aplicar migrations
python manage.py migrate
```

## 🆘 Troubleshooting

### Erro: `psycopg2` não encontrado
```bash
pip install psycopg2-binary
```

### Erro de conexão
- Verifique se a URL está correta
- Confirme que o IP está liberado no firewall do banco
- Teste a conexão com `python manage.py dbshell`

## 🔐 Segurança

- Nunca commite o arquivo `.env`
- Use variáveis de ambiente em produção
- Altere `DEBUG=False` em produção

## 📚 Links Úteis

- [dj-database-url](https://github.com/jazzband/dj-database-url)
- [Supabase Docs](https://supabase.com/docs)
- [Railway Docs](https://docs.railway.app/)
