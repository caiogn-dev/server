# 🚀 Guia Completo: Deploy Django na AWS

## ⚡ Opção Mais Rápida: Elastic Beanstalk (15 minutos)

### Passo 1: Prepare seu código para Git

```bash
cd c:\Users\User\Documents\api\server

# Crie .gitignore
echo "venv/
*.pyc
__pycache__/
db.sqlite3
.env
*.egg-info/
staticfiles/
media/
.DS_Store" > .gitignore

# Inicie git (se não tiver)
git init
git add .
git commit -m "Initial commit - ready for AWS"
```

### Passo 2: Push para GitHub

```bash
# 1. Crie um repositório vazio em: https://github.com/new
#    Nome: pastita-api
#    Não adicione README/gitignore

# 2. No terminal:
git remote add origin https://github.com/SEU-USER/pastita-api.git
git branch -M main
git push -u origin main
```

### Passo 3: Configure AWS Credentials

1. Acesse: https://console.aws.amazon.com/
2. Crie uma conta (free tier)
3. Vá em **IAM** → **Users** → **Create user**
   - Nome: `pastita-deploy`
   - Selecione: **Attach policies directly** → `AdministratorAccess`
4. Após criar, clique no usuário → **Security credentials** → **Create access key**
   - Escolha: `Command Line Interface (CLI)`
   - Copie: `Access Key ID` e `Secret Access Key`

### Passo 4: Instale EB CLI

```powershell
# No PowerShell como Admin:
python -m pip install awsebcli --upgrade --user

# Verifique
eb --version
```

### Passo 5: Configure AWS Credentials Localmente

```bash
# Configure
aws configure

# Será pedido:
AWS Access Key ID: [cole-aqui]
AWS Secret Access Key: [cole-aqui]
Default region name: sa-east-1
Default output format: json
```

### Passo 6: Initialize Elastic Beanstalk

```bash
cd c:\Users\User\Documents\api\server

# Initialize
eb init -p python-3.11 pastita-api --region sa-east-1

# Será perguntado:
# - Do you want to set up SSH? → y
# - Select a keypair → [crie uma nova ou selecione]
```

### Passo 7: Crie o Environment

```bash
# Crie ambiente (substitua YOUR_* pelos valores reais)
eb create pastita-production \
  --instance-type t3.micro \
  --envvars DEBUG=False,DATABASE_URL=YOUR_DATABASE_URL,MERCADO_PAGO_ACCESS_TOKEN=YOUR_MP_TOKEN,SECRET_KEY=YOUR_SECRET_KEY,FRONTEND_URL=https://pastita.com.br,BACKEND_URL=https://your-api-url.com

# Aguarde (3-5 minutos)
# Quando terminar:
eb open
```

⚠️ **IMPORTANTE**: Nunca compartilhe suas credenciais! Use variáveis de ambiente.

**Pronto! Sua API está ao vivo! 🎉**

---

## 📋 Alternativa: EC2 (Mais Controle)

### Passo 1: Crie uma Instância EC2

1. Acesse: https://console.aws.amazon.com/ec2/
2. **Instances** → **Launch instance**
   - **Name**: pastita-api
   - **AMI**: Ubuntu 22.04 LTS (free tier)
   - **Instance type**: t3.micro
   - **Key pair**: Crie uma nova (salve .pem em local seguro)
   - **Network settings**: 
     - Allow SSH (22) ✅
     - Allow HTTP (80) ✅
     - Allow HTTPS (443) ✅
   - **Storage**: 30 GB (free tier)
   - **Launch**

### Passo 2: Conecte via SSH

```bash
# Windows PowerShell
# Navegue até a pasta com o .pem
cd Downloads

# Conecte
ssh -i seu-key.pem ubuntu@seu-ip-publico

# Exemplo:
# ssh -i pastita-key.pem ubuntu@35.123.45.67
```

### Passo 3: Configure o Servidor

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y \
  python3-pip \
  python3-venv \
  postgresql-client \
  git \
  nginx \
  certbot \
  python3-certbot-nginx

# Clone seu repositório
git clone https://github.com/SEU-USER/pastita-api.git
cd pastita-api

# Create venv
python3 -m venv venv
source venv/bin/activate

# Install Python packages
pip install -r requirements.txt
pip install gunicorn

# Create .env (copie do seu local)
nano .env
# Cole o conteúdo e Ctrl+X, Y, Enter
```

### Passo 4: Configure Gunicorn

```bash
# Teste
gunicorn --bind 127.0.0.1:8000 server.wsgi

# Ctrl+C para parar
```

### Passo 5: Configure Nginx

```bash
# Create config
sudo nano /etc/nginx/sites-available/pastita

# Cole isto:
```

```nginx
server {
    listen 80;
    server_name _;  # Mude para seu domínio depois

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /home/ubuntu/pastita-api/staticfiles/;
    }

    location /media/ {
        alias /home/ubuntu/pastita-api/media/;
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/pastita /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default

# Test
sudo nginx -t

# Restart
sudo systemctl restart nginx
```

### Passo 6: Configure Systemd (Auto-start)

```bash
# Create service file
sudo nano /etc/systemd/system/pastita.service
```

```ini
[Unit]
Description=Pastita Django API
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/pastita-api
ExecStart=/home/ubuntu/pastita-api/venv/bin/gunicorn \
    --bind 127.0.0.1:8000 \
    --workers 4 \
    --timeout 120 \
    server.wsgi:application

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Enable e start
sudo systemctl enable pastita
sudo systemctl start pastita

# Check status
sudo systemctl status pastita

# View logs
sudo journalctl -u pastita -f
```

### Passo 7: HTTPS com Let's Encrypt

```bash
# Replace _ com seu domínio em /etc/nginx/sites-available/pastita
# Depois:

sudo certbot --nginx -d seu-dominio.com

# Follow prompts
```

**Pronto! API rodando com HTTPS! 🔐**

---

## 🔍 Teste sua Aplicação

```bash
# Localmente (desenvolvimento)
curl http://localhost:8000/api/

# Em produção
curl https://seu-dominio.com/api/
curl https://seu-app-eb.elasticbeanstalk.com/api/
```

---

## 📊 Custo Estimado (12 meses free tier)

| Serviço | EB | EC2 |
|---------|----|----|
| Compute | t3.micro ✅ | t3.micro ✅ |
| Database | Supabase | Supabase |
| Storage | 30GB ✅ | 30GB ✅ |
| **Total** | **$0** | **$0** |

---

## 🐛 Troubleshooting

### EB Deployment falha
```bash
eb logs
# Veja os erros
```

### EC2 Connection timeout
```bash
# Verifique Security Group
# Portas 22, 80, 443 devem estar abertas
```

### Gunicorn não inicia
```bash
# SSH para EC2 e teste:
/home/ubuntu/pastita-api/venv/bin/gunicorn --bind 127.0.0.1:8000 server.wsgi
```

---

## ✅ Checklist Final

- [ ] GitHub: código commitado
- [ ] AWS: conta criada
- [ ] Credentials: AWS CLI configurado
- [ ] EB: ambiente criado OU EC2: instância rodando
- [ ] Domínio: apontando para AWS
- [ ] HTTPS: certificado Let's Encrypt instalado
- [ ] Banco: Supabase conectando
- [ ] API: respondendo em https://seu-dominio.com/api/

---

**Qual você quer fazer agora?**
1. **EB (rápido)** - Só copiar-colar comandos
2. **EC2 (completo)** - Mais aprendizado

Diga qual e vou dar suporte total! 🚀
