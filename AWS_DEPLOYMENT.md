# AWS Deployment Guide para Django Pastita API

## 🚀 Opção 1: AWS Elastic Beanstalk (RECOMENDADO)

### Vantagens:
✅ Gerencia infraestrutura automaticamente
✅ Auto-scaling
✅ 12 meses gratuito (t3.micro)
✅ Integração com RDS (PostgreSQL gerenciado)
✅ CI/CD integrado

### Setup:

#### 1. Instale o EB CLI
```bash
pip install awsebcli --upgrade --user
```

#### 2. Configure AWS Credentials
```bash
aws configure
# Insira:
# AWS Access Key ID: [sua-key]
# AWS Secret Access Key: [sua-secret]
# Default region: us-east-1 (ou sa-east-1 para Brasil)
# Default output: json
```

#### 3. Initialize EB
```bash
cd c:\Users\User\Documents\api\server
eb init -p python-3.11 pastita-api --region sa-east-1
```

#### 4. Create Environment
```bash
eb create pastita-production --instance-type t3.micro --database
```

#### 5. Deploy
```bash
eb deploy
```

#### 6. Abra a aplicação
```bash
eb open
```

---

## 🖥️ Opção 2: AWS EC2 (Mais Controle)

### Setup:

#### 1. Crie uma Instância EC2
- AMI: Ubuntu 22.04 LTS
- Tipo: t3.micro (free tier)
- Região: sa-east-1 (São Paulo)
- Security Group: Abra portas 22 (SSH), 80 (HTTP), 443 (HTTPS)

#### 2. Conecte via SSH
```bash
ssh -i seu-key.pem ubuntu@seu-ip-publico
```

#### 3. Configure a Máquina
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3-pip python3-venv postgresql-client git

# Clone seu projeto
git clone https://github.com/caiogn-dev/server.git
cd server

# Create venv
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt

# Set environment variables
nano .env
# (Copie o conteúdo do seu .env local)

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput
```

#### 4. Configure Gunicorn
```bash
# Install gunicorn (já está em requirements.txt)
pip install gunicorn

# Teste
gunicorn --bind 0.0.0.0:8000 server.wsgi
```

#### 5. Configure Nginx como Reverse Proxy
```bash
sudo apt install -y nginx

# Create config file
sudo nano /etc/nginx/sites-available/pastita

# Adicione:
```

```nginx
server {
    listen 80;
    server_name seu-dominio.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /home/ubuntu/server/staticfiles/;
    }

    location /media/ {
        alias /home/ubuntu/server/media/;
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/pastita /etc/nginx/sites-enabled/

# Test
sudo nginx -t

# Restart nginx
sudo systemctl restart nginx
```

#### 6. Configure Systemd para Auto-start Gunicorn
```bash
sudo nano /etc/systemd/system/pastita.service
```

```ini
[Unit]
Description=Pastita Django API
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/server
ExecStart=/home/ubuntu/server/venv/bin/gunicorn --bind 127.0.0.1:8000 --workers 4 server.wsgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# Enable e start
sudo systemctl enable pastita
sudo systemctl start pastita

# Check status
sudo systemctl status pastita
```

#### 7. HTTPS com Let's Encrypt
```bash
sudo apt install -y certbot python3-certbot-nginx

sudo certbot --nginx -d seu-dominio.com
```

---

## 📊 Comparison

| Feature | EB | EC2 |
|---------|----|----|
| Setup | 5 min | 30 min |
| Gerenciamento | Automático | Manual |
| Auto-scaling | ✅ Sim | ❌ Não |
| Custo | $0 (free tier) | $0 (free tier t3.micro) |
| Controle | Limitado | Total |
| Recomendado para | Produção | Dev/Learning |

---

## 🔐 Variáveis de Ambiente no AWS

### Elastic Beanstalk
```bash
eb setenv DEBUG=False
eb setenv DB_ENGINE=django.db.backends.postgresql
eb setenv DB_NAME=pastita
eb setenv DB_USER=postgres
eb setenv DB_PASSWORD=SuaSenha123
eb setenv DB_HOST=seu-rds-endpoint.rds.amazonaws.com
eb setenv MERCADO_PAGO_ACCESS_TOKEN=seu-token
```

### EC2
Edite `/home/ubuntu/server/.env` ou adicione ao `/etc/systemd/system/pastita.service`

---

## 🧪 Teste a Aplicação

```bash
# Local
curl http://localhost:8000/api/

# Production (após deploy)
curl https://seu-dominio.com/api/
```

---

## 📝 Próximos Passos

1. Configure domínio (Route 53 ou seu registrador)
2. Setup SSL (Let's Encrypt)
3. Configure backups do banco de dados
4. Setup monitoramento (CloudWatch)
5. Configure CI/CD (GitHub Actions → AWS)

---

**Qual opção você prefere?** 
- Elastic Beanstalk (mais fácil, recomendado)
- EC2 (mais controle)
