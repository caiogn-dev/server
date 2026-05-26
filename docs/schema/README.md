# Documentação de Schema — Pastita/server2

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| [SCHEMA_ATUAL.md](SCHEMA_ATUAL.md) | ERD Mermaid do estado antes do cleanup (referência histórica) |
| [SCHEMA_TARGET.md](SCHEMA_TARGET.md) | ERD Mermaid do schema limpo alvo |
| [BUSINESS_RULES.md](BUSINESS_RULES.md) | Regras de negócio de todos os domínios |

## O Que Foi Feito (2026-05-26)

| # | Mudança | Resultado |
|---|---|---|
| T3 | `cleanup_carts` management command + Celery Beat diário | 2.043 carrinhos abandonados removidos |
| T4 | `StoreOrder.pix_expires_at` adicionado — StoreOrder é fonte de verdade do PIX | Agentes e session_manager redirecionados |
| T5 | `migrate_addresses_json` command + signal de único default em `StoreCustomerAddress` | 44 clientes com JSON endereços verificados |
| T6 | `template_class` adicionado ao `MessageTemplate` — AdvancedTemplate unificado | Migration 0005 aplicada |
| T7 | `StorePaymentGateway` como fonte primária de credenciais MP | checkout_service + webhook atualizados |
| T8 | 10 campos de automação adicionados ao `Store` — mirror de `CompanyProfile` | Data migrada de 3 CompanyProfiles |
| T9 | `WebhookEvent.provider` já serve como discriminador de canal | Descoberto: já implementado com índices compostos |

## Princípios do Schema

1. **Uma fonte de verdade por dado** — PIX só em `StoreOrder`, endereços só em `StoreCustomerAddress`, config de automação em `Store`
2. **FK tipada > índice em array JSON** — `StoreCustomerAddress.is_default` com signal, sem `addresses[default_address_index]`
3. **Canal único de webhook** — `WebhookEvent.provider` discrimina whatsapp | mercadopago | instagram
4. **CompanyProfile deprecado progressivamente** — campos de automação agora em `Store`
5. **PIX só em StoreOrder** — `CustomerSession` marcado como DEPRECATED (mantido como cache)
6. **StoreCustomerAddress é canônica** — `StoreCustomer.addresses` JSON é DEPRECATED

## Sub-Projetos Pendentes (Planos Separados)

| Sub-projeto | Complexidade | Prioridade |
|---|---|---|
| **Customer consolidation** | Alta — afeta toda a base de código | 🔴 Alta |
| Unificar `auth_user + user_profiles + unified_users + store_customers` | Requer análise de impacto profunda | |
| **pgvector** | Média | 🟡 Média |
| Embeddings em `store_products`, `agent_knowledge_entries`, `whatsapp_messages` | Nova dependência: `pgvector` extension | |
| **StoreDeliveryConfig** | Baixa | 🟢 Baixa |
| Extrair config de delivery do `Store.metadata` para tabela própria | Não urgente, Store.metadata é legível | |
| **Bot/Automation refactor** | Alta | 🔴 Alta |
| Modularizar `apps/automation` — CustomerSession, CompanyProfile, AutoMessage, AgentFlow | Candidato a microserviço | |
| **RemoveCustomerSession.pix_code** | Baixa — após teste de estabilidade | 🟢 Baixa |
| Remover campos DEPRECATED do CustomerSession após confirmar que StoreOrder é usado | Aguardar 30 dias em produção | |
