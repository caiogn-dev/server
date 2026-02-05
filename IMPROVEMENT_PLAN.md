# 🔧 Server Backend - Plano de Melhorias

## 📊 Análise do Estado Atual

### ✅ Pontos Fortes
- Arquitetura multi-tenant bem definida
- Stores app como fonte única de verdade para e-commerce
- Messaging dispatcher unificado já implementado
- Webhooks centralizados com handlers
- Permissions bem definidas (`IsStoreOwner`, `IsStoreStaff`)
- Models divididos em módulos (stores/models/)

### ⚠️ Problemas Identificados

#### 1. **Arquivos de Views Muito Grandes**
| Arquivo | Linhas | Problema |
|---------|--------|----------|
| `stores/api/views.py` | 1570 | Monolítico, difícil manutenção |
| `automation/api/views.py` | 1216 | Muitos ViewSets em um arquivo |
| `marketing/api/views.py` | 909 | Lógica misturada |
| `instagram/api/views.py` | 650 | Poderia ser dividido |

**Solução**: Dividir em múltiplos arquivos por feature

#### 2. **Services Fragmentados por Canal**
```
apps/
├── whatsapp/services/message_service.py (608 linhas)
├── instagram/services/message_service.py (343 linhas)
├── automation/services/automation_service.py (858 linhas)
├── campaigns/services/campaign_service.py (474 linhas)
└── marketing/services/email_marketing_service.py (555 linhas)
```

**Problema**: Lógica de envio duplicada entre canais

**Solução**: Já existe `messaging/dispatcher.py` - migrar todos para usar ele

#### 3. **Inconsistência de Permissões**
- Algumas views usam `IsAuthenticated` sem filtro de store
- ✅ CORRIGIDO: automation views agora filtram por store/account

#### 4. **Apps Legados Ainda Referenciados**
- `orders` (legado) vs `stores.StoreOrder` (novo)
- `ecommerce` (legado) vs `stores.StoreProduct` (novo)
- `payments` (legado) vs `stores.StorePayment` (novo)

**Solução**: Criar migration script para remover referências

---

## 🛠️ Plano de Implementação

### Fase 1: Divisão de Views (P0)

#### 1.1 Estrutura Proposta para `stores/api/`
```
apps/stores/api/
├── __init__.py
├── views/
│   ├── __init__.py
│   ├── store_views.py      # StoreViewSet
│   ├── product_views.py    # ProductViewSet, CategoryViewSet
│   ├── order_views.py      # OrderViewSet
│   ├── cart_views.py       # CartViewSet
│   ├── coupon_views.py     # CouponViewSet
│   ├── delivery_views.py   # DeliveryZoneViewSet
│   └── payment_views.py    # PaymentViewSet (já existe)
├── serializers/
│   ├── __init__.py
│   ├── store_serializers.py
│   ├── product_serializers.py
│   ├── order_serializers.py
│   └── ...
└── filters.py
```

#### 1.2 Estrutura para `automation/api/`
```
apps/automation/api/
├── views/
│   ├── company_profile_views.py
│   ├── auto_message_views.py
│   ├── customer_session_views.py
│   ├── scheduled_message_views.py
│   └── report_views.py
└── serializers/
```

### Fase 2: Unificação de Messaging (P1)

#### 2.1 Migrar para Messaging Dispatcher
```python
# ANTES (disperso)
# whatsapp/services/message_service.py
def send_message(account, to, text):
    # Lógica WhatsApp específica
    pass

# instagram/services/message_service.py  
def send_dm(account, to, text):
    # Lógica Instagram específica
    pass

# DEPOIS (unificado)
# Usar messaging/dispatcher.py
from apps.messaging.dispatcher import MessageDispatcher

dispatcher = MessageDispatcher()
dispatcher.send_message(
    channel='whatsapp',  # ou 'instagram', 'email'
    recipient=phone,
    content={'text': text},
    store_id=store.id
)
```

#### 2.2 Adicionar Providers Faltantes
```python
# messaging/providers/
├── base.py           # BaseProvider (já existe)
├── whatsapp_provider.py  # ✅
├── email_provider.py     # ✅
├── instagram_provider.py # 🆕 CRIAR
└── sms_provider.py       # 🆕 FUTURO
```

### Fase 3: Cleanup de Apps Legados (P2)

#### 3.1 Script de Migração
```python
# management/commands/cleanup_legacy_apps.py

def handle(self):
    # 1. Verificar se há Orders legados
    from apps.orders.models import Order as LegacyOrder
    legacy_count = LegacyOrder.objects.count()
    
    if legacy_count > 0:
        # Migrar para StoreOrder
        self.migrate_orders()
    
    # 2. Remover do INSTALLED_APPS
    # 3. Remover migrations
```

