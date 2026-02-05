# 🔧 Server Backend - Plano de Melhorias

## 📊 Análise do Estado Atual

### ✅ Pontos Fortes
- Arquitetura multi-tenant bem definida
- Stores app como fonte única de verdade para e-commerce
- Messaging dispatcher unificado já implementado
- Webhooks centralizados com handlers
- Permissions bem definidas (`IsStoreOwner`, `IsStoreStaff`)
- Models divididos em módulos (stores/models/)
- **NOVO**: Estrutura modular de views para stores (`stores/api/views/`)
- **NOVO**: Instagram Provider para messaging dispatcher
- **NOVO**: Backward compatibility mantida durante migração

### ⚠️ Problemas Identificados

#### 1. **Arquivos de Views Muito Grandes** 🔄 EM PROGRESSO
| Arquivo | Linhas | Status |
|---------|--------|--------|
| `stores/api/views.py` | 1570 | ✅ Estrutura modular criada em `views/` |
| `automation/api/views.py` | 1216 | ✅ Estrutura criada com backward compat |
| `marketing/api/views.py` | 909 | ⏳ Pendente |
| `instagram/api/views.py` | 650 | ⏳ Pendente |

#### 2. **Services Fragmentados por Canal** ✅ PARCIALMENTE RESOLVIDO
```
messaging/providers/
├── base.py               # ✅ Interface base
├── whatsapp_provider.py  # ✅ Implementado
├── email_provider.py     # ✅ Implementado
├── instagram_provider.py # ✅ NOVO - Implementado
└── sms_provider.py       # ⏳ Futuro
```

#### 3. **Inconsistência de Permissões** ✅ RESOLVIDO
- ✅ automation views filtram por store/account
- ✅ Permissions base criadas em `stores/api/views/base.py`

#### 4. **Apps Legados Ainda Referenciados** ⏳ PENDENTE
- `orders` (legado) vs `stores.StoreOrder` (novo)
- `ecommerce` (legado) vs `stores.StoreProduct` (novo)
- `payments` (legado) vs `stores.StorePayment` (novo)

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

### ✅ Completado (Sprint Atual)
- [x] Adicionar filtro de ownership em automation views
- [x] Criar estrutura modular para `stores/api/views/` (base, store_views, product_views, order_views, coupon_views, delivery_views)
- [x] Criar estrutura modular para `automation/api/views/` (base, com backward compatibility)
- [x] Criar Instagram provider para messaging (`messaging/providers/instagram_provider.py`)
- [x] Registrar Instagram provider no MessageDispatcher

### 🔄 Em Progresso (Próxima Sprint)
- [ ] Migrar views restantes de stores (Cart, Checkout, Wishlist, Catalog)
- [ ] Migrar campanhas WhatsApp para usar dispatcher
- [ ] Adicionar Redis caching em endpoints frequentes
- [ ] Completar migração modular de automation views

### 📋 Backlog (Próximas Sprints)

#### Sprint 3 - API Rate Limiting & Quotas
- [ ] **Rate Limiter**: Implementar throttling por tenant/endpoint
- [ ] **API Quotas**: Sistema de quotas por plano (free/pro/enterprise)
- [ ] **Usage Dashboard**: Endpoint para visualizar uso de API
- [ ] **Overage Alerts**: Notificações quando próximo do limite

#### Sprint 4 - Sistema de Pagamentos
- [ ] **PIX Integration**: Pagamento via PIX (EFI/Gerencianet)
- [ ] **Card Payments**: Integração Stripe/PagSeguro
- [ ] **Boleto**: Geração de boletos bancários
- [ ] **Split Payments**: Divisão automática de pagamentos
- [ ] **Refund System**: Sistema de estornos

#### Sprint 5 - Webhooks Avançados
- [ ] **Outbound Webhooks**: Sistema de webhooks de saída
- [ ] **Retry Logic**: Exponential backoff para falhas
- [ ] **Webhook Logs**: Histórico detalhado de entregas
- [ ] **Webhook Builder**: Interface para criar webhooks customizados

#### Sprint 6 - Sistema de Cache
- [ ] **Redis Cache**: Cache layer para queries frequentes
- [ ] **Cache Invalidation**: Invalidação automática por signals
- [ ] **Cache Warming**: Pré-carregamento de dados críticos
- [ ] **Cache Analytics**: Métricas de hit/miss

#### Sprint 7 - Audit & Compliance
- [ ] **Audit Logging**: Log de todas ações sensíveis
- [ ] **User Activity**: Trail de auditoria por usuário
- [ ] **Export Logs**: Export para compliance (CSV/JSON)
- [ ] **Data Retention**: Políticas de retenção configuráveis

#### Sprint 8 - Testes & Qualidade
- [ ] **Unit Tests**: Coverage mínimo de 80%
- [ ] **Integration Tests**: Testes de integração com DB
- [ ] **API Tests**: Testes automatizados de endpoints
- [ ] **Load Tests**: Testes de carga com Locust

### 🚀 Futuro (Roadmap)

