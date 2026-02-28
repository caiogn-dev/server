# Guia de Diagnóstico de Mensagens WhatsApp

## Problema: Não está recebendo nem enviando mensagens

## Checklist de Verificação

### 1. Verificar Docker Containers
Execute no host:
```bash
docker-compose ps
```

Todos devem estar "Up":
- web (Django)
- db (PostgreSQL)
- redis (Redis)
- celery_worker
- celery_beat

### 2. Verificar Logs
```bash
# Logs do Django
docker-compose logs web --tail=100

# Logs do Celery Worker
docker-compose logs celery_worker --tail=100

# Logs específicos de WhatsApp
docker-compose exec web tail -f /var/log/whatsapp/*.log
```

### 3. Verificar Conta WhatsApp no Admin
Acesse: http://localhost:8000/admin/whatsapp/whatsappaccount/

Verifique para cada conta:
- ✅ Is Active: True
- ✅ Is Connected: True
- ✅ API Token: Preenchido
- ✅ Webhook Verify Token: Preenchido
- ✅ Phone Number ID: Correto

### 4. Verificar Configuração Webhook
No Meta Developer Dashboard:
- Acesse: https://developers.facebook.com/apps/
- Vá em WhatsApp > Configuration
- Webhook URL deve ser: `https://seu-dominio.com/webhooks/whatsapp/`
- Verify Token deve corresponder à configuração

### 5. Testar Webhook Localmente
```bash
# Dentro do container
docker-compose exec web bash
python manage.py shell -c "
from apps.whatsapp.services import WebhookService
service = WebhookService()
print('Webhook Service OK')
"
```

### 6. Verificar Automacao/Handlers
```bash
# No Django shell
docker-compose exec web python manage.py shell

from apps.automation.models import CompanyProfile
profiles = CompanyProfile.objects.all()
for p in profiles:
    print(f'Conta: {p.account}')
    print(f'Auto reply: {p.auto_reply_enabled}')
    print(f'Llm enabled: {getattr(p, \"llm_enabled\", None)}')
```

## Comandos Úteis

### Enviar mensagem de teste
```bash
docker-compose exec web python manage.py shell -c "
from apps.whatsapp.services import MessageService
service = MessageService()
service.send_text_message(
    account_id='sua-conta-id',
    to='+5511999999999',  # número de teste
    text='Teste manual'
)
"
```

### Verificar fila do Celery
```bash
docker-compose exec redis redis-cli
SELECT 0
KEYS *celery*
SMEMBERS celery
```

### Reiniciar containers
```bash
docker-compose restart
```

## Problemas Comuns

### 1. Celery não está processando tarefas
**Sintoma:** Mensagens ficam em "pending"
**Solução:**
```bash
docker-compose up -d celery_worker celery_beat
```

### 2. Webhook não recebendo eventos
**Sintoma:** Nenhuma mensagem chegando
**Solução:**
- Verificar URL do webhook no Meta Dashboard
- Verificar se o webhook está registrado: `docker-compose logs web | grep "webhook"`
- Testar manualmente com curl

### 3. Handlers/LLM respondendo automaticamente
**Sintoma:** Bot responde mesmo "desativado" 
**Causa:** `auto_reply_enabled=True` no CompanyProfile
**Solução:**
```python
# Desativar no Django shell
from apps.automation.models import CompanyProfile
profile = CompanyProfile.objects.first()
profile.auto_reply_enabled = False
profile.save()
```

### 4. Erro de autenticação
**Sintoma:** "Error sending message: 401"
**Solução:**
- Atualizar API Token no WhatsAppAccount
- Verificar permissões no Meta Dashboard

## Scripts de Diagnóstico

Execute dentro do container:
```bash
docker-compose exec web bash
./scripts/diagnose_whatsapp.py
```

Ou use o script acima deste arquivo.

## Próximos Passos

Se após estas verificações o problema persistir:
1. Colete os logs completos: `docker-compose logs > logs.txt`
2. Verifique o estado do banco de dados
3. Consulte a documentação oficial do WhatsApp Business API