#### 3.2 Atualizar INSTALLED_APPS
```python
# config/settings/base.py
INSTALLED_APPS = [
    # Core Django
    ...
    # Active Apps
    'apps.stores',
    'apps.whatsapp',
    'apps.messaging',
    'apps.automation',
    'apps.conversations',
    'apps.webhooks',
    'apps.agents',
    'apps.marketing',
    'apps.notifications',
    'apps.audit',
    
    # DEPRECATED - Remover após migração
    # 'apps.orders',    # → stores.StoreOrder
    # 'apps.ecommerce', # → stores.StoreProduct
    # 'apps.payments',  # → stores.StorePayment
]
```

### Fase 4: Otimizações de Performance (P2)

#### 4.1 Query Optimization
```python
# Usar select_related e prefetch_related consistentemente
class StoreOrderViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        return StoreOrder.objects.select_related(
            'store', 'customer'
        ).prefetch_related(
            'items', 'items__product'
        )
```

#### 4.2 Caching Strategy
```python
# Usar cache para dados que mudam pouco
from django.core.cache import cache

def get_store_settings(store_id):
    cache_key = f'store_settings_{store_id}'
    settings = cache.get(cache_key)
    
    if not settings:
        settings = StoreSettings.objects.get(store_id=store_id)
        cache.set(cache_key, settings, timeout=300)  # 5 min
    
    return settings
```

#### 4.3 Async Tasks
```python
# Mover operações pesadas para Celery
@shared_task
def process_bulk_messages(message_ids):
    messages = ScheduledMessage.objects.filter(id__in=message_ids)
    dispatcher = MessageDispatcher()
    
    for msg in messages:
        dispatcher.send_message(...)
```

---

## 📁 Estrutura Final Proposta

```
apps/
├── core/              # Base models, utils, permissions ✅
├── stores/            # E-commerce completo ✅
│   ├── models/        # Dividido em módulos ✅
│   ├── api/
│   │   ├── views/     # 🆕 Dividir
│   │   └── serializers/
│   └── services/
├── messaging/         # Dispatcher unificado ✅
│   ├── dispatcher.py
│   └── providers/
├── whatsapp/          # WhatsApp específico
├── instagram/         # Instagram específico
├── automation/        # Automação
│   ├── api/
│   │   └── views/     # 🆕 Dividir
│   └── services/
├── conversations/     # Chat management
├── webhooks/          # Webhooks centralizados ✅
├── agents/            # AI Agents (Langflow)
├── marketing/         # Email marketing
├── notifications/     # Push notifications
└── audit/             # Audit logs
```

---

## 🎯 Checklist de Implementação

### Imediato (Esta Sprint)
- [x] Adicionar filtro de ownership em automation views
- [ ] Dividir `stores/api/views.py` em módulos
- [ ] Dividir `automation/api/views.py` em módulos

### Próxima Sprint
- [ ] Criar Instagram provider para messaging
- [ ] Migrar campanhas WhatsApp para usar dispatcher
- [ ] Adicionar caching em endpoints frequentes

### Futuro
- [ ] Remover apps legados (orders, ecommerce, payments)
- [ ] Implementar API versioning (v2)
- [ ] Adicionar rate limiting por tenant

---

## 📊 Métricas de Sucesso

| Métrica | Atual | Meta |
|---------|-------|------|
| Maior arquivo de views | 1570 linhas | <300 linhas |
| Tempo médio de resposta | ~200ms | <100ms |
| Coverage de testes | ~30% | 70% |
| Duplicação de código | ~15% | <5% |

---

## 🔒 Segurança

### Já Implementado
- ✅ `IsStoreOwner` permission
- ✅ `IsStoreStaff` permission  
- ✅ `HasStoreAccess` permission
- ✅ Filtro de queryset por owner em automation views
- ✅ Webhook signature validation
- ✅ Token encryption para integrações

### A Implementar
- [ ] Rate limiting por tenant
- [ ] Audit log para operações sensíveis
- [ ] IP allowlist para webhooks
- [ ] 2FA para admin

---

## 🔗 Referências

- [Django REST Framework Best Practices](https://www.django-rest-framework.org/community/tutorials-and-resources/)
- [Two Scoops of Django](https://www.feldroy.com/books/two-scoops-of-django-3-x)
- [Django Channels](https://channels.readthedocs.io/)
- [Celery Best Practices](https://docs.celeryq.dev/en/stable/userguide/tasks.html#best-practices)
