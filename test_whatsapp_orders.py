"""
Script para testar notificações WhatsApp ao criar e atualizar pedidos.
Execute com: python manage.py shell < test_whatsapp_orders.py
"""

from apps.stores.models import Store, StoreOrder
from apps.whatsapp.models import WhatsAppAccount
from decimal import Decimal
from datetime import datetime
import json

print("\n" + "="*80)
print("TESTE DE NOTIFICAÇÕES WHATSAPP - Pastita")
print("="*80 + "\n")

# ============================================================================
# TESTE 1: Verificar configuração de contas WhatsApp
# ============================================================================
print("📋 TESTE 1: Verificando contas WhatsApp configuradas...")
print("-" * 80)

accounts = WhatsAppAccount.objects.all()
print(f"Total de contas: {accounts.count()}\n")

if accounts.count() == 0:
    print("❌ FALHA: Nenhuma conta WhatsApp configurada!")
else:
    for i, acc in enumerate(accounts[:3], 1):
        phone_id = getattr(acc, 'phone_number_id', None)
        status = getattr(acc, 'status', 'unknown')
        store = getattr(acc, 'store', None)
        print(f"Conta {i}:")
        print(f"  ID: {acc.id}")
        print(f"  phone_number_id: {'✓' if phone_id else '❌'} {phone_id}")
        print(f"  status: {status}")
        print(f"  store: {store.slug if store else 'default'}")
        print()

# ============================================================================
# TESTE 2: Verificar lojas disponíveis
# ============================================================================
print("📋 TESTE 2: Verificando lojas disponíveis...")
print("-" * 80)

stores = Store.objects.all()
print(f"Total de lojas: {stores.count()}\n")

if stores.count() == 0:
    print("❌ FALHA: Nenhuma loja encontrada!")
else:
    for i, store in enumerate(stores[:3], 1):
        print(f"Loja {i}: {store.name} (slug: {store.slug})")

# ============================================================================
# TESTE 3: Criar e atualizar pedido com notificação
# ============================================================================
print("\n📋 TESTE 3: Criando pedido de teste e testando notificação...")
print("-" * 80)

# Obter primeira loja
store = Store.objects.first()
if not store:
    print("❌ FALHA: Sem loja para criar pedido!")
else:
    print(f"✓ Usando loja: {store.name}\n")
    
    # Criar pedido de teste
    order = StoreOrder.objects.create(
        store=store,
        customer_name="João Silva (TESTE)",
        customer_phone="5561987654321",  # Número de teste
        customer_email="teste@example.com",
        status=StoreOrder.OrderStatus.PENDING,
        total_amount=Decimal('99.99'),
    )
    print(f"✓ Pedido criado: {order.order_number} (ID: {order.id})")
    print(f"  Cliente: {order.customer_name}")
    print(f"  Telefone: {order.customer_phone}")
    print(f"  Status inicial: {order.status}\n")
    
    # Testar transição 1: PENDING → PROCESSING
    print("→ Testando transição: PENDING → PROCESSING com notificação...")
    order.update_status(StoreOrder.OrderStatus.PROCESSING, notify=True)
    order.refresh_from_db()
    
    notification_key_1 = 'whatsapp_notification_processing'
    notification_1 = order.metadata.get(notification_key_1)
    
    if notification_1:
        print(f"  ✓ Notificação registrada: {notification_1}\n")
    else:
        print(f"  ⚠ Notificação NÃO registrada (check logs para [WhatsAppNotification])\n")
    
    # Testar transição 2: PROCESSING → CONFIRMED
    print("→ Testando transição: PROCESSING → CONFIRMED com notificação...")
    order.update_status(StoreOrder.OrderStatus.CONFIRMED, notify=True)
    order.refresh_from_db()
    
    notification_key_2 = 'whatsapp_notification_confirmed'
    notification_2 = order.metadata.get(notification_key_2)
    
    if notification_2:
        print(f"  ✓ Notificação registrada: {notification_2}\n")
    else:
        print(f"  ⚠ Notificação NÃO registrada (check logs para [WhatsAppNotification])\n")
    
    # Exibir metadata final
    print("→ Metadata do pedido (flags de notificação):")
    notification_flags = {k: v for k, v in order.metadata.items() if 'notification' in k}
    print(f"  {json.dumps(notification_flags, indent=2)}\n")

# ============================================================================
# TESTE 4: Verificar logs gerados
# ============================================================================
print("="*80)
print("✓ TESTES CONCLUÍDOS!")
print("="*80)
print("\n📌 PRÓXIMAS AÇÕES:\n")
print("1. Abra outro terminal e veja os logs em tempo real:")
print("   $ tail -f server/logs/dev.log | grep '[WhatsAppNotification]'")
print("\n2. Procure por mensagens de sucesso ou erro:")
print("   - ✓ SUCCESS: '[WhatsAppNotification] ✓ Message sent successfully!'")
print("   - ❌ FAILURE: '[WhatsAppNotification] RETURN:' ou '[WhatsAppNotification] ✗ EXCEPTION:'")
print("\n3. Se a conta WhatsApp estiver correta, você verá:")
print("   - ✓ Phone normalization")
print("   - ✓ Account retrieved")
print("   - ✓ Message sent successfully")
print("\n" + "="*80 + "\n")
