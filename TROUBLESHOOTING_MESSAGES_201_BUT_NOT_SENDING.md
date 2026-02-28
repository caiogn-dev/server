# Troubleshooting: API retorna 201 mas mensagem não chega

## Sintoma
- POST `/api/v1/whatsapp/messages/send_text/` retorna 201 Created
- Mensagem não chega no celular do cliente
- Não está recebendo mensagens de entrada

## Causas Prováveis

### 1. Celery Worker Não Está Rodando
**Por que:** A API cria a mensagem no banco (201), mas o Celery deveria processar o envio.

**Verificar:**
```bash
docker-compose ps | grep celery
docker-compose logs celery_worker --tail=50
```

**Solução:**
```bash
docker-compose up -d celery_worker celery_beat
docker-compose restart celery_worker
```

### 2. Mensagem Ficou em Status "pending"
**Por que:** Celery não processou a tarefa.

**Verificar:**
```bash
docker-compose exec web python manage.py shell -c"
from apps.whatsapp.models import Message
pending = Message.objects.filter(status='pending').count()
print(f'Mensagens pendentes: {pending}')
"
```

**Solução:** Reiniciar Celery ou processar manualmente.

### 3. Erro Silencioso no Envio
**Por que:** A mensagem é processada mas falha silenciosamente.

**Verificar:**
```bash
docker-compose logs celery_worker | grep -i error
docker-compose exec web python manage.py shell -c "
from apps.whatsapp.models import Message
failed = Message.objects.filter(status='failed')[:10]
for m in failed:
    print(f'{m.to_number}: {m.error_message}')
"
```

### 4. Conta WhatsApp Desconectada
**Por que:** A conta perdeu a conexão com a API do Meta.

**Verificar:**
```bash
docker-compose exec web python manage.py shell -c "
from apps.whatsapp.models import WhatsAppAccount
accounts = WhatsAppAccount.objects.all()
for acc in accounts:
    print(f'{acc.phone_number}:')
    print(f'  is_active={acc.is_active}')
    print(f'  is_connected={acc.is_connected}')
    print(f'  api_token={bool(acc.api_token)}')
    print(f'  phone_number_id={acc.phone_number_id}')
"
```

**Solução:** Reconectar conta no admin ou atualizar tokens.

### 5. Webhook Não Configurado (Recebimento)
**Por que:** Não recebe mensagens porque o webhook não está configurado.

**Verificar:**
- Acesse: https://developers.facebook.com/apps/
- Vá em WhatsApp > Configuration
- Verifique Webhook URL

**Deveria ser:**
```
https://backend.pastita.com.br/webhooks/whatsapp/
```

### 6. API Token Inválido ou Expirado
**Por que:** O token de acesso à API do WhatsApp expirou.

**Solução:**
1. Acesse: https://developers.facebook.com/
2. Vá em ferramentas > Tokens de Acesso
3. Gere novo token de acesso do sistema
4. Copie o token
5. Atualize no Django Admin:
   ```
   /admin/whatsapp/whatsappaccount/
   ```

## Passos para Diagnóstico Completo

### Passo 1: Verificar se Celery está processando
```bash
docker-compose exec redis redis-cli
LLEN celery
```

Se retornar > 0, há mensagens na fila aguardando processamento.

### Passo 2: Verificar se há mensagens failed
```bash
docker-compose exec web python manage.py shell -c "
from apps.whatsapp.models import Message
failed = Message.objects.filter(status='failed', created_at__gte=timezone.now() - timedelta(hours=24))
for m in failed:
    print(f'{m.to_number}: {m.error_message}')
"
```

### Passo 3: Testar envio manual
```bash
docker-compose exec web python manage.py shell -c "
from apps.whatsapp.services import MessageService
service = MessageService()
result = service.send_text_message(
    account_id='SUA_CONTA_ID',
    to='+5511999999999',
    text='Teste manual'
)
print(result)
"
```

## Soluções Comuns

### Restart em tudo
```bash
docker-compose down
docker-compose up -d
docker-compose logs -f celery_worker
```

### Limpar fila do Celery e reiniciar
```bash
docker-compose exec redis redis-cli FLUSHALL
docker-compose restart celery_worker
```

### Reprocessar mensagens pendentes
```bash
docker-compose exec web python manage.py shell -c "
from apps.whatsapp.tasks import send_message_async
from apps.whatsapp.models import Message

pending = Message.objects.filter(status='pending')
for msg in pending:
    send_message_async.delay(
        account_id=str(msg.account_id),
        to_number=msg.to_number,
        message_type='text',
        content={'text': msg.content}
    )
"
```

## Verifique Estes Logs

1. **Logs do Django:**
   ```bash
   docker-compose logs web --tail=200
   ```

2. **Logs do Celery Worker:**
   ```bash
   docker-compose logs celery_worker --tail=200
   ```

3. **Logs específicos de WhatsApp:**
   ```bash
   docker-compose exec web find /var/log -name "*whatsapp*" -type f 2>/dev/null | xargs tail -50
   ```

## Se Nada Funcionar

1. Verifique se a conta não foi bloqueada pelo Meta
2. Verifique limites de taxa (rate limits)
3. Teste com número diferente
4. Verifique se o número está no formato internacional (+55...)

## Execute Este Script

```bash
docker-compose exec web bash
bash /app/scripts/check_messages_not_sending.sh
```

Isso vai mostrar o status completo das mensagens.
