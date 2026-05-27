# Schema Atual — Pastita/server2

> Gerado em 2026-05-26. Reflete o estado ANTES do cleanup.

## ERD — Domínio E-commerce

```mermaid
erDiagram
    Store {
        uuid id PK
        string name
        string slug
        string status
        string store_type
        string primary_color
        string secondary_color
        string template
        string tagline
        string custom_domain
        decimal default_delivery_fee
        string metadata_json "⚠️ delivery config aqui duplica StoreDeliveryZone"
        int owner_id FK
        int whatsapp_account_id FK
    }

    CompanyProfile {
        uuid id PK
        string company_name "⚠️ duplica Store.name"
        string address "⚠️ duplica Store.address"
        string whatsapp_number "⚠️ duplica Store.whatsapp_number"
        string website_url "⚠️ duplica Store.website_url"
        bool auto_reply_enabled
        bool use_ai_agent
        int default_agent_id FK
        int store_id FK
        int account_id FK
    }

    StoreOrder {
        uuid id PK
        string order_number
        string access_token
        string customer_name "⚠️ duplica User.first_name+last_name"
        string customer_email "⚠️ duplica User.email"
        string customer_phone "⚠️ duplica StoreCustomer.phone"
        string pix_code "✅ fonte de verdade do PIX"
        string pix_qr_code
        string status
        string payment_status
        decimal subtotal
        decimal delivery_fee
        decimal total
        int store_id FK
        int customer_id FK "nullable — usuario django"
    }

    StoreCustomer {
        uuid id PK
        string phone
        string whatsapp
        json addresses "⚠️ duplica StoreCustomerAddress"
        int default_address_index "⚠️ frágil — índice em array JSON"
        int store_id FK
        int unified_user_id FK "⚠️ 45/54 são NULL"
        int user_id FK
    }

    StoreCustomerAddress {
        uuid id PK
        string street
        string number
        string neighborhood
        string city
        string state
        string zip_code
        bool is_default
        int customer_id FK
    }

    CustomerSession {
        uuid id PK
        string phone_number
        string pix_code "⚠️ duplica StoreOrder.pix_code"
        string pix_qr_code "⚠️ duplica StoreOrder.pix_qr_code"
        datetime pix_expires_at "⚠️ não tem equivalente em StoreOrder"
        int company_id FK
        int order_id FK
        int conversation_id FK
        int unified_user_id FK
    }

    StoreIntegration {
        uuid id PK
        string integration_type "mercadopago | whatsapp"
        string access_token_encrypted "⚠️ duplica StorePaymentGateway.access_token"
        int store_id FK
    }

    StorePaymentGateway {
        uuid id PK
        string gateway_type "mercadopago | stripe"
        string api_key "⚠️ duplica StoreIntegration.api_key_encrypted"
        string access_token "⚠️ duplica StoreIntegration.access_token_encrypted"
        int store_id FK
    }

    Store ||--o{ StoreOrder : "tem"
    Store ||--o{ StoreCustomer : "tem"
    Store ||--|| CompanyProfile : "1:1 duplicado"
    StoreCustomer ||--o{ StoreCustomerAddress : "tem"
    StoreOrder ||--o{ StoreOrderItem : "tem"
    StoreOrder ||--o| CustomerSession : "referenciado por"
    Store ||--o{ StoreIntegration : "tem"
    Store ||--o{ StorePaymentGateway : "tem"
```

## ERD — Domínio Mensageria

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
        string phone_number
        string contact_name "⚠️ não FK para Customer"
        string wa_id
        string mode
        string status
        int account_id FK
        int assigned_agent_id FK
    }

    Message_WA {
        uuid id PK
        string whatsapp_message_id
        string direction
        string text_body
        string status
        int account_id FK
        int conversation_id FK
    }

    WebhookEvent_WA {
        uuid id PK
        string event_type
        string processing_status
        json payload "⚠️ duplica WebhookEvent central"
        int account_id FK
    }

    WebhookEvent_Central {
        uuid id PK
        string event_type
        string processing_status
        json payload "⚠️ duplica WebhookEvent_WA"
    }

    MessageTemplate {
        uuid id PK
        string name
        string category
        string status
        int account_id FK
    }

    AdvancedTemplate {
        uuid id PK
        string name "⚠️ mesmo conceito de MessageTemplate"
        string template_type
        int account_id FK
    }

    WhatsAppAccount ||--o{ Conversation : "tem"
    WhatsAppAccount ||--o{ Message_WA : "tem"
    WhatsAppAccount ||--o{ WebhookEvent_WA : "tem"
    WhatsAppAccount ||--o{ MessageTemplate : "tem"
    WhatsAppAccount ||--o{ AdvancedTemplate : "⚠️ duplica MessageTemplate"
    Conversation ||--o{ Message_WA : "tem"
```

## Inventário de Redundâncias

| # | Redundância | Impacto | Prioridade |
|---|---|---|---|
| R1 | `CompanyProfile` duplica `Store` (name, address, whatsapp, website) | Dados divergentes em prod | 🔴 Alta |
| R2 | `pix_code/pix_qr_code` em `CustomerSession` E `StoreOrder` | Fonte de verdade ambígua do PIX | 🔴 Alta |
| R3 | `StoreCustomer.addresses` JSON E `StoreCustomerAddress` tabela | Sincronização manual, bug-prone | 🔴 Alta |
| R4 | `StoreIntegration` E `StorePaymentGateway` para MercadoPago | Credenciais em dois lugares | 🟡 Média |
| R5 | `whatsapp_webhook_events` E `webhook_events` (central) | 7.681 + 13.024 = duplicados | 🟡 Média |
| R6 | `MessageTemplate` E `AdvancedTemplate` | Mesma entidade, dois modelos | 🟡 Média |
| R7 | `StoreOrder.customer_name/email/phone` quando FK `customer` existe | Campos denormalizados divergem | 🟢 Baixa |
| R8 | `unified_users` 340 registros, 285 sem `django_user` | Identidade fragmentada | 🔴 Alta |
| R9 | 3.426 carrinhos guest > 7 dias | Performance, storage | 🟡 Média |
| R10 | `Store.metadata` JSON para config de delivery | Deveria ser StoreDeliveryConfig | 🟢 Baixa |
