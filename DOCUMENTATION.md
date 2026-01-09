# 📚 Documentação Completa - WhatsApp Business Platform API

## Índice

1. [Introdução](#1-introdução)
2. [Pré-requisitos](#2-pré-requisitos)
3. [Instalação Passo a Passo](#3-instalação-passo-a-passo)
4. [Configuração do Meta Developer Portal](#4-configuração-do-meta-developer-portal)
5. [Configuração da Aplicação](#5-configuração-da-aplicação)
6. [Autenticação na API](#6-autenticação-na-api)
7. [Gerenciamento de Contas WhatsApp](#7-gerenciamento-de-contas-whatsapp)
8. [Envio de Mensagens](#8-envio-de-mensagens)
9. [Recebimento de Mensagens (Webhooks)](#9-recebimento-de-mensagens-webhooks)
10. [Gerenciamento de Conversas](#10-gerenciamento-de-conversas)
11. [Integração com Langflow (LLM)](#11-integração-com-langflow-llm)
12. [Sistema de Pedidos](#12-sistema-de-pedidos)
13. [Sistema de Pagamentos](#13-sistema-de-pagamentos)
14. [Exemplos de Integração](#14-exemplos-de-integração)
15. [Troubleshooting](#15-troubleshooting)

---

## 1. Introdução

A **WhatsApp Business Platform API** é uma solução completa para integração com a API oficial do WhatsApp Business da Meta. Esta plataforma permite:

- ✅ Enviar e receber mensagens via WhatsApp
- ✅ Gerenciar múltiplos números de WhatsApp
- ✅ Automatizar conversas com LLM (Langflow)
- ✅ Gerenciar pedidos e pagamentos
- ✅ Processar webhooks de forma idempotente

### Arquitetura da Solução

```
┌─────────────────────────────────────────────────────────────────┐
│                        SUA APLICAÇÃO                             │
│  (Frontend, Mobile App, Sistema ERP, CRM, etc.)                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              WHATSAPP BUSINESS PLATFORM API                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  WhatsApp   │  │   Orders    │  │  Langflow   │              │
│  │    API      │  │    API      │  │    API      │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    META WHATSAPP CLOUD API                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Pré-requisitos

### 2.1 Requisitos de Sistema

| Componente | Versão Mínima | Recomendado |
|------------|---------------|-------------|
| Python | 3.10 | 3.11+ |
| PostgreSQL | 13 | 15+ |
| Redis | 6 | 7+ |
| RAM | 2GB | 4GB+ |
| Disco | 10GB | 20GB+ |

### 2.2 Requisitos do Meta

Antes de começar, você precisa ter:

1. **Conta Meta Business** verificada
2. **App criado** no Meta Developer Portal
3. **WhatsApp Business Account (WABA)** configurado
4. **Phone Number ID** do número de WhatsApp
5. **Access Token** permanente ou de longa duração
6. **App Secret** para validação de webhooks

### 2.3 Informações Necessárias

Anote as seguintes informações do seu app Meta:

```
WABA_ID: ___________________
PHONE_NUMBER_ID: ___________________
ACCESS_TOKEN: ___________________
APP_SECRET: ___________________
VERIFY_TOKEN: ___________________ (você define)
```

---

## 3. Instalação Passo a Passo

### 3.1 Instalação Local (Desenvolvimento)

```bash
# 1. Clone ou extraia o projeto
cd whatsapp_business

# 2. Crie um ambiente virtual
python -m venv venv

# 3. Ative o ambiente virtual
# Linux/Mac:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# 4. Instale as dependências
pip install -r requirements.txt

# 5. Copie o arquivo de configuração
cp .env.example .env

# 6. Edite o arquivo .env com suas configurações
nano .env  # ou use seu editor preferido

# 7. Execute as migrações do banco de dados
python manage.py migrate

# 8. Crie um superusuário para o admin
python manage.py createsuperuser

# 9. Inicie o servidor de desenvolvimento
python manage.py runserver 0.0.0.0:8000
```

### 3.2 Instalação com Docker (Produção)

```bash
# 1. Configure as variáveis de ambiente
cp .env.example .env
nano .env

# 2. Build e inicie os containers
docker-compose up -d

# 3. Execute as migrações
docker-compose exec web python manage.py migrate

# 4. Crie o superusuário
docker-compose exec web python manage.py createsuperuser

# 5. Verifique os logs
docker-compose logs -f
```

### 3.3 Iniciando o Celery (Processamento Assíncrono)

```bash
# Terminal 1 - Worker
celery -A config.celery worker -l info -Q whatsapp,orders,payments,langflow

# Terminal 2 - Beat (tarefas agendadas)
celery -A config.celery beat -l info
```

---

## 4. Configuração do Meta Developer Portal

### 4.1 Configurando o Webhook

1. Acesse o [Meta Developer Portal](https://developers.facebook.com/)
2. Selecione seu App
3. Vá em **WhatsApp** > **Configuration**
4. Em **Webhook**, clique em **Edit**
5. Configure:
   - **Callback URL**: `https://seu-dominio.com/webhooks/whatsapp/`
   - **Verify Token**: O mesmo valor de `WHATSAPP_WEBHOOK_VERIFY_TOKEN` no seu `.env`
6. Clique em **Verify and Save**
7. Inscreva-se nos campos:
   - `messages`
   - `message_deliveries`
   - `message_reads`

### 4.2 Obtendo Token Permanente

1. No Meta Developer Portal, vá em **WhatsApp** > **API Setup**
2. Clique em **Generate Access Token**
3. Para token permanente, use o System User:
   - Vá em **Business Settings** > **System Users**
   - Crie um System User com permissão de Admin
   - Gere um token com as permissões:
     - `whatsapp_business_management`
     - `whatsapp_business_messaging`

---

## 5. Configuração da Aplicação

### 5.1 Arquivo .env Completo

```env
# ===========================================
# DJANGO SETTINGS
# ===========================================
DJANGO_SECRET_KEY=sua-chave-secreta-muito-longa-e-aleatoria
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=seu-dominio.com,www.seu-dominio.com

# ===========================================
# DATABASE (PostgreSQL)
# ===========================================
DB_NAME=whatsapp_business
DB_USER=seu_usuario
DB_PASSWORD=sua_senha_segura
DB_HOST=localhost
DB_PORT=5432

# ===========================================
# REDIS / CELERY
# ===========================================
REDIS_URL=redis://localhost:6379/1
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# ===========================================
# WHATSAPP BUSINESS API (META)
# ===========================================
WHATSAPP_API_VERSION=v18.0
WHATSAPP_WEBHOOK_VERIFY_TOKEN=seu-token-de-verificacao-personalizado
WHATSAPP_APP_SECRET=seu-app-secret-do-meta

# ===========================================
# LANGFLOW (OPCIONAL)
# ===========================================
LANGFLOW_API_URL=http://localhost:7860
LANGFLOW_API_KEY=sua-api-key-do-langflow

# ===========================================
# RATE LIMITING
# ===========================================
RATE_LIMIT_ENABLED=True
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=60

# ===========================================
# CORS (Origens permitidas)
# ===========================================
CORS_ALLOWED_ORIGINS=https://seu-frontend.com,https://app.seu-dominio.com

# ===========================================
# SECURITY (Produção)
# ===========================================
SECURE_SSL_REDIRECT=True
```

---

## 6. Autenticação na API

### 6.1 Obtendo Token de Autenticação

A API usa **Token Authentication**. Para obter um token:

**Opção 1: Via Admin Django**
1. Acesse `https://seu-dominio.com/admin/`
2. Vá em **Auth Token** > **Tokens**
3. Clique em **Add Token**
4. Selecione o usuário e salve
5. Copie o token gerado

**Opção 2: Via Shell Django**
```bash
python manage.py shell
```
```python
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

user = User.objects.get(username='seu_usuario')
token, created = Token.objects.get_or_create(user=user)
print(f"Token: {token.key}")
```

### 6.2 Usando o Token nas Requisições

Inclua o header `Authorization` em todas as requisições:

```bash
curl -X GET "https://seu-dominio.com/api/v1/whatsapp/accounts/" \
  -H "Authorization: Token seu-token-aqui" \
  -H "Content-Type: application/json"
```

**Exemplo em Python:**
```python
import requests

API_URL = "https://seu-dominio.com/api/v1"
TOKEN = "seu-token-aqui"

headers = {
    "Authorization": f"Token {TOKEN}",
    "Content-Type": "application/json"
}

response = requests.get(f"{API_URL}/whatsapp/accounts/", headers=headers)
print(response.json())
```

**Exemplo em JavaScript:**
```javascript
const API_URL = "https://seu-dominio.com/api/v1";
const TOKEN = "seu-token-aqui";

fetch(`${API_URL}/whatsapp/accounts/`, {
    headers: {
        "Authorization": `Token ${TOKEN}`,
        "Content-Type": "application/json"
    }
})
.then(response => response.json())
.then(data => console.log(data));
```

---

## 7. Gerenciamento de Contas WhatsApp

### 7.1 Cadastrar uma Nova Conta

```bash
curl -X POST "https://seu-dominio.com/api/v1/whatsapp/accounts/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Minha Empresa",
    "phone_number_id": "123456789012345",
    "waba_id": "987654321098765",
    "phone_number": "5511999999999",
    "display_phone_number": "+55 11 99999-9999",
    "access_token": "EAAxxxxxxxxxxxxxxx",
    "webhook_verify_token": "meu-verify-token",
    "auto_response_enabled": true,
    "human_handoff_enabled": true
  }'
```

**Resposta:**
```json
{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Minha Empresa",
    "phone_number_id": "123456789012345",
    "waba_id": "987654321098765",
    "phone_number": "5511999999999",
    "display_phone_number": "+55 11 99999-9999",
    "status": "active",
    "token_version": 1,
    "auto_response_enabled": true,
    "human_handoff_enabled": true,
    "masked_token": "EAAx****xxxx",
    "created_at": "2024-01-15T10:30:00Z"
}
```

### 7.2 Listar Contas

```bash
curl -X GET "https://seu-dominio.com/api/v1/whatsapp/accounts/" \
  -H "Authorization: Token seu-token"
```

### 7.3 Ativar/Desativar Conta

```bash
# Desativar
curl -X POST "https://seu-dominio.com/api/v1/whatsapp/accounts/{id}/deactivate/" \
  -H "Authorization: Token seu-token"

# Ativar
curl -X POST "https://seu-dominio.com/api/v1/whatsapp/accounts/{id}/activate/" \
  -H "Authorization: Token seu-token"
```

### 7.4 Rotacionar Token de Acesso

```bash
curl -X POST "https://seu-dominio.com/api/v1/whatsapp/accounts/{id}/rotate_token/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "access_token": "novo-token-de-acesso"
  }'
```

### 7.5 Sincronizar Templates

```bash
curl -X POST "https://seu-dominio.com/api/v1/whatsapp/accounts/{id}/sync_templates/" \
  -H "Authorization: Token seu-token"
```

---

## 8. Envio de Mensagens

### 8.1 Enviar Mensagem de Texto

```bash
curl -X POST "https://seu-dominio.com/api/v1/whatsapp/messages/send_text/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "550e8400-e29b-41d4-a716-446655440000",
    "to": "5511988887777",
    "text": "Olá! Como posso ajudá-lo hoje?",
    "preview_url": false
  }'
```

**Resposta:**
```json
{
    "id": "msg-uuid-aqui",
    "whatsapp_message_id": "wamid.xxxxx",
    "direction": "outbound",
    "message_type": "text",
    "status": "sent",
    "from_number": "5511999999999",
    "to_number": "5511988887777",
    "text_body": "Olá! Como posso ajudá-lo hoje?",
    "sent_at": "2024-01-15T10:35:00Z"
}
```

### 8.2 Enviar Template

```bash
curl -X POST "https://seu-dominio.com/api/v1/whatsapp/messages/send_template/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "550e8400-e29b-41d4-a716-446655440000",
    "to": "5511988887777",
    "template_name": "hello_world",
    "language_code": "pt_BR",
    "components": [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": "João"}
            ]
        }
    ]
  }'
```

### 8.3 Enviar Botões Interativos

```bash
curl -X POST "https://seu-dominio.com/api/v1/whatsapp/messages/send_interactive_buttons/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "550e8400-e29b-41d4-a716-446655440000",
    "to": "5511988887777",
    "body_text": "Como você gostaria de prosseguir?",
    "buttons": [
        {"id": "btn_sim", "title": "Sim"},
        {"id": "btn_nao", "title": "Não"},
        {"id": "btn_ajuda", "title": "Preciso de ajuda"}
    ],
    "footer": "Escolha uma opção"
  }'
```

### 8.4 Enviar Lista Interativa

```bash
curl -X POST "https://seu-dominio.com/api/v1/whatsapp/messages/send_interactive_list/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "550e8400-e29b-41d4-a716-446655440000",
    "to": "5511988887777",
    "body_text": "Selecione um produto:",
    "button_text": "Ver Produtos",
    "sections": [
        {
            "title": "Eletrônicos",
            "rows": [
                {"id": "prod_1", "title": "Smartphone", "description": "R$ 1.999,00"},
                {"id": "prod_2", "title": "Notebook", "description": "R$ 3.499,00"}
            ]
        },
        {
            "title": "Acessórios",
            "rows": [
                {"id": "prod_3", "title": "Fone Bluetooth", "description": "R$ 199,00"},
                {"id": "prod_4", "title": "Carregador", "description": "R$ 89,00"}
            ]
        }
    ],
    "header": "🛒 Nossa Loja",
    "footer": "Preços sujeitos a alteração"
  }'
```

### 8.5 Enviar Imagem

```bash
curl -X POST "https://seu-dominio.com/api/v1/whatsapp/messages/send_image/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "550e8400-e29b-41d4-a716-446655440000",
    "to": "5511988887777",
    "image_url": "https://exemplo.com/imagem.jpg",
    "caption": "Confira nosso novo produto!"
  }'
```

### 8.6 Enviar Documento

```bash
curl -X POST "https://seu-dominio.com/api/v1/whatsapp/messages/send_document/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "550e8400-e29b-41d4-a716-446655440000",
    "to": "5511988887777",
    "document_url": "https://exemplo.com/catalogo.pdf",
    "filename": "Catalogo_2024.pdf",
    "caption": "Segue nosso catálogo atualizado"
  }'
```

### 8.7 Marcar Mensagem como Lida

```bash
curl -X POST "https://seu-dominio.com/api/v1/whatsapp/messages/mark_as_read/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "550e8400-e29b-41d4-a716-446655440000",
    "message_id": "wamid.xxxxx"
  }'
```

### 8.8 Obter Histórico de Conversa

```bash
curl -X POST "https://seu-dominio.com/api/v1/whatsapp/messages/conversation_history/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "550e8400-e29b-41d4-a716-446655440000",
    "phone_number": "5511988887777",
    "limit": 50
  }'
```

---

## 9. Recebimento de Mensagens (Webhooks)

### 9.1 Como Funciona

Quando um cliente envia uma mensagem para seu número WhatsApp:

1. A Meta envia um POST para `/webhooks/whatsapp/`
2. A API valida a assinatura do webhook
3. O evento é salvo no banco de dados
4. Uma task Celery processa a mensagem
5. Se configurado, o Langflow gera uma resposta automática

### 9.2 Estrutura do Webhook Recebido

```json
{
    "object": "whatsapp_business_account",
    "entry": [{
        "id": "WABA_ID",
        "changes": [{
            "value": {
                "messaging_product": "whatsapp",
                "metadata": {
                    "display_phone_number": "5511999999999",
                    "phone_number_id": "123456789"
                },
                "contacts": [{
                    "profile": {"name": "João Silva"},
                    "wa_id": "5511988887777"
                }],
                "messages": [{
                    "from": "5511988887777",
                    "id": "wamid.xxxxx",
                    "timestamp": "1673789012",
                    "type": "text",
                    "text": {"body": "Olá, preciso de ajuda"}
                }]
            },
            "field": "messages"
        }]
    }]
}
```

### 9.3 Consultando Mensagens Recebidas

```bash
# Listar todas as mensagens
curl -X GET "https://seu-dominio.com/api/v1/whatsapp/messages/?direction=inbound" \
  -H "Authorization: Token seu-token"

# Filtrar por conta
curl -X GET "https://seu-dominio.com/api/v1/whatsapp/messages/?account={account_id}&direction=inbound" \
  -H "Authorization: Token seu-token"
```

### 9.4 Consultando Status de Mensagens

```bash
# Mensagens enviadas
curl -X GET "https://seu-dominio.com/api/v1/whatsapp/messages/?direction=outbound&status=delivered" \
  -H "Authorization: Token seu-token"

# Mensagens com erro
curl -X GET "https://seu-dominio.com/api/v1/whatsapp/messages/?status=failed" \
  -H "Authorization: Token seu-token"
```

---

## 10. Gerenciamento de Conversas

### 10.1 Listar Conversas

```bash
curl -X GET "https://seu-dominio.com/api/v1/conversations/?account={account_id}" \
  -H "Authorization: Token seu-token"
```

### 10.2 Filtrar por Status

```bash
# Conversas abertas
curl -X GET "https://seu-dominio.com/api/v1/conversations/?status=open" \
  -H "Authorization: Token seu-token"

# Conversas em modo humano
curl -X GET "https://seu-dominio.com/api/v1/conversations/?mode=human" \
  -H "Authorization: Token seu-token"
```

### 10.3 Alternar para Atendimento Humano

```bash
curl -X POST "https://seu-dominio.com/api/v1/conversations/{id}/switch_to_human/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 1
  }'
```

### 10.4 Voltar para Atendimento Automático

```bash
curl -X POST "https://seu-dominio.com/api/v1/conversations/{id}/switch_to_auto/" \
  -H "Authorization: Token seu-token"
```

### 10.5 Atribuir Agente

```bash
curl -X POST "https://seu-dominio.com/api/v1/conversations/{id}/assign_agent/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 2
  }'
```

### 10.6 Adicionar Nota à Conversa

```bash
curl -X POST "https://seu-dominio.com/api/v1/conversations/{id}/add_note/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Cliente solicitou reembolso. Encaminhar para financeiro.",
    "is_internal": true
  }'
```

### 10.7 Fechar/Resolver Conversa

```bash
# Fechar
curl -X POST "https://seu-dominio.com/api/v1/conversations/{id}/close/" \
  -H "Authorization: Token seu-token"

# Resolver
curl -X POST "https://seu-dominio.com/api/v1/conversations/{id}/resolve/" \
  -H "Authorization: Token seu-token"

# Reabrir
curl -X POST "https://seu-dominio.com/api/v1/conversations/{id}/reopen/" \
  -H "Authorization: Token seu-token"
```

### 10.8 Adicionar Tags

```bash
curl -X POST "https://seu-dominio.com/api/v1/conversations/{id}/add_tag/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "tag": "vip"
  }'
```

---

## 11. Integração com Langflow (LLM)

### 11.1 Configurando o Langflow

1. **Instale o Langflow:**
```bash
pip install langflow
langflow run --host 0.0.0.0 --port 7860
```

2. **Crie um Flow no Langflow:**
   - Acesse `http://localhost:7860`
   - Crie um novo flow com componentes de chat
   - Salve e anote o Flow ID

### 11.2 Registrar Flow na API

```bash
curl -X POST "https://seu-dominio.com/api/v1/langflow/flows/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Atendimento Automático",
    "description": "Flow para atendimento ao cliente",
    "flow_id": "seu-flow-id-do-langflow",
    "endpoint_url": "http://langflow:7860/api/v1/run/seu-flow-id",
    "status": "active",
    "input_type": "chat",
    "output_type": "chat",
    "timeout_seconds": 30,
    "max_retries": 3,
    "default_context": {
        "empresa": "Minha Empresa",
        "horario_atendimento": "08:00 às 18:00"
    }
  }'
```

### 11.3 Associar Flow a Conta WhatsApp

```bash
# Associar
curl -X POST "https://seu-dominio.com/api/v1/langflow/flows/{flow_id}/assign_accounts/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "account_ids": ["account-uuid-1", "account-uuid-2"]
  }'
```

### 11.4 Configurar Conta para Usar o Flow

```bash
curl -X PATCH "https://seu-dominio.com/api/v1/whatsapp/accounts/{account_id}/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "default_langflow_flow_id": "flow-uuid",
    "auto_response_enabled": true
  }'
```

### 11.5 Processar Mensagem Manualmente

```bash
curl -X POST "https://seu-dominio.com/api/v1/langflow/flows/process/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "flow_id": "flow-uuid",
    "message": "Qual o horário de funcionamento?",
    "context": {
        "customer_name": "João",
        "customer_phone": "5511988887777"
    },
    "session_id": "session-opcional"
  }'
```

**Resposta:**
```json
{
    "response": "Olá João! Nosso horário de funcionamento é de 08:00 às 18:00, de segunda a sexta.",
    "session_id": "abc123",
    "flow_id": "flow-uuid"
}
```

### 11.6 Gerenciar Sessões

```bash
# Listar sessões
curl -X GET "https://seu-dominio.com/api/v1/langflow/sessions/" \
  -H "Authorization: Token seu-token"

# Ver histórico da sessão
curl -X GET "https://seu-dominio.com/api/v1/langflow/sessions/{id}/history/" \
  -H "Authorization: Token seu-token"

# Limpar histórico
curl -X POST "https://seu-dominio.com/api/v1/langflow/sessions/{id}/clear_history/" \
  -H "Authorization: Token seu-token"
```

---

## 12. Sistema de Pedidos

### 12.1 Criar Pedido

```bash
curl -X POST "https://seu-dominio.com/api/v1/orders/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "account-uuid",
    "customer_phone": "5511988887777",
    "customer_name": "João Silva",
    "customer_email": "joao@email.com",
    "items": [
        {
            "product_id": "SKU001",
            "product_name": "Smartphone XYZ",
            "product_sku": "SKU001",
            "quantity": 1,
            "unit_price": 1999.90
        },
        {
            "product_id": "SKU002",
            "product_name": "Capa Protetora",
            "quantity": 2,
            "unit_price": 49.90
        }
    ],
    "shipping_address": {
        "street": "Rua das Flores",
        "number": "123",
        "complement": "Apto 45",
        "neighborhood": "Centro",
        "city": "São Paulo",
        "state": "SP",
        "zip_code": "01234-567"
    },
    "notes": "Entregar no período da tarde"
  }'
```

**Resposta:**
```json
{
    "id": "order-uuid",
    "order_number": "ORD-20240115-ABC123",
    "status": "pending",
    "customer_phone": "5511988887777",
    "customer_name": "João Silva",
    "subtotal": "2099.70",
    "total": "2099.70",
    "items": [
        {
            "product_name": "Smartphone XYZ",
            "quantity": 1,
            "unit_price": "1999.90",
            "total_price": "1999.90"
        },
        {
            "product_name": "Capa Protetora",
            "quantity": 2,
            "unit_price": "49.90",
            "total_price": "99.80"
        }
    ],
    "created_at": "2024-01-15T14:30:00Z"
}
```

### 12.2 Fluxo de Status do Pedido

```
PENDING → CONFIRMED → AWAITING_PAYMENT → PAID → SHIPPED → DELIVERED
    ↓         ↓              ↓             ↓
CANCELLED  CANCELLED     CANCELLED     CANCELLED
```

### 12.3 Confirmar Pedido

```bash
curl -X POST "https://seu-dominio.com/api/v1/orders/{id}/confirm/" \
  -H "Authorization: Token seu-token"
```

### 12.4 Marcar Aguardando Pagamento

```bash
curl -X POST "https://seu-dominio.com/api/v1/orders/{id}/awaiting_payment/" \
  -H "Authorization: Token seu-token"
```

### 12.5 Marcar como Pago

```bash
curl -X POST "https://seu-dominio.com/api/v1/orders/{id}/mark_paid/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "payment_reference": "PAY-123456"
  }'
```

### 12.6 Enviar Pedido

```bash
curl -X POST "https://seu-dominio.com/api/v1/orders/{id}/ship/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "tracking_code": "BR123456789",
    "carrier": "Correios"
  }'
```

### 12.7 Marcar como Entregue

```bash
curl -X POST "https://seu-dominio.com/api/v1/orders/{id}/deliver/" \
  -H "Authorization: Token seu-token"
```

### 12.8 Cancelar Pedido

```bash
curl -X POST "https://seu-dominio.com/api/v1/orders/{id}/cancel/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "Cliente solicitou cancelamento"
  }'
```

### 12.9 Consultar Pedidos do Cliente

```bash
curl -X GET "https://seu-dominio.com/api/v1/orders/by_customer/?phone=5511988887777" \
  -H "Authorization: Token seu-token"
```

### 12.10 Estatísticas de Pedidos

```bash
curl -X GET "https://seu-dominio.com/api/v1/orders/stats/?account_id={account_id}" \
  -H "Authorization: Token seu-token"
```

---

## 13. Sistema de Pagamentos

### 13.1 Configurar Gateway de Pagamento

```bash
curl -X POST "https://seu-dominio.com/api/v1/payments/gateways/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Stripe Produção",
    "gateway_type": "stripe",
    "is_enabled": true,
    "is_sandbox": false,
    "configuration": {
        "currency": "BRL"
    }
  }'
```

### 13.2 Criar Pagamento

```bash
curl -X POST "https://seu-dominio.com/api/v1/payments/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "order-uuid",
    "amount": 2099.70,
    "gateway_id": "gateway-uuid",
    "payment_method": "pix",
    "payer_email": "joao@email.com",
    "payer_name": "João Silva",
    "payer_document": "123.456.789-00"
  }'
```

### 13.3 Processar Pagamento

```bash
curl -X POST "https://seu-dominio.com/api/v1/payments/{id}/process/" \
  -H "Authorization: Token seu-token"
```

### 13.4 Confirmar Pagamento (Manual)

```bash
curl -X POST "https://seu-dominio.com/api/v1/payments/{id}/confirm/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "external_id": "pi_xxxxx",
    "gateway_response": {
        "status": "succeeded"
    }
  }'
```

### 13.5 Webhook de Pagamento

Configure o webhook do gateway para:
```
URL: https://seu-dominio.com/webhooks/payments/{gateway_id}/
```

O sistema processa automaticamente:
- Stripe: `payment_intent.succeeded`, `payment_intent.payment_failed`
- Mercado Pago: `payment.created`, `payment.approved`
- PIX: Notificações de pagamento

### 13.6 Reembolsar Pagamento

```bash
curl -X POST "https://seu-dominio.com/api/v1/payments/{id}/refund/" \
  -H "Authorization: Token seu-token" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 100.00,
    "reason": "Produto com defeito"
  }'
```

---

## 14. Exemplos de Integração

### 14.1 Integração Python Completa

```python
import requests
from typing import Optional, Dict, Any

class WhatsAppBusinessClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip('/')
        self.headers = {
            "Authorization": f"Token {token}",
            "Content-Type": "application/json"
        }
    
    def _request(self, method: str, endpoint: str, data: Dict = None) -> Dict:
        url = f"{self.base_url}{endpoint}"
        response = requests.request(method, url, headers=self.headers, json=data)
        response.raise_for_status()
        return response.json()
    
    # WhatsApp Accounts
    def list_accounts(self) -> Dict:
        return self._request("GET", "/api/v1/whatsapp/accounts/")
    
    def create_account(self, data: Dict) -> Dict:
        return self._request("POST", "/api/v1/whatsapp/accounts/", data)
    
    # Messages
    def send_text(self, account_id: str, to: str, text: str) -> Dict:
        return self._request("POST", "/api/v1/whatsapp/messages/send_text/", {
            "account_id": account_id,
            "to": to,
            "text": text
        })
    
    def send_template(self, account_id: str, to: str, template_name: str, 
                      language: str = "pt_BR", components: list = None) -> Dict:
        return self._request("POST", "/api/v1/whatsapp/messages/send_template/", {
            "account_id": account_id,
            "to": to,
            "template_name": template_name,
            "language_code": language,
            "components": components or []
        })
    
    def send_buttons(self, account_id: str, to: str, body: str, 
                     buttons: list) -> Dict:
        return self._request("POST", "/api/v1/whatsapp/messages/send_interactive_buttons/", {
            "account_id": account_id,
            "to": to,
            "body_text": body,
            "buttons": buttons
        })
    
    def get_conversation_history(self, account_id: str, phone: str, 
                                  limit: int = 50) -> Dict:
        return self._request("POST", "/api/v1/whatsapp/messages/conversation_history/", {
            "account_id": account_id,
            "phone_number": phone,
            "limit": limit
        })
    
    # Conversations
    def list_conversations(self, account_id: str = None, 
                           status: str = None) -> Dict:
        params = []
        if account_id:
            params.append(f"account={account_id}")
        if status:
            params.append(f"status={status}")
        query = "?" + "&".join(params) if params else ""
        return self._request("GET", f"/api/v1/conversations/{query}")
    
    def switch_to_human(self, conversation_id: str, agent_id: int = None) -> Dict:
        data = {"agent_id": agent_id} if agent_id else {}
        return self._request("POST", 
            f"/api/v1/conversations/{conversation_id}/switch_to_human/", data)
    
    # Orders
    def create_order(self, account_id: str, customer_phone: str, 
                     items: list, **kwargs) -> Dict:
        data = {
            "account_id": account_id,
            "customer_phone": customer_phone,
            "items": items,
            **kwargs
        }
        return self._request("POST", "/api/v1/orders/", data)
    
    def confirm_order(self, order_id: str) -> Dict:
        return self._request("POST", f"/api/v1/orders/{order_id}/confirm/")
    
    def mark_order_paid(self, order_id: str, reference: str = "") -> Dict:
        return self._request("POST", f"/api/v1/orders/{order_id}/mark_paid/", {
            "payment_reference": reference
        })
    
    # Langflow
    def process_with_langflow(self, flow_id: str, message: str, 
                               context: Dict = None) -> Dict:
        return self._request("POST", "/api/v1/langflow/flows/process/", {
            "flow_id": flow_id,
            "message": message,
            "context": context or {}
        })


# Exemplo de uso
if __name__ == "__main__":
    client = WhatsAppBusinessClient(
        base_url="https://seu-dominio.com",
        token="seu-token-aqui"
    )
    
    # Listar contas
    accounts = client.list_accounts()
    print(f"Contas: {accounts}")
    
    # Enviar mensagem
    if accounts.get("results"):
        account_id = accounts["results"][0]["id"]
        
        # Texto simples
        result = client.send_text(
            account_id=account_id,
            to="5511988887777",
            text="Olá! Sua mensagem foi recebida."
        )
        print(f"Mensagem enviada: {result}")
        
        # Botões interativos
        result = client.send_buttons(
            account_id=account_id,
            to="5511988887777",
            body="Como posso ajudar?",
            buttons=[
                {"id": "suporte", "title": "Suporte"},
                {"id": "vendas", "title": "Vendas"},
                {"id": "outros", "title": "Outros"}
            ]
        )
        print(f"Botões enviados: {result}")
```

### 14.2 Integração JavaScript/Node.js

```javascript
const axios = require('axios');

class WhatsAppBusinessClient {
    constructor(baseUrl, token) {
        this.baseUrl = baseUrl.replace(/\/$/, '');
        this.headers = {
            'Authorization': `Token ${token}`,
            'Content-Type': 'application/json'
        };
    }

    async request(method, endpoint, data = null) {
        const url = `${this.baseUrl}${endpoint}`;
        const response = await axios({
            method,
            url,
            headers: this.headers,
            data
        });
        return response.data;
    }

    // WhatsApp Accounts
    async listAccounts() {
        return this.request('GET', '/api/v1/whatsapp/accounts/');
    }

    // Messages
    async sendText(accountId, to, text) {
        return this.request('POST', '/api/v1/whatsapp/messages/send_text/', {
            account_id: accountId,
            to,
            text
        });
    }

    async sendTemplate(accountId, to, templateName, languageCode = 'pt_BR', components = []) {
        return this.request('POST', '/api/v1/whatsapp/messages/send_template/', {
            account_id: accountId,
            to,
            template_name: templateName,
            language_code: languageCode,
            components
        });
    }

    async sendButtons(accountId, to, bodyText, buttons) {
        return this.request('POST', '/api/v1/whatsapp/messages/send_interactive_buttons/', {
            account_id: accountId,
            to,
            body_text: bodyText,
            buttons
        });
    }

    // Orders
    async createOrder(accountId, customerPhone, items, options = {}) {
        return this.request('POST', '/api/v1/orders/', {
            account_id: accountId,
            customer_phone: customerPhone,
            items,
            ...options
        });
    }

    async confirmOrder(orderId) {
        return this.request('POST', `/api/v1/orders/${orderId}/confirm/`);
    }

    // Langflow
    async processWithLangflow(flowId, message, context = {}) {
        return this.request('POST', '/api/v1/langflow/flows/process/', {
            flow_id: flowId,
            message,
            context
        });
    }
}

// Exemplo de uso
async function main() {
    const client = new WhatsAppBusinessClient(
        'https://seu-dominio.com',
        'seu-token-aqui'
    );

    try {
        // Listar contas
        const accounts = await client.listAccounts();
        console.log('Contas:', accounts);

        if (accounts.results && accounts.results.length > 0) {
            const accountId = accounts.results[0].id;

            // Enviar mensagem
            const result = await client.sendText(
                accountId,
                '5511988887777',
                'Olá! Mensagem enviada via Node.js'
            );
            console.log('Mensagem enviada:', result);
        }
    } catch (error) {
        console.error('Erro:', error.response?.data || error.message);
    }
}

main();
```

### 14.3 Webhook Handler (Flask)

```python
from flask import Flask, request, jsonify
import hmac
import hashlib

app = Flask(__name__)

WEBHOOK_SECRET = "seu-app-secret"

def verify_signature(payload, signature):
    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)

@app.route('/webhook/whatsapp', methods=['GET', 'POST'])
def whatsapp_webhook():
    if request.method == 'GET':
        # Verificação do webhook
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        
        if mode == 'subscribe' and token == 'seu-verify-token':
            return challenge, 200
        return 'Forbidden', 403
    
    # POST - Receber eventos
    signature = request.headers.get('X-Hub-Signature-256', '')
    
    if not verify_signature(request.data, signature):
        return 'Invalid signature', 401
    
    data = request.json
    
    # Processar eventos
    for entry in data.get('entry', []):
        for change in entry.get('changes', []):
            if change.get('field') == 'messages':
                value = change.get('value', {})
                
                # Mensagens recebidas
                for message in value.get('messages', []):
                    process_message(message, value.get('contacts', []))
                
                # Status de mensagens
                for status in value.get('statuses', []):
                    process_status(status)
    
    return jsonify({'status': 'ok'})

def process_message(message, contacts):
    from_number = message.get('from')
    message_type = message.get('type')
    
    if message_type == 'text':
        text = message.get('text', {}).get('body', '')
        print(f"Mensagem de {from_number}: {text}")
        
        # Aqui você pode chamar sua API para processar
        # ou responder diretamente
    
    elif message_type == 'interactive':
        interactive = message.get('interactive', {})
        if interactive.get('type') == 'button_reply':
            button_id = interactive.get('button_reply', {}).get('id')
            print(f"Botão clicado por {from_number}: {button_id}")

def process_status(status):
    message_id = status.get('id')
    status_type = status.get('status')
    print(f"Status da mensagem {message_id}: {status_type}")

if __name__ == '__main__':
    app.run(port=5000)
```

---

## 15. Troubleshooting

### 15.1 Problemas Comuns

#### Erro: "Webhook verification failed"
**Causa:** O verify token não corresponde.
**Solução:** Verifique se `WHATSAPP_WEBHOOK_VERIFY_TOKEN` no `.env` é igual ao configurado no Meta Developer Portal.

#### Erro: "Invalid signature"
**Causa:** O app secret está incorreto.
**Solução:** Verifique `WHATSAPP_APP_SECRET` no `.env`.

#### Erro: "WhatsApp account not found"
**Causa:** O `phone_number_id` não está cadastrado.
**Solução:** Cadastre a conta via API ou admin.

#### Erro: "Rate limit exceeded"
**Causa:** Muitas requisições em pouco tempo.
**Solução:** Aguarde ou ajuste `RATE_LIMIT_REQUESTS` no `.env`.

#### Mensagens não chegam
**Causas possíveis:**
1. Webhook não configurado corretamente
2. Celery não está rodando
3. Redis não está acessível

**Soluções:**
```bash
# Verificar Celery
celery -A config.celery inspect active

# Verificar Redis
redis-cli ping

# Verificar logs
tail -f logs/app.log
```

### 15.2 Logs e Debugging

```bash
# Ver logs da aplicação
tail -f logs/app.log

# Ver logs do Celery
celery -A config.celery worker -l debug

# Ver logs do Docker
docker-compose logs -f web
docker-compose logs -f celery
```

### 15.3 Verificar Saúde da API

```bash
# Health check
curl https://seu-dominio.com/api/v1/health/

# Resposta esperada:
# {"status":"healthy","checks":{"database":"ok","cache":"ok"}}
```

### 15.4 Contato e Suporte

Para dúvidas ou problemas:
1. Verifique os logs da aplicação
2. Consulte a documentação da API Meta
3. Verifique a documentação do Langflow

---

## Apêndice A: Referência Rápida de Endpoints

| Recurso | Método | Endpoint | Descrição |
|---------|--------|----------|-----------|
| Health | GET | `/api/v1/health/` | Status da API |
| Accounts | GET | `/api/v1/whatsapp/accounts/` | Listar contas |
| Accounts | POST | `/api/v1/whatsapp/accounts/` | Criar conta |
| Messages | POST | `/api/v1/whatsapp/messages/send_text/` | Enviar texto |
| Messages | POST | `/api/v1/whatsapp/messages/send_template/` | Enviar template |
| Messages | POST | `/api/v1/whatsapp/messages/send_interactive_buttons/` | Enviar botões |
| Messages | POST | `/api/v1/whatsapp/messages/send_interactive_list/` | Enviar lista |
| Conversations | GET | `/api/v1/conversations/` | Listar conversas |
| Conversations | POST | `/api/v1/conversations/{id}/switch_to_human/` | Modo humano |
| Orders | POST | `/api/v1/orders/` | Criar pedido |
| Orders | POST | `/api/v1/orders/{id}/confirm/` | Confirmar |
| Orders | POST | `/api/v1/orders/{id}/mark_paid/` | Marcar pago |
| Langflow | POST | `/api/v1/langflow/flows/process/` | Processar LLM |
| Webhook | POST | `/webhooks/whatsapp/` | Webhook Meta |
| Webhook | POST | `/webhooks/payments/{gateway_id}/` | Webhook pagamento |

---

## Apêndice B: Códigos de Status HTTP

| Código | Significado |
|--------|-------------|
| 200 | Sucesso |
| 201 | Criado com sucesso |
| 400 | Requisição inválida |
| 401 | Não autenticado |
| 403 | Sem permissão |
| 404 | Não encontrado |
| 429 | Rate limit excedido |
| 500 | Erro interno |
| 502 | Erro no serviço externo |

---

**Versão da Documentação:** 1.0.0  
**Última Atualização:** Janeiro 2024
