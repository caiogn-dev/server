# Schema Target — Pastita/server2

> Estado alvo após execução completa deste plano.
> A consolidação de identidade (Customer único) é sub-projeto separado.

## ERD — Domínio E-commerce (Target)

```mermaid
erDiagram
    Store {
        uuid id PK
        string name
        string slug
        string status
        string store_type
        string template
        string tagline
        string custom_domain
        string primary_color
        string secondary_color
        string logo_url
        bool auto_reply_enabled "migrado do CompanyProfile"
        bool use_ai_agent "migrado do CompanyProfile"
        bool welcome_message_enabled "migrado do CompanyProfile"
        bool abandoned_cart_notification "migrado do CompanyProfile"
        int abandoned_cart_delay_minutes "migrado do CompanyProfile"
        bool pix_notification_enabled "migrado do CompanyProfile"
        bool payment_confirmation_enabled "migrado do CompanyProfile"
        bool order_status_notification_enabled "migrado do CompanyProfile"
        int default_agent_id FK
        int owner_id FK
        int whatsapp_account_id FK
    }

    StoreDeliveryConfig {
        uuid id PK
        decimal default_fee
        decimal free_threshold
        decimal max_distance_km
        int max_time_minutes
        string provider "google_maps | fixed"
        int store_id FK "1:1"
    }

    StoreOrder {
        uuid id PK
        string order_number
        string access_token
        string pix_code "ÚNICA fonte de verdade"
        string pix_qr_code
        datetime pix_expires_at
        string status
        string payment_status
        decimal subtotal
        decimal delivery_fee
        decimal total
        int store_id FK
        int customer_id FK "StoreCustomer — nullable guest"
    }

    StoreCustomer {
        uuid id PK
        string phone "principal identificador"
        string email
        string name
        int store_id FK
        int user_id FK "django User — nullable"
        int default_address_id FK "FK direto — sem índice JSON"
    }

    StoreCustomerAddress {
        uuid id PK
        string street
        string number
        string complement
        string neighborhood
        string city
        string state
        string zip_code
        decimal lat
        decimal lng
        bool is_default
        int customer_id FK
    }

    PaymentGateway {
        uuid id PK
        string gateway_type "mercadopago | stripe | pix_manual"
        bool is_enabled
        bool is_default
        string public_key
        string api_key_encrypted
        string access_token_encrypted
        string webhook_secret
        int store_id FK
    }

    Store ||--o{ StoreOrder : "tem"
    Store ||--o{ StoreCustomer : "tem"
    Store ||--|| StoreDeliveryConfig : "1:1"
    Store ||--o{ PaymentGateway : "tem"
    StoreCustomer ||--o{ StoreCustomerAddress : "tem"
    StoreCustomer ||--o| StoreCustomerAddress : "default_address"
    StoreOrder ||--o{ StoreOrderItem : "tem"
```

## ERD — Domínio Mensageria (Target)

```mermaid
erDiagram
    WhatsAppAccount {
        uuid id PK
        string phone_number_id
        string waba_id
        string access_token_encrypted
        int default_agent_id FK
        int owner_id FK
    }

    Conversation {
        uuid id PK
        string external_id "wa_id, ig_thread_id..."
        string phone_number
        string contact_name
        string channel "whatsapp | instagram | messenger"
        string mode
        string status
        int account_id FK
        int assigned_agent_id FK
    }

    Message {
        uuid id PK
        string external_message_id
        string direction
        string text_body
        string media_url
        string status
        int conversation_id FK
    }

    WebhookEvent {
        uuid id PK
        string channel "whatsapp | mercadopago | instagram"
        string event_type
        string processing_status
        json payload
        datetime processed_at
        int retry_count
    }

    WhatsAppTemplate {
        uuid id PK
        string name
        string category "authentication | marketing | utility"
        string status "approved | pending | rejected"
        json components
        string meta_template_id
        int account_id FK
    }

    WhatsAppAccount ||--o{ Conversation : "tem"
    Conversation ||--o{ Message : "tem"
    WhatsAppAccount ||--o{ WhatsAppTemplate : "tem"
```

## Princípios do Schema Limpo

1. **Uma fonte de verdade por dado** — PIX fica só em `StoreOrder`. Endereços só em `StoreCustomerAddress`. Config de automação só em `Store`.
2. **FKs tipadas em vez de índices em arrays JSON** — `StoreCustomer.default_address_id` aponta para linha, não `addresses[default_address_index]`.
3. **Webhook único por canal** — `WebhookEvent` com campo `channel` em vez de tabela por canal.
4. **Templates unificados** — `WhatsAppTemplate` absorve `AdvancedTemplate`.
5. **PaymentGateway único** — `StoreIntegration` guarda integrações não-payment; `PaymentGateway` guarda payment com credenciais.
6. **CompanyProfile extinto** — campos de automação migram para `Store`.
