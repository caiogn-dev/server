# 🚀 Guia de Conexão com Supabase PostgreSQL

## 📋 Passo 1: Criar Projeto no Supabase

1. Acesse: https://supabase.com/
2. Faça login ou crie uma conta
3. Clique em **"New Project"**
4. Preencha os dados:
   - **Project Name**: `pastita-api` (ou seu nome)
   - **Database Password**: Crie uma senha forte e anote
   - **Region**: Selecione a mais próxima do Brasil (São Paulo se disponível)
5. Clique **"Create new project"** e aguarde (~2 minutos)

---

## 🔑 Passo 2: Obter Credenciais de Conexão

Após o projeto ser criado:

1. Na barra lateral, vá em **Settings** → **Database**
2. Procure por **"Connection String"** ou **"JDBC"**
3. Você verá algo assim:
   ```
   postgresql://postgres:[PASSWORD]@db.[PROJECT-ID].supabase.co:5432/postgres
   ```

4. Anote os valores:
   - **DB_USER**: `postgres`
   - **DB_PASSWORD**: `[sua-senha-gerada]`
   - **DB_HOST**: `db.[PROJECT-ID].supabase.co`
   - **DB_PORT**: `5432`
   - **DB_NAME**: `postgres`

---

## ✏️ Passo 3: Atualizar Arquivo `.env`

Abra o arquivo `.env` na pasta `c:\Users\User\Documents\api\server\` e atualize:

```ini
# Database Configuration - PostgreSQL/Supabase
DB_ENGINE=django.db.backends.postgresql
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=SUA_SENHA_SUPABASE_AQUI
DB_HOST=db.seu-project-id.supabase.co
DB_PORT=5432
```

**Exemplo completo:**
```ini
DB_ENGINE=django.db.backends.postgresql
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=abc123XYZ!@#
DB_HOST=db.xyzabcde.supabase.co
DB_PORT=5432
```

---

## 🔄 Passo 4: Criar Migrations

Abra o PowerShell em `c:\Users\User\Documents\api\server\` e execute:

```powershell
# Ativar venv
C:\Users\User\Documents\api\venv\Scripts\Activate.ps1

# Criar migrations para PostgreSQL
python manage.py makemigrations

# Aplicar migrations ao Supabase
python manage.py migrate
```

**Saída esperada:**
```
Operations to perform:
  Apply all migrations: admin, api, auth, contenttypes, sessions
Running migrations:
  Applying contenttypes.0001_initial... OK
  Applying auth.0001_initial... OK
  ...
```

---

## ✅ Passo 5: Verificar Conexão

Execute o comando de teste:

```powershell
python manage.py dbshell
```

Você deve ver um prompt PostgreSQL:
```
postgres=>#
```

Digite `\q` para sair.

---

## 🚀 Passo 6: Iniciar Servidor com Supabase

```powershell
python manage.py runserver
```

Acesse http://localhost:8000/api/ para confirmar funcionamento.

---

## 🆘 Troubleshooting

### ❌ Erro: `could not connect to server`
- Verifique se o **DB_HOST** está correto
- Confirme a **DB_PASSWORD**
- Teste a conexão no Supabase UI

### ❌ Erro: `permission denied for schema public`
- No Supabase, vá em **SQL** e execute:
  ```sql
  GRANT ALL ON SCHEMA public TO postgres;
  GRANT ALL ON ALL TABLES IN SCHEMA public TO postgres;
  ```

### ❌ Erro: `psycopg2` não encontrado
```powershell
pip install psycopg2-binary
```

---

## 📝 Ambiente Local (Desenvolvimento)

Para voltar a usar SQLite:

```ini
DB_ENGINE=django.db.backends.sqlite3
```

---

## 🔐 Segurança em Produção

- Nunca compartilhe seu arquivo `.env`
- Use variáveis de ambiente no servidor
- Altere `DEBUG=False` em produção
- Use `ALLOWED_HOSTS = ['pastita.com.br', 'www.pastita.com.br']`
- Gere uma nova `SECRET_KEY` para produção

---

## 📚 Links Úteis

- [Supabase Docs](https://supabase.com/docs)
- [Django PostgreSQL](https://docs.djangoproject.com/en/6.0/ref/databases/#postgresql-notes)
- [Psycopg2 Docs](https://www.psycopg.org/2/)
