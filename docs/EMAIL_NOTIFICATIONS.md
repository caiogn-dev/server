# Sistema de Notificações por Email - Pastita

## Visão Geral

O sistema de notificações por email usa o **Resend API** para envio de emails e **Celery** para processamento assíncrono e tarefas agendadas.

## Variáveis de Ambiente Necessárias

```bash
# Resend API (obrigatório para emails)
RESEND_API_KEY=re_xxxxxxxxxxxx
RESEND_FROM_EMAIL=contato@pastita.com.br
RESEND_FROM_NAME=Pastita

# Celery/Redis (obrigatório para tarefas assíncronas)
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
REDIS_URL=redis://localhost:6379/0
```

## Triggers de Email Configurados

| Trigger | Descrição | Delay | Quando é Disparado |
|---------|-----------|-------|-------------------|
| `new_user` | Boas-vindas | Imediato | Registro de novo usuário |
| `order_confirmed` | Pedido confirmado | Imediato | Criação de pedido |
| `payment_confirmed` | Pagamento confirmado | Imediato | Pagamento aprovado |
| `order_shipped` | Saiu para entrega | Imediato | Status → SHIPPED |
| `order_delivered` | Pedido entregue | Imediato | Status → DELIVERED |
| `order_cancelled` | Pedido cancelado | Imediato | Status → CANCELLED |
| `cart_abandoned` | Carrinho abandonado | 30 min | Carrinho sem checkout |

## Fluxo de Disparo

### 1. Pedido Criado
```
checkout_service.create_order()
  └── trigger_order_email_automation(order, 'order_confirmed')
        └── email_automation_service.trigger()
              └── Envia email via Resend
```

### 2. Mudança de Status do Pedido
```
StoreOrder.update_status(new_status)
  └── _trigger_status_email_automation(new_status)
        └── trigger_order_email_automation(order, trigger_type)
              └── email_automation_service.trigger()
```

### 3. Carrinho Abandonado (Celery)
```
Celery Beat (a cada 5 min)
  └── check_abandoned_carts()
        └── send_abandoned_cart_notification.delay(session_id)
              └── AutomationService._send_notification()
```

## Iniciando o Celery

### Worker
```bash
cd /workspace/project/server
celery -A config.celery worker -l info -Q default,whatsapp,orders,payments,automation
```

### Beat (Scheduler)
```bash
cd /workspace/project/server
celery -A config.celery beat -l info
```

### Ambos juntos (desenvolvimento)
```bash
cd /workspace/project/server
celery -A config.celery worker -l info -B
```

## Tarefas Agendadas (Celery Beat)

| Tarefa | Intervalo | Descrição |
|--------|-----------|-----------|
| `check-abandoned-carts` | 5 min | Verifica carrinhos abandonados |
| `check-pending-pix-payments` | 10 min | Lembra pagamentos PIX pendentes |
| `cleanup-expired-sessions` | 24h | Limpa sessões expiradas |
| `process-scheduled-messages` | 1 min | Processa mensagens agendadas |

## Testando Manualmente

### Testar envio de email
```python
from apps.notifications.services import email_service

result = email_service.send_email(
    to='teste@email.com',
    subject='Teste',
    html='<h1>Teste</h1>'
)
print(result)
```

### Testar automação
```python
from apps.marketing.services.email_automation_service import email_automation_service

result = email_automation_service.trigger(
    store_id='6949125e-c340-4b86-9747-cee10f9e341f',
    trigger_type='order_confirmed',
    recipient_email='cliente@teste.com',
    recipient_name='Cliente Teste',
    context={
        'order_number': 'PAS123456',
        'order_total': '150.00'
    }
)
print(result)
```

## Personalização de Templates

Os templates suportam variáveis no formato `{{variavel}}`:

- `{{customer_name}}` - Nome completo do cliente
- `{{first_name}}` - Primeiro nome
- `{{email}}` - Email do cliente
- `{{order_number}}` - Número do pedido
- `{{order_total}}` - Total do pedido
- `{{store_name}}` - Nome da loja
- `{{tracking_code}}` - Código de rastreio (quando disponível)

## Logs

Os logs de automação são salvos em `EmailAutomationLog`:

```python
from apps.marketing.models import EmailAutomationLog

logs = EmailAutomationLog.objects.filter(
    automation__store_id='6949125e-c340-4b86-9747-cee10f9e341f'
).order_by('-created_at')[:10]

for log in logs:
    print(f"{log.recipient_email} - {log.status} - {log.sent_at}")
```

## Troubleshooting

### Emails não estão sendo enviados
1. Verificar se `RESEND_API_KEY` está configurado
2. Verificar logs: `EmailAutomationLog.objects.filter(status='failed')`
3. Verificar se a automação está ativa: `EmailAutomation.objects.filter(is_active=True)`

### Carrinho abandonado não dispara
1. Verificar se Celery está rodando
2. Verificar se `CompanyProfile.abandoned_cart_notification = True`
3. Verificar delay configurado (padrão: 30 min)

### Verificar status do Celery
```bash
celery -A config.celery inspect active
celery -A config.celery inspect scheduled
```
