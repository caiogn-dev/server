#!/bin/bash
# Script para verificar por que mensagens não estão sendo enviadas
# Mesmo com API retornando 201

echo "=============================================="
echo "ANALISE: Mensagens criadas mas nao enviadas"
echo "=============================================="

# 1. Ver mensagens recentes e seus status
echo -e "\n1. STATUS DAS MENSAGENS (ultimas 10)"
echo "----------------------------------------------"
python manage.py shell -c "
from apps.whatsapp.models import Message
from django.utils import timezone
from datetime import timedelta

messages = Message.objects.filter(
    direction='outbound'
).order_by('-created_at')[:10]

print(f'{'ID':<10} | {'Status':<12} | {'Para':<20} | {'Criada em':<20}')
print('-' * 70)
for msg in messages:
    print(f'{msg.id:<10} | {msg.status:<12} | {str(msg.to_number):<20} | {msg.created_at.strftime(\"%Y-%m-%d %H:%M\")}')
    if msg.status == 'failed':
        print(f'           ERRO: {msg.error_message[:100] if msg.error_message else \"Sem erro\"}')
"

# 2. Ver mensagens pendentes
echo -e "\n2. MENSAGENS PENDENTES (nao processadas pelo Celery)"
echo "----------------------------------------------"
python manage.py shell -c "
from apps.whatsapp.models import Message
pending = Message.objects.filter(status='pending').order_by('-created_at')[:20]
print(f'Total pendentes: {pending.count()}')
for msg in pending[:10]:
    print(f'- {msg.to_number}: {msg.content[:50]}... ({msg.created_at})')
"

# 3. Verificar conta ativa
echo -e "\n3. CONTA WHATSAPP ATIVA"
echo "----------------------------------------------"
python manage.py shell -c "
from apps.whatsapp.models import WhatsAppAccount
accounts = WhatsAppAccount.objects.filter(is_active=True)
for acc in accounts:
    print(f'Conta: {acc.phone_number}')
    print(f'  API Token configurado: {bool(acc.api_token)}')
    print(f'  Phone Number ID: {acc.phone_number_id}')
    print(f'  Is Connected: {acc.is_connected}')
"

# 4. Verificar Celery
echo -e "\n4. STATUS DO CELERY"
echo "----------------------------------------------"
# Verificar se celery worker está rodando
ps aux | grep -E "celery.*worker" | grep -v grep || echo "Celery Worker: NAO ENCONTRADO"

# Verificar fila Redis
redis-cli -h redis LLEN celery 2>/dev/null || echo "Redis: Nao acessivel ou sem fila"

# 5. Teste de envio manual
echo -e "\n5. TESTAR ENVIO MANUAL"
echo "----------------------------------------------"
python manage.py shell -c "
from apps.whatsapp.services import MessageService
from apps.whatsapp.models import WhatsAppAccount, Message
from celery import current_app

# Verificar fila
inspector = current_app.control.inspect()
active_workers = inspector.active()
print(f'Workers ativos: {len(active_workers) if active_workers else 0}')

# Pegar primeira conta ativa
account = WhatsAppAccount.objects.filter(is_active=True).first()
if account:
    print(f'\\nConta encontrada: {account.phone_number}')
    print(f'Testando envio para: +5511999999999')
    
    try:
        service = MessageService()
        # Nao enviar de verdade, so verificar
        print('MessageService inicializado com sucesso')
    except Exception as e:
        print(f'Erro no MessageService: {e}')
else:
    print('NENHUMA CONTA ATIVA ENCONTRADA!')
"

# 6. Verificar logs recentes
echo -e "\n6. LOGS RECENTES (envio de mensagens)"
echo "----------------------------------------------"
tail -n 50 /var/log/django/pastita.log 2>/dev/null | grep -E "(send|message|celery)" | tail -20 || echo "Nao foi possivel acessar logs"

echo -e "\n=============================================="
echo "DIAGNOSTICO COMPLETO"
echo "=============================================="
