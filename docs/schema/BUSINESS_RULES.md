# Regras de Negócio — Pastita/server2

> Fonte de verdade para implementadores e agentes de IA.
> Atualizar sempre que uma regra mudar.

---

## 1. Ciclo de Vida do Pedido

```mermaid
stateDiagram-v2
    [*] --> pending : checkout criado
    pending --> confirmed : lojista confirma
    pending --> cancelled : cancelamento manual/timeout
    confirmed --> paid : pagamento confirmado (Webhook MP)
    confirmed --> preparing : lojista inicia preparo
    paid --> preparing : automático após pagamento
    preparing --> ready : lojista marca pronto
    ready --> delivered : entregador confirma entrega
    ready --> picked_up : cliente retira (pickup)
    delivered --> [*]
    picked_up --> [*]
    cancelled --> [*]
```

**Regras:**
- `access_token` é UUID v4, imutável após criação. Permite acesso público ao pedido sem autenticação.
- `pix_code` e `pix_qr_code` vivem APENAS em `StoreOrder`. O `CustomerSession` NÃO deve duplicar esses campos.
- `payment_status` é independente de `status`. Um pedido `confirmed` pode ter `payment_status=pending` (ex: pagamento na entrega).
- Cancelamento: só permitido em `pending` ou `confirmed`. Pedidos em `preparing` ou além não podem ser cancelados via API.
- `order_number` é sequencial por loja, formato `LOJA-YYYYMMDD-NNNN`.

## 2. Carrinho e Checkout

```mermaid
sequenceDiagram
    Cliente->>+API: POST /checkout/ (X-Cart-Key)
    API->>StoreCart: busca por session_key
    API->>StoreCartItem: valida itens, estoque
    API->>StoreOrder: cria order (status=pending)
    API->>StoreCart: desativa cart (is_active=False)
    API-->>-Cliente: {order_id, access_token, pix_code?}
```

**Regras:**
- Carrinho guest identificado por `X-Cart-Key` (UUID gerado no frontend, armazenado em localStorage).
- Carrinho autenticado tem FK `user`, mas também mantém `session_key` para compatibilidade.
- Carrinhos guest sem atividade por 30 dias são elegíveis para cleanup automático.
- Checkout valida `min_order_value` ANTES de processar pagamento.
- Cupom é validado no checkout; `coupon_code` é gravado no `StoreOrder` como snapshot.

## 3. Identificação do Cliente

**Hoje (problemático):**
```
WhatsApp → UnifiedUser (phone) ← CustomerSession
                ↕ (45/54 sem link)
auth_user ← UserProfile
    ↕
StoreCustomer (por loja)
```

**Regra atual (a respeitar até consolidação):**
- `StoreCustomer` é o perfil do cliente POR LOJA. Um cliente que compra em 2 lojas tem 2 `StoreCustomer`.
- `phone` é o identificador primário para clientes que chegam via WhatsApp.
- Email `{phone}@pastita.local` é email técnico interno — NUNCA exibir para o cliente.
- `StoreCustomer.user` (FK) é o `auth_user` Django. `StoreCustomer.unified_user` aponta para o `UnifiedUser` que agrega canais.
- O campo `StoreCustomer.addresses` (JSON) é DEPRECATED — usar tabela `StoreCustomerAddress`.

## 4. Endereços

**Regras:**
- `StoreCustomerAddress` é a fonte de verdade.
- `is_default=True` marca o endereço padrão. Só um endereço pode ser `is_default=True` por cliente. Garantir via signal ou constraint.
- `StoreCustomer.default_address_id` (FK pós-cleanup) aponta direto para `StoreCustomerAddress`.
- Endereços capturados no checkout são salvos automaticamente via `CustomerIdentityService.sync_checkout_customer`.
- `lat`/`lng` são preenchidos de forma lazy (geocodificados na primeira vez que a taxa de entrega for calculada).

## 5. Taxa de Entrega

```mermaid
flowchart TD
    A[Recebe distance_km OU lat/lng OU address/zip] --> B{Tem lat/lng?}
    B -- não --> C[Geocodifica via Google Maps]
    C --> D[Tem coordenadas]
    B -- sim --> D
    D --> E{Há StoreDeliveryZone ativa?}
    E -- sim --> F[Busca zona que contém distance_km]
    F --> G{Zona encontrada?}
    G -- sim --> H[Retorna delivery_fee da zona]
    G -- não --> I[Retorna unavailable]
    E -- não --> J[Usa cálculo dinâmico: base_fee + fee_per_km × max(0, dist - flat_km)]
```

**Regras:**
- Google Maps é o único provider de geocodificação. Não usar HERE Maps.
- `StoreDeliveryZone` é a fonte de verdade de zonas. `Store.default_delivery_fee` é fallback quando não há zonas.
- A taxa de entrega é SEMPRE calculada pelo backend. O Flutter/frontend nunca deve hardcodar valores.
- `delivery_fee` gravado no `StoreOrder` é snapshot imutável no momento do checkout.

## 6. Pagamento PIX (MercadoPago)

