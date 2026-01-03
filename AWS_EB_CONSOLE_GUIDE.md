# 🌐 AWS Elastic Beanstalk via Console (Interface Web)

## ✅ Pré-requisitos

- ✅ Conta AWS criada
- ✅ Código no GitHub (pastita-api)
- ✅ Credenciais AWS

---

## 🚀 Passo 1: Acesse o Console AWS

1. Vá para: https://console.aws.amazon.com/
2. Faça login com sua conta
3. Procure por **"Elastic Beanstalk"** (use a search bar no topo)
4. Clique em **"Elastic Beanstalk"**

---

## 📋 Passo 2: Crie uma Nova Aplicação

Na página do Elastic Beanstalk:

1. Clique no botão azul **"Create application"**
2. Preencha:
   - **Application name**: `pastita-api`
   - **Environment name**: `pastita-production`
   - **Domain name** (opcional): `pastita-production`

3. Clique **"Next"**

---

## 🔧 Passo 3: Configure o Ambiente

1. **Platform**: 
   - Selecione **"Python"**
   - Versão: **"Python 3.11"**

2. **Application code**:
   - Selecione **"Upload your code"**
   - Clique **"Choose file"** e selecione seu arquivo `.zip` (seu projeto)
   - Ou **"Code location"** → selecione **GitHub**

---

## 📦 Passo 4: Conecte ao GitHub (Recomendado)

Se escolher GitHub:

1. Clique em **"Connect to GitHub"**
2. **Authorize AWS Connector for GitHub**
3. Procure por **"pastita-api"** (seu repo)
4. Selecione a **branch**: `main`
5. **Connect**

GitHub vai enviar o código automaticamente! ✨

---

## ⚙️ Passo 5: Configure Variáveis de Ambiente

Na mesma página, procure por **"Environment properties"**:

Adicione cada variável:

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
ALLOWED_HOSTS = pastita-production.elasticbeanstalk.com
```

Clique **"Add property"** para cada uma.

---

## 💾 Passo 6: Configure Instância

Na seção **"Instance configuration"**:

1. **Instance type**: `t3.micro` (free tier)
2. **Root volume type**: `gp2`
3. **Root volume size**: `30 GB`

---

## 🌐 Passo 7: Configure Load Balancer

Na seção **"Load balancer configuration"**:

1. **Load balancer type**: `Application Load Balancer`
2. **Environment tier**: `WebServer`

---

## 📝 Passo 8: Review e Create

1. Revise todas as configurações
2. Clique **"Create environment"** (botão verde)
3. **Aguarde 5-10 minutos** ⏳

Railway vai:
- Provisionar a instância EC2
- Instalar Python
- Clonar seu repo do GitHub
- Instalar dependências
- Rodar migrations
- Subir sua aplicação

---

## 📊 Monitorar o Deployment

1. Volte para **Elastic Beanstalk**
2. Clique em **"pastita-api"**
3. Clique em **"pastita-production"**
4. Veja o **"Recent logs"** em tempo real

Quando o status for **"Ready"** e health for **"Green"** ✅ → Pronto!

---

## 🌍 Acesse sua Aplicação

Quando estiver online, você terá uma URL como:

```
http://pastita-production.elasticbeanstalk.com/api/
```

Clique em **"Domain"** para ver a URL exata.

---

## 📝 Atualizar Código (Depois)

Quando mudar o código:

1. Commit no GitHub:
```powershell
git add .
git commit -m "Suas mudanças"
git push origin main
```

2. No AWS EB Console:
   - Vá em **"pastita-production"**
   - Clique **"Deploy"** (botão azul)
   - Selecione o commit recente
   - Clique **"Deploy"**

Pronto! Deploy automático! 🚀

---

## 🐛 Troubleshooting

### Status: "Degraded" ou "Severe"
→ Clique em **"Logs"** → **"Request Logs"** para ver o erro

### Health: "Yellow"
→ Migrations não rodaram. Conecte via SSH:
- Clique em **"EC2 instances"**
- Clique na instância
- Clique **"Connect"** (use EC2 Instance Connect)
- Execute migrations manualmente

### 502 Bad Gateway
→ Aplicação não está respondendo. Veja logs.

---

## 📚 Dashboard do EB

| Menu | O que faz |
|------|-----------|
| **Dashboard** | Status geral |
| **Configuration** | Mudar instância, variáveis, etc |
| **Logs** | Ver erros em tempo real |
| **Monitoring** | CPU, memória, requisições |
| **Application versions** | Histórico de deploys |

---

## ✨ Pronto!

Sua API estará **100% online** na AWS! 🎉

URL: `http://pastita-production.elasticbeanstalk.com/api/`

---

**Conseguiu? Me avisa quando ficar Green!** 🚀
