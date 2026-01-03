# 🚂 Railway Deployment - Guia Completo (Via Web)

## ✅ Pré-requisitos

- ✅ Código no GitHub (já tem)
- ✅ Supabase configurado (já tem)
- ✅ `.env` com variáveis (já tem)

---

## 🚀 Passo 1: Crie Conta no Railway

1. Acesse: https://railway.app/
2. Clique **"Start Free"**
3. **Login with GitHub** (autorize)
4. Pronto! 🎉

---

## 📋 Passo 2: Crie um Novo Projeto

1. Na página inicial, clique **"+ New Project"**
2. Escolha **"Deploy from GitHub repo"**
3. **Conecte GitHub** (se não estiver conectado)
4. Procure por **"pastita-api"** (seu repo)
5. Clique nele para selecionar
6. Clique **"Deploy"**

Railway vai criar o projeto automaticamente! ✨

---

## ⚙️ Passo 3: Adicione Variáveis de Ambiente

Na página do projeto:

1. Vá em **"Variables"** (abinha do topo)
2. Clique **"+ New Variable"**
3. Adicione cada uma:

```
DEBUG = False
SECRET_KEY = django-insecure-eg*ds206gdc0j_xfm%m%#h#qzo)ycucg@3c=8+=hf#%(@t3gc%
DB_ENGINE = django.db.backends.postgresql
DB_NAME = postgres
DB_USER = postgres
DB_PASSWORD = Caio@2026mano
DB_HOST = db.irrakcwiaubidijzhdok.supabase.co
DB_PORT = 5432
MERCADO_PAGO_ACCESS_TOKEN = seu-token-aqui
ALLOWED_HOSTS = seu-app.up.railway.app
```

Depois de adicionar, clique **"Save"**

---

## 🔧 Passo 4: Configure o Deploy

Na página do projeto:

1. Vá em **"Settings"** (engrenagem)
2. Procure por **"Domains"**
3. Clique **"Generate Domain"**
4. Você vai ter uma URL como:
   ```
   seu-app-production.up.railway.app
   ```

Copie e guarde essa URL! 🌐

---

## 📦 Passo 5: Configure o Procfile (IMPORTANTE)

Seu projeto precisa de um arquivo `Procfile` na raiz:

```
web: gunicorn server.wsgi:application
```

**Se ainda não tiver:**

1. Volte para VS Code
2. Crie um arquivo **Procfile** (sem extensão) na pasta `server`
3. Cole:
```
web: gunicorn server.wsgi:application
```
4. Commit e push:
```powershell
git add .
git commit -m "Add Procfile for Railway"
git push origin main
```

Railway vai detectar automaticamente! ✅

---

## 🚀 Passo 6: Deploy Automático

Quando você fizer `git push`, Railway faz deploy automaticamente!

1. Vá em **"Deployments"** no Railway
2. Veja o progresso em tempo real
3. Quando aparecer uma **bolinha verde**, está online! ✅

---

## 🧪 Passo 7: Teste sua API

```
https://seu-app-production.up.railway.app/api/
```

ou via curl:

```powershell
curl https://seu-app-production.up.railway.app/api/
```

---

## 📊 Railway Dashboard Overview

| Abinha | O que faz |
|--------|-----------|
| **Deployments** | Ver histórico de deploys |
| **Logs** | Ver logs em tempo real |
| **Variables** | Gerenciar variáveis de ambiente |
| **Settings** | Domínio, região, etc |
| **Metrics** | CPU, memória, requisições |

---

## 💰 Custo

- **Free tier**: $5/mês (incluído)
- **Supabase**: Já tem (free)
- **Total**: $0 (cabe no free tier)

---

## 🐛 Troubleshooting

### Build falha
→ Clique em **"Logs"** e veja o erro

### Erro 502
→ Migrations não rodaram. Vá em **"Variables"** e triggere novo deploy

### Domínio não funciona
→ Aguarde 2-5 minutos (DNS propaga)

---

## ✨ Resumo Rápido

1. ✅ Crie conta Railway
2. ✅ Conecte GitHub
3. ✅ Adicione variáveis
4. ✅ Crie Procfile
5. ✅ Git push
6. ✅ Pronto! 🚀

---

**Conseguiu? Avisa quando estiver online!** 🎉