```mermaid
sequenceDiagram
    Cliente->>+API: checkout com payment_method=pix
    API->>MercadoPago: cria preferência
    MercadoPago-->>API: {pix_code, qr_code, expires_at}
    API->>StoreOrder: salva pix_code, pix_qr_code
    API-->>-Cliente: {pix_code, pix_qr_code}
    loop polling
        Cliente->>API: GET /orders/{id}/payment-status/?token=
        API-->>Cliente: {payment_status}
    end
    MercadoPago->>+Webhook: POST /webhooks/payments/mercadopago/
    Webhook->>StoreOrder: atualiza payment_status=paid
    Webhook->>StoreOrder: atualiza status=paid
    Webhook-->>-MercadoPago: 200 OK
```

**Regras:**
- `pix_code` e `pix_qr_code` pertencem ao `StoreOrder`. O `CustomerSession` não deve duplicá-los.
- Webhook do MercadoPago é idempotente — reprocessar o mesmo evento não deve criar pagamento duplicado. Verificar `event_id` no `WebhookEvent`.
- `StorePayment` registra cada tentativa de pagamento. Um pedido pode ter múltiplos `StorePayment` (retrials).
- Credenciais de gateway ficam em `PaymentGateway` (pós-cleanup) ou `StoreIntegration` (hoje). Nunca em variável de ambiente hardcoded por loja.

## 7. WhatsApp — Pipeline de Automação

```mermaid
flowchart TD
    A[Mensagem recebida] --> B[WebhookEvent criado]
    B --> C[apps.automation: detecta intenção]
    C --> D{Intenção}
    D -- saudação --> E[AutoMessage: welcome]
    D -- cardápio --> F[AutoMessage: menu]
    D -- pedido/checkout --> G[CustomerSession: inicia fluxo]
    D -- complexo/NLP --> H[AgentFlow ou LLM Agent]
    G --> I{Tem endereço?}
    I -- não --> J[Caio pede endereço]
    I -- sim --> K[Calcula taxa de entrega]
    K --> L[Gera PIX via MercadoPago]
    L --> M[Salva em StoreOrder]
```

**Regras do Agente Caio:**
- Deve perguntar endereço/localização ANTES de calcular entrega.
- NÃO deve expor valores de taxa de entrega internamente (ex: "a taxa é R$8 porque você está a 4km").
- NÃO deve gerar PIX antes de ter itens claros no carrinho.
- Handover para humano quando: `CustomerSession.status = 'needs_human'` ou após 3 tentativas sem progresso.
- Bot está no modo automático quando `CompanyProfile.auto_reply_enabled = True` E `Conversation.mode = 'bot'`.

## 8. OTP WhatsApp

```mermaid
sequenceDiagram
    App->>+API: POST /auth/whatsapp/send/ {phone_number}
    API->>WhatsApp: envia template "codigo_verificacao"
    API-->>-App: {expires_in_minutes: 15, expires_at}
    App->>+API: POST /auth/whatsapp/verify/ {phone_number, code}
    API->>Redis: valida código (TTL 15min, max 3 tentativas)
    API->>CustomerIdentityService: resolve_user(phone)
    API->>Token: get_or_create DRF token
    API-->>-App: {valid: true, token: "abc123..."}
```

**Regras:**
- OTP usa template Meta `codigo_verificacao`. Não usar mensagem de texto livre fora da janela de 24h.
- Código expira em 15 minutos. Máximo 3 tentativas antes de bloquear.
- A resposta do `/send/` NUNCA inclui o código (nem em DEBUG=True na API — apenas no log).
- Email `@pastita.local` nunca aparece na resposta do `/verify/`.
- `_resolve_whatsapp_account_id`: usa `whatsapp_account_id` do request → `DEFAULT_WHATSAPP_ACCOUNT_ID` no settings → único WhatsAppAccount ativo no banco.

## 9. Webhook Central

**Regras:**
- Todo webhook recebido (WhatsApp, MercadoPago, Instagram) passa por `apps.webhooks.dispatcher`.
- HMAC-SHA256 validado na entrada. Payload rejeitado se assinatura inválida.
- `WebhookEvent.processing_status`: `pending` → `processed` | `failed` | `dead_letter`.
- Retry automático até 3 vezes com backoff exponencial para eventos `failed`.
- `dead_letter` = falhou todas as tentativas. Fica em `WebhookDeadLetter` para inspeção manual.
- (Pós-cleanup) `WebhookEvent` tem campo `channel` em vez de tabela por canal.

## 10. Ciclo de Vida do Carrinho

**Regras de cleanup:**
- Carrinho guest (`user=NULL`) com `updated_at > 30 dias` → elegível para DELETE.
- Carrinho autenticado com `updated_at > 90 dias` → elegível para DELETE.
- Carrinho com `is_active=False` (checkout feito) → elegível para DELETE imediato após 7 dias.
- O job `cleanup_carts` roda diariamente via Celery Beat.
- NUNCA deletar carrinho com `is_active=True` e `updated_at < 30 dias` (usuário pode estar ativo).
