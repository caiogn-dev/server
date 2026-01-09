# WhatsApp Business Platform

Plataforma completa para integração com a API oficial do WhatsApp Business da Meta, desenvolvida em Django com arquitetura API-first.

## 📋 Índice

- [Arquitetura](#arquitetura)
- [Funcionalidades](#funcionalidades)
- [Instalação](#instalação)
- [Configuração](#configuração)
- [Endpoints da API](#endpoints-da-api)
- [Webhooks](#webhooks)
- [Integração com Langflow](#integração-com-langflow)
- [Fluxo de Pedidos](#fluxo-de-pedidos)

## 🏗️ Arquitetura

```
whatsapp_business/
├── config/                    # Configurações do projeto Django
│   ├── settings/
│   │   ├── base.py           # Configurações base
│   │   ├── development.py    # Configurações de desenvolvimento
│   │   └── production.py     # Configurações de produção
│   ├── urls.py               # URLs principais
│   ├── celery.py             # Configuração do Celery
│   └── wsgi.py
├── apps/
│   ├── core/                 # App base com utilitários
│   │   ├── models.py         # Modelos base
│   │   ├── exceptions.py     # Exceções customizadas
│   │   ├── middleware.py     # Middlewares (logging, rate limiting)
│   │   └── utils.py          # Utilitários
│   ├── whatsapp/             # Integração WhatsApp
│   │   ├── models.py         # WhatsAppAccount, Message, WebhookEvent
│   │   ├── services/         # WhatsAppAPIService, MessageService
│   │   ├── repositories/     # Repositórios de dados
│   │   ├── api/              # ViewSets e Serializers
│   │   ├── webhooks/         # Webhook handlers
│   │   └── tasks/            # Celery tasks
│   ├── conversations/        # Gerenciamento de conversas
│   ├── orders/               # Fluxo de pedidos
│   ├── payments/             # Integração pagamentos
│   └── langflow/             # Integração LLM/Langflow
└── manage.py
```

### Padrões Arquiteturais

- **Services**: Lógica de negócio encapsulada
- **Repositories**: Abstração de acesso a dados
- **Domain/Use Cases**: Casos de uso do domínio
- **Event-driven**: Processamento assíncrono com Celery

## ✨ Funcionalidades

### WhatsApp Business API
- ✅ Envio de mensagens de texto
- ✅ Envio de templates aprovados
- ✅ Mensagens interativas (botões e listas)
- ✅ Envio de mídia (imagens, documentos)
- ✅ Recebimento de mensagens via webhook
- ✅ Status de mensagens (sent, delivered, read, failed)
- ✅ Múltiplos números de WhatsApp

### Gerenciamento de Números
- ✅ Cadastro de múltiplos números
- ✅ Isolamento seguro de tokens (criptografia)
- ✅ Controle de ativação/desativação
- ✅ Rotação de tokens

### Automação com Langflow
- ✅ Integração com Langflow para LLM
- ✅ Processamento automático de mensagens
- ✅ Sessões de conversa com contexto
- ✅ Alternância entre atendimento humano/automático

### Pedidos e Pagamentos
- ✅ Criação e gerenciamento de pedidos
- ✅ Fluxo completo de status
- ✅ Integração com gateways de pagamento
- ✅ Webhooks de pagamento
- ✅ Notificações automáticas

## 🚀 Instalação

### Requisitos
- Python 3.11+
- PostgreSQL 15+ (ou SQLite para desenvolvimento)
- Redis 7+

### Desenvolvimento Local

```bash
# Clone o repositório
cd whatsapp_business

# Crie um ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows

# Instale as dependências
pip install -r requirements.txt

# Configure as variáveis de ambiente
cp .env.example .env
# Edite o arquivo .env com suas configurações

# Execute as migrações
python manage.py migrate

# Crie um superusuário
python manage.py createsuperuser

# Inicie o servidor
python manage.py runserver
```

### Docker

```bash
# Build e start
docker-compose up -d

# Migrações
docker-compose exec web python manage.py migrate

# Criar superusuário
docker-compose exec web python manage.py createsuperuser
```

## ⚙️ Configuração

### Variáveis de Ambiente

```env
# Django
DJANGO_SECRET_KEY=your-secret-key
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DB_NAME=whatsapp_business
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432

# Redis/Celery
REDIS_URL=redis://localhost:6379/1
CELERY_BROKER_URL=redis://localhost:6379/0

# WhatsApp Business API
WHATSAPP_API_VERSION=v18.0
WHATSAPP_WEBHOOK_VERIFY_TOKEN=your-verify-token
WHATSAPP_APP_SECRET=your-app-secret

# Langflow
LANGFLOW_API_URL=http://localhost:7860
LANGFLOW_API_KEY=your-langflow-api-key
```

## 📡 Endpoints da API

### Autenticação
A API usa Token Authentication. Inclua o header:
```
Authorization: Token <your-token>
```

### WhatsApp Accounts

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/api/v1/whatsapp/accounts/` | Listar contas |
| POST | `/api/v1/whatsapp/accounts/` | Criar conta |
| GET | `/api/v1/whatsapp/accounts/{id}/` | Detalhes da conta |
| PUT | `/api/v1/whatsapp/accounts/{id}/` | Atualizar conta |
| DELETE | `/api/v1/whatsapp/accounts/{id}/` | Remover conta |
| POST | `/api/v1/whatsapp/accounts/{id}/activate/` | Ativar conta |
| POST | `/api/v1/whatsapp/accounts/{id}/deactivate/` | Desativar conta |
| POST | `/api/v1/whatsapp/accounts/{id}/rotate_token/` | Rotacionar token |
| POST | `/api/v1/whatsapp/accounts/{id}/sync_templates/` | Sincronizar templates |

### Messages

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/api/v1/whatsapp/messages/` | Listar mensagens |
| GET | `/api/v1/whatsapp/messages/{id}/` | Detalhes da mensagem |
| POST | `/api/v1/whatsapp/messages/send_text/` | Enviar texto |
| POST | `/api/v1/whatsapp/messages/send_template/` | Enviar template |
| POST | `/api/v1/whatsapp/messages/send_interactive_buttons/` | Enviar botões |
| POST | `/api/v1/whatsapp/messages/send_interactive_list/` | Enviar lista |
| POST | `/api/v1/whatsapp/messages/send_image/` | Enviar imagem |
| POST | `/api/v1/whatsapp/messages/send_document/` | Enviar documento |
| POST | `/api/v1/whatsapp/messages/mark_as_read/` | Marcar como lida |
| POST | `/api/v1/whatsapp/messages/conversation_history/` | Histórico |
| POST | `/api/v1/whatsapp/messages/stats/` | Estatísticas |

### Conversations

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/api/v1/conversations/` | Listar conversas |
| GET | `/api/v1/conversations/{id}/` | Detalhes |
| POST | `/api/v1/conversations/{id}/switch_to_human/` | Modo humano |
| POST | `/api/v1/conversations/{id}/switch_to_auto/` | Modo automático |
| POST | `/api/v1/conversations/{id}/assign_agent/` | Atribuir agente |
| POST | `/api/v1/conversations/{id}/close/` | Fechar |
| POST | `/api/v1/conversations/{id}/resolve/` | Resolver |
| GET | `/api/v1/conversations/{id}/notes/` | Listar notas |
| POST | `/api/v1/conversations/{id}/add_note/` | Adicionar nota |

### Orders

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/api/v1/orders/` | Listar pedidos |
| POST | `/api/v1/orders/` | Criar pedido |
| GET | `/api/v1/orders/{id}/` | Detalhes |
| POST | `/api/v1/orders/{id}/confirm/` | Confirmar |
| POST | `/api/v1/orders/{id}/awaiting_payment/` | Aguardando pagamento |
| POST | `/api/v1/orders/{id}/mark_paid/` | Marcar como pago |
| POST | `/api/v1/orders/{id}/ship/` | Enviar |
| POST | `/api/v1/orders/{id}/deliver/` | Entregar |
| POST | `/api/v1/orders/{id}/cancel/` | Cancelar |
| GET | `/api/v1/orders/{id}/events/` | Eventos |
| GET | `/api/v1/orders/stats/` | Estatísticas |

### Payments

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/api/v1/payments/` | Listar pagamentos |
| POST | `/api/v1/payments/` | Criar pagamento |
| POST | `/api/v1/payments/{id}/process/` | Processar |
| POST | `/api/v1/payments/{id}/confirm/` | Confirmar |
| POST | `/api/v1/payments/{id}/fail/` | Falhar |
| POST | `/api/v1/payments/{id}/cancel/` | Cancelar |
| POST | `/api/v1/payments/{id}/refund/` | Reembolsar |

### Langflow

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/api/v1/langflow/flows/` | Listar flows |
| POST | `/api/v1/langflow/flows/` | Criar flow |
| POST | `/api/v1/langflow/flows/process/` | Processar mensagem |
| GET | `/api/v1/langflow/flows/{id}/stats/` | Estatísticas |
| GET | `/api/v1/langflow/sessions/` | Listar sessões |
| GET | `/api/v1/langflow/sessions/{id}/history/` | Histórico |

## 🔗 Webhooks

### WhatsApp Webhook

Configure no Meta Developer Portal:
```
URL: https://your-domain.com/webhooks/whatsapp/
Verify Token: (configurado em WHATSAPP_WEBHOOK_VERIFY_TOKEN)
```

O webhook recebe:
- Mensagens de texto
- Mensagens interativas
- Status de mensagens
- Erros

### Payment Webhooks

```
URL: https://your-domain.com/webhooks/payments/{gateway_id}/
```

Suporta:
- Stripe
- Mercado Pago
- PagSeguro
- PIX
- Custom

## 🤖 Integração com Langflow

### Configuração

1. Crie um flow no Langflow
2. Registre o flow na API:

```json
POST /api/v1/langflow/flows/
{
    "name": "Atendimento Automático",
    "flow_id": "seu-flow-id-do-langflow",
    "endpoint_url": "http://langflow:7860/api/v1/run/seu-flow-id",
    "status": "active",
    "input_type": "chat",
    "output_type": "chat"
}
```

3. Associe o flow a uma conta WhatsApp:

```json
POST /api/v1/langflow/flows/{id}/assign_accounts/
{
    "account_ids": ["uuid-da-conta"]
}
```

4. Configure a conta para usar o flow:

```json
PATCH /api/v1/whatsapp/accounts/{id}/
{
    "default_langflow_flow_id": "uuid-do-flow",
    "auto_response_enabled": true
}
```

### Processamento Manual

```json
POST /api/v1/langflow/flows/process/
{
    "flow_id": "uuid-do-flow",
    "message": "Olá, preciso de ajuda",
    "context": {
        "customer_name": "João"
    }
}
```

## 📦 Fluxo de Pedidos

```
PENDING → CONFIRMED → AWAITING_PAYMENT → PAID → SHIPPED → DELIVERED
                                    ↓
                               CANCELLED
```

### Criar Pedido

```json
POST /api/v1/orders/
{
    "account_id": "uuid-da-conta",
    "customer_phone": "5511999999999",
    "customer_name": "João Silva",
    "items": [
        {
            "product_name": "Produto A",
            "quantity": 2,
            "unit_price": 99.90
        }
    ],
    "shipping_address": {
        "street": "Rua Exemplo",
        "number": "123",
        "city": "São Paulo",
        "state": "SP",
        "zip_code": "01234-567"
    }
}
```

## 📊 Documentação da API

Acesse a documentação interativa:
- Swagger UI: `/api/docs/`
- ReDoc: `/api/redoc/`
- OpenAPI Schema: `/api/schema/`

## 🔒 Segurança

- Validação de assinatura dos webhooks da Meta
- Criptografia de tokens de acesso
- Rate limiting configurável
- Logging estruturado
- Proteção CORS

## 📝 Licença

MIT License
