# Toca Delivery Integration

Data: 2026-04-19
Escopo: `server2` (Django) ↔ Toca Delivery SaaS (`api.tocadelivery.com.br`)

---

## 1. Visão geral

Quando um pedido de entrega é confirmado no `server2`, ele automaticamente cria uma **corrida** no Toca Delivery SaaS. O Toca se encarrega de:

- Despachar a corrida para motoboys disponíveis
- Rastrear o ciclo de vida (aceito → em coleta → em rota → entregue)
- Notificar o cliente via WhatsApp (próprio fluxo do Toca)

O `server2` recebe as atualizações de status via **polling periódico** (Celery Beat, 60s) e futuramente via **webhook** (quando o campo `empresa.webhook_url` for disparado pelo Toca).

---

## 2. Arquitetura

```
StoreOrder.status = 'confirmed'
        │
        ▼ (signal: on_order_confirmed_dispatch_toca)
        │
        ▼
dispatch_order_to_toca_delivery.delay(order_id)   [Celery task]
        │
        ▼
TocaDeliveryProvider.create(store, order)
        │  POST /corridas  →  api.tocadelivery.com.br
        │
        ▼
StoreOrder.external_delivery_id = corrida UUID
StoreOrder.external_delivery_code = 'TCA-XXXX'
StoreOrder.external_delivery_url = rastreio público


[Celery Beat — cada 60s]
sync_toca_delivery_statuses()
        │
        ▼
TocaDeliveryProvider.get_status(external_delivery_id)
        │  GET /corridas/{id}  →  api.tocadelivery.com.br
        │
        ▼
        Status mapping:
        aceita / em_coleta / coletada / em_rota  →  StoreOrder.status = 'out_for_delivery'
        entregue                                 →  StoreOrder.status = 'delivered'
        cancelada                                →  (sem mudança automática — revisão humana)


[Webhook futuro — quando Toca disparar empresa.webhook_url]
POST /webhooks/v1/toca-delivery/
        │
        ▼
TocaDeliveryHandler.handle(event, payload, headers)
        │
        ▼
Mesmo mapeamento de status acima
```

---

## 3. Configuração

Adicionar ao `.env` do `server2`:

```env
TOCA_DELIVERY_API_URL=https://api.tocadelivery.com.br
TOCA_DELIVERY_EMAIL=email@empresa.com
TOCA_DELIVERY_PASSWORD=senha_segura
TOCA_DELIVERY_ENABLED=true
TOCA_DELIVERY_WEBHOOK_SECRET=chave_hmac_compartilhada
```

Para habilitar apenas por loja (sem TOCA_DELIVERY_ENABLED global):

```python
# Em Store.metadata (via admin ou API)
{
    "delivery_provider": "toca"
}
```

---

## 4. Endpoints do Toca Delivery utilizados

| Método | Endpoint | Uso |
|--------|----------|-----|
| POST | `/auth/login` | Autenticação JWT |
| POST | `/corridas/calcular-preco` | Quote de preço |
| POST | `/corridas` | Criar corrida |
| GET | `/corridas/{id}` | Consultar status |
| POST | `/corridas/{id}/cancelar` | Cancelar corrida |

---

## 5. Mapeamento de status

| CorridaStatus (Toca) | StoreOrder.OrderStatus (server2) |
|----------------------|----------------------------------|
| `criada` | — (sem mudança) |
| `ofertada` | — (sem mudança) |
| `aceita` | `out_for_delivery` |
| `em_coleta` | `out_for_delivery` |
| `coletada` | `out_for_delivery` |
| `em_rota` | `out_for_delivery` |
| `entregue` | `delivered` |
| `cancelada` | — (revisão humana necessária) |

---

## 6. Campos adicionados em StoreOrder

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `external_delivery_provider` | CharField(50) | `'toca'` quando despachado |
| `external_delivery_id` | CharField(100) | UUID da corrida no Toca |
| `external_delivery_code` | CharField(30) | Código legível (ex: `TCA-1234`) |
| `external_delivery_status` | CharField(30) | Status atual no Toca |
| `external_delivery_url` | URLField | URL de rastreio público |

---

## 7. Arquivos relevantes

```
apps/stores/services/delivery_provider/
    __init__.py           — fábrica get_delivery_provider(store)
    base.py               — ABC DeliveryProvider + dataclasses
    toca_delivery.py      — TocaDeliveryProvider (cliente da API)
    internal.py           — InternalDeliveryProvider (no-op)

apps/stores/tasks.py
    dispatch_order_to_toca_delivery()   — cria corrida
    sync_toca_delivery_statuses()       — polling periódico (60s)

apps/stores/signals.py
    on_order_confirmed_dispatch_toca()  — dispara task ao confirmar pedido

apps/webhooks/handlers/toca_delivery_handler.py
    TocaDeliveryHandler                 — receptor de webhook do Toca

apps/stores/migrations/0006_order_external_delivery_provider.py

config/settings/base.py
    TOCA_DELIVERY_API_URL / EMAIL / PASSWORD / ENABLED / WEBHOOK_SECRET

config/celery.py
    sync-toca-delivery-statuses         — Beat schedule (60s)
```

---

## 8. Autenticação

O Toca Delivery usa **JWT Bearer**. O `TocaDeliveryProvider`:

1. Faz `POST /auth/login` com email/password
2. Cacheia o `access_token` no Django cache backend com TTL de 55 minutos
3. Em caso de `401`, invalida o cache e reauthentifica automaticamente

---

## 9. Webhook receiver

**Endpoint**: `POST /webhooks/v1/toca-delivery/`

**Payload esperado**:
```json
{
    "corrida_id": "uuid-da-corrida",
    "codigo": "TCA-1234",
    "status": "em_rota",
    "evento": "status_change",
    "timestamp": "2026-04-19T10:00:00Z"
}
```

**Segurança**: HMAC-SHA256 no header `X-Toca-Signature` (hex digest do body).
Configure `TOCA_DELIVERY_WEBHOOK_SECRET` no `.env` do `server2` e o mesmo valor no painel Toca.

Para registrar o webhook no Toca Delivery:
```
PATCH /me/webhook
{ "webhook_url": "https://backend.pastita.com.br/webhooks/v1/toca-delivery/" }
```

---

## 10. Testes

```bash
make test-app APP=tests.test_toca_delivery_provider   # 42 testes
make test-app APP=tests.test_geo_service               # 41 testes (Google Maps)
```

Cobertura:
- Auth: success, missing credentials, cache hit, 401 retry
- Quote: success, error status
- Create: success, correct payload, 422 error, 401 reauthentication
- Cancel: success, failure
- Get status: success, not found
- Status mapping: todos os 8 status possíveis
- Factory: internal por padrão, toca por settings globais, toca por store.metadata