#### Infraestrutura
- [ ] **GraphQL API**: API alternativa com subscriptions
- [ ] **Microservices**: Separar messaging em serviço próprio
- [ ] **Kubernetes**: Deploy em K8s com auto-scaling
- [ ] **Multi-region**: Suporte a múltiplas regiões

#### Integrações
- [ ] **iFood API**: Integração com marketplace
- [ ] **Rappi API**: Integração com marketplace
- [ ] **Correios API**: Cálculo de frete automático
- [ ] **NFe**: Emissão de notas fiscais

#### IA & Analytics
- [ ] **ML Pipeline**: Pipeline para treinar modelos
- [ ] **Recommendation Engine**: Recomendação de produtos
- [ ] **Anomaly Detection**: Detecção de fraudes
- [ ] **Predictive Analytics**: Previsão de vendas

---

## 🆕 Novas Features Planejadas

### 1. 💳 Sistema de Pagamentos Integrado
```python
# apps/payments/providers/
├── base.py           # Interface base
├── pix_provider.py   # PIX via EFI/Gerencianet
├── stripe_provider.py
├── pagseguro_provider.py
└── boleto_provider.py

# Fluxo de pagamento
class PaymentService:
    def create_payment(self, order, method):
        provider = self.get_provider(method)
        return provider.create(order)
    
    def handle_webhook(self, provider, data):
        payment = provider.process_webhook(data)
        if payment.is_confirmed:
            self.notify_order_paid(payment.order)
```

### 2. 🔄 Sistema de Webhooks Outbound
```python
# Eventos disponíveis
WEBHOOK_EVENTS = [
    'order.created',
    'order.paid',
    'order.shipped',
    'order.delivered',
    'order.cancelled',
    'product.low_stock',
    'customer.created',
    'message.received',
    'payment.confirmed',
    'payment.failed',
]

# Configuração por store
class StoreWebhookConfig(models.Model):
    store = models.ForeignKey(Store)
    url = models.URLField()
    events = ArrayField(models.CharField())
    secret = models.CharField()  # HMAC signing
    is_active = models.BooleanField()
    retry_count = models.IntegerField(default=3)
```

### 3. 📊 Analytics Engine
```python
# Métricas calculadas em real-time
class AnalyticsService:
    def get_store_metrics(self, store_id, period):
        return {
            'revenue': self.calculate_revenue(store_id, period),
            'orders': self.count_orders(store_id, period),
            'aov': self.average_order_value(store_id, period),
            'conversion_rate': self.conversion_rate(store_id, period),
            'top_products': self.top_products(store_id, period),
            'customer_retention': self.retention_rate(store_id, period),
            'hourly_distribution': self.orders_by_hour(store_id, period),
        }
```

### 4. 🤖 AI Service Layer
```python
# apps/ai/services/
├── sentiment_analyzer.py   # Análise de sentimento
├── intent_classifier.py    # Classificação de intenção
├── reply_suggester.py      # Sugestões de resposta
├── demand_forecaster.py    # Previsão de demanda
└── fraud_detector.py       # Detecção de fraudes
```

---

## 📊 Métricas de Sucesso

| Métrica | Atual | Meta Sprint 3 | Meta Final |
|---------|-------|---------------|------------|
| Maior arquivo de views | 1570 linhas | 500 linhas | <300 linhas |
| Tempo médio de resposta | ~200ms | 150ms | <100ms |
| Coverage de testes | ~30% | 60% | 80% |
| Duplicação de código | ~15% | 8% | <5% |
| Uptime | 99% | 99.5% | 99.9% |
| P95 Latency | 500ms | 300ms | <200ms |

---

## 🔒 Segurança

### ✅ Já Implementado
- ✅ `IsStoreOwner` permission
- ✅ `IsStoreStaff` permission  
- ✅ `HasStoreAccess` permission
- ✅ Filtro de queryset por owner em automation views
- ✅ Webhook signature validation
- ✅ Token encryption para integrações

### 📋 A Implementar
- [ ] **Rate Limiting**: Por tenant e endpoint
- [ ] **Audit Logging**: Todas operações sensíveis
- [ ] **IP Allowlist**: Para webhooks críticos
- [ ] **2FA Admin**: Autenticação em dois fatores
- [ ] **Secret Rotation**: Rotação automática de secrets
- [ ] **RBAC**: Role-based access control granular
- [ ] **Data Encryption**: Encryption at rest
- [ ] **PCI Compliance**: Para processamento de pagamentos

---

## 🔗 Referências

- [Django REST Framework Best Practices](https://www.django-rest-framework.org/community/tutorials-and-resources/)
- [Two Scoops of Django](https://www.feldroy.com/books/two-scoops-of-django-3-x)
- [Django Channels](https://channels.readthedocs.io/)
- [Celery Best Practices](https://docs.celeryq.dev/en/stable/userguide/tasks.html#best-practices)
- [The Twelve-Factor App](https://12factor.net/)
- [Stripe API Design](https://stripe.com/docs/api)
- [GitHub REST API Guidelines](https://docs.github.com/en/rest)
