# 🔧 Plano de Refactoring - Server

## Visão Geral

Este documento detalha o plano de refactoring para melhorar a arquitetura do projeto.

---

## 📋 Fase 1: Dividir stores/models.py (1854 linhas)

### Objetivo
Dividir o arquivo monolítico em módulos menores e mais gerenciáveis.

### Estrutura Proposta
```
apps/stores/models/
├── __init__.py          # Re-exporta todos os modelos
├── base.py              # Store, StoreIntegration, StoreWebhook
├── category.py          # StoreCategory
├── product.py           # StoreProduct, StoreProductVariant, StoreProductType
├── combo.py             # StoreCombo, StoreComboItem
├── customer.py          # StoreCustomer, StoreWishlist
├── cart.py              # StoreCart, StoreCartItem, StoreCartComboItem
├── order.py             # StoreOrder, StoreOrderItem, StoreOrderComboItem
├── delivery.py          # StoreDeliveryZone
└── coupon.py            # StoreCoupon
```

### Passos
1. Criar diretório `apps/stores/models/`
2. Mover cada grupo de modelos para seu arquivo
3. Criar `__init__.py` que re-exporta tudo
4. Testar que imports continuam funcionando

---

## 📋 Fase 2: Migrar dependências dos apps deprecated

### Apps Deprecated
- `apps.orders` → Migrar para `apps.stores`
- `apps.payments` → Migrar para `apps.stores`
- `apps.ecommerce` → Migrar para `apps.stores`

### Arquivos que precisam ser atualizados

#### Dependências de `apps.orders.models.Order`:
| Arquivo | Ação |
|---------|------|
| `apps/payments/services/payment_service.py` | Usar StoreOrder |
| `apps/payments/consumers.py` | Usar StoreOrder |
| `apps/campaigns/api/views.py` | Usar StoreOrder |
| `apps/core/export_views.py` | Usar StoreOrder |
| `apps/core/dashboard_views.py` | Usar StoreOrder |
| `apps/automation/services/automation_service.py` | Usar StoreOrder |
| `apps/automation/tasks/scheduled.py` | Usar StoreOrder |
| `apps/unified/api/views.py` | Já usa ambos (manter) |
| `apps/whatsapp/api/views.py` | Usar StoreOrder |
| `apps/whatsapp/management/commands/force_delete_account.py` | Usar StoreOrder |
| `apps/marketing/api/views.py` | Usar StoreOrder |
| `apps/audit/api/views.py` | Usar StoreOrder |

#### Dependências de `apps.payments.models.Payment`:
| Arquivo | Ação |
|---------|------|
| `apps/core/export_views.py` | Criar StorePayment ou remover |
| `apps/core/dashboard_views.py` | Criar StorePayment ou remover |
| `apps/core/routing.py` | Remover PaymentConsumer |
| `apps/automation/tasks/scheduled.py` | Criar StorePayment ou remover |
| `apps/whatsapp/api/views.py` | Criar StorePayment ou remover |
| `apps/whatsapp/management/commands/force_delete_account.py` | Criar StorePayment ou remover |
| `apps/audit/api/views.py` | Criar StorePayment ou remover |

### Estratégia
1. **NÃO remover** os apps deprecated ainda
2. Criar modelo `StorePayment` em stores se necessário
3. Atualizar imports gradualmente
4. Manter compatibilidade retroativa

---

## 📋 Fase 3: Unificar campaigns e marketing

### Análise
- `apps.campaigns` - Campanhas WhatsApp (broadcast, drip)
- `apps.marketing` - Email marketing (Resend)

### Decisão
**MANTER SEPARADOS** - São canais diferentes:
- campaigns = WhatsApp
- marketing = Email

Apenas documentar melhor a separação.

---

## 📋 Fase 4: Adicionar Testes

### Cobertura Atual
- `tests/test_ecommerce_api.py`
- `tests/test_orders_api.py`

### Testes a Adicionar
1. `tests/test_stores_api.py` - API de lojas
2. `tests/test_whatsapp_webhook.py` - Webhooks WhatsApp
3. `tests/test_automation.py` - Automação

---

## 🚀 Ordem de Execução

1. ✅ **Fase 1**: Dividir stores/models.py
2. ⏳ **Fase 2**: Migrar dependências (parcial - apenas imports seguros)
3. ⏳ **Fase 3**: Documentar separação campaigns/marketing
4. ⏳ **Fase 4**: Adicionar testes básicos

---

## ⚠️ Riscos

| Risco | Mitigação |
|-------|-----------|
| Quebrar imports | Testar com `python manage.py check` |
| Quebrar migrações | Não alterar estrutura de tabelas |
| Perder dados | Não remover apps deprecated |

---

## 📅 Timeline Estimado

- Fase 1: 30 minutos
- Fase 2: 1 hora (parcial)
- Fase 3: 10 minutos
- Fase 4: 30 minutos

**Total: ~2 horas**
