# ANÁLISE DE DUPLICIDADES - Sistema de Mensagens

## Resumo Executivo

O sistema possui **duplicações críticas** que causam inconsistências, erros 500 e dificuldade de manutenção. A arquitetura atual tem múltiplos apps com responsabilidades sobrepostas.

---

## 1. DUPLICAÇÕES IDENTIFICADAS

### 1.1 Apps Duplicados

| App Principal | App Duplicado | Situação |
|---------------|---------------|----------|
| `core` | `core_v2` | Ambos ativos - BaseModel duplicado |
| `messaging` | `messaging_v2` | Ambos ativos - Models similares |
| `marketing` | `marketing_v2` | Ambos ativos - Campaign duplicado |
| `stores` | `commerce` | Ambos ativos - Store duplicado |
| `messaging` | `messenger` | messenger deprecated mas importado |
| `messaging` | `whatsapp` | Models de conta/conversa duplicados |
| `messaging` | `instagram` | Models de conta/conversa duplicados |

### 1.2 Models Duplicados

#### A. Contas de Plataforma (CRÍTICO)

**WhatsApp:**
- `whatsapp.WhatsAppAccount` (apps/whatsapp/models.py) ← **FONTE DE VERDADE**
- `stores.StoreIntegration` (apps/stores/models/base.py) - tem phone_number_id, waba_id
- `messaging_v2.PlatformAccount` (apps/messaging_v2/models.py) - model genérico

**Instagram:**
- `instagram.InstagramAccount` (apps/instagram/models.py) ← **FONTE DE VERDADE**
- `stores.StoreIntegration` - pode armazenar Instagram
- `messaging_v2.PlatformAccount` - model genérico

**Messenger:**
- `messaging.MessengerAccount` (apps/messaging/models.py) ← **FONTE DE VERDADE**
- `stores.StoreIntegration` - pode armazenar Messenger
- `messaging_v2.PlatformAccount` - model genérico

#### B. Conversas

- `conversations.Conversation` (apps/conversations/models.py) ← **FONTE DE VERDADE**
- `messaging.MessengerConversation` - Messenger específico
- `instagram.InstagramConversation` - Instagram específico
- `messaging_v2.Conversation` - Model genérico

#### C. Mensagens

- `whatsapp.Message` (apps/whatsapp/models.py) ← **FONTE DE VERDADE**
- `messaging.MessengerMessage` - Messenger específico
- `instagram.InstagramMessage` - Instagram específico
- `messaging_v2.UnifiedMessage` - Model genérico

#### D. Templates

- `whatsapp.MessageTemplate` (apps/whatsapp/models.py) ← **FONTE DE VERDADE**
- `messaging_v2.MessageTemplate` - Model genérico
- `marketing_v2.Template` - Marketing específico

#### E. Lojas/Empresas

- `stores.Store` (apps/stores/models/base.py) ← **FONTE DE VERDADE**
- `commerce.Store` (apps/commerce/models.py) - Model duplicado
- `automation.CompanyProfile` - Perfil de empresa vinculado à Store

#### F. Campanhas

- `campaigns.Campaign` (apps/campaigns/models.py) ← **FONTE DE VERDADE**
- `marketing.EmailCampaign` - Email específico
- `marketing_v2.Campaign` - Model genérico

#### G. Mensagens Agendadas

- `automation.ScheduledMessage` (apps/automation/models.py) ← **FONTE DE VERDADE**
- `marketing_v2.ScheduledMessage` - Model duplicado

---

## 2. PROBLEMAS CAUSADOS

### 2.1 Erro 500 em `/messaging/messenger/accounts/`

**Causa provável:** 
- O endpoint usa `messaging.MessengerAccount` 
- Mas o frontend pode estar tentando criar em outro model
- Ou há inconsistência entre serializer e model

### 2.2 Dados não aparecem no painel

**Causa:**
- WABA ID e Phone Number ID estão em `whatsapp.WhatsAppAccount`
- Mas o painel pode estar consultando `stores.StoreIntegration` ou `messaging_v2.PlatformAccount`
- Não há sincronização entre essas tabelas

### 2.3 Inconsistência Django Admin

**Causa:**
- Múltiplas tabelas com nomes similares:
  - `messenger_accounts`
  - `whatsapp_accounts` 
  - `instagram_accounts`
  - `store_integrations`
  - `platform_accounts` (messaging_v2)

---

## 3. FONTE DE VERDADE POR ENTIDADE

| Entidade | Fonte de Verdade | Tabela |
|----------|------------------|--------|
| Usuário | `users.User` | `users` |
| Loja | `stores.Store` | `stores` |
| WhatsApp Account | `whatsapp.WhatsAppAccount` | `whatsapp_accounts` |
| Instagram Account | `instagram.InstagramAccount` | `instagram_accounts` |
| Messenger Account | `messaging.MessengerAccount` | `messenger_accounts` |
| Conversa | `conversations.Conversation` | `conversations` |
| Mensagem | `whatsapp.Message` | `whatsapp_messages` |
| Template WhatsApp | `whatsapp.MessageTemplate` | `whatsapp_templates` |
| Campanha | `campaigns.Campaign` | `campaigns` |
| Mensagem Agendada | `automation.ScheduledMessage` | `scheduled_messages` |
| Perfil Empresa | `automation.CompanyProfile` | `company_profiles` |
| Produto | `stores.StoreProduct` | `store_products` |
| Pedido | `stores.StoreOrder` | `store_orders` |
| Cliente | `stores.StoreCustomer` | `store_customers` |

---

## 4. ESTRUTURA ALVO (CLEAN ARCHITECTURE)

```
apps/
├── core/                    # Configurações base, usuários, auth
│   ├── models.py           # BaseModel, User
│   └── ...
├── stores/                  # Lojas, produtos, pedidos, pagamentos
│   ├── models/
│   │   ├── base.py         # Store, StoreIntegration, StoreWebhook
│   │   ├── product.py      # StoreProduct, StoreCategory
│   │   ├── order.py        # StoreOrder, StoreOrderItem
│   │   ├── customer.py     # StoreCustomer
│   │   └── payment.py      # StorePayment
│   └── ...
├── messaging/               # Todas as plataformas unificadas
│   ├── models/
│   │   ├── __init__.py
│   │   ├── platform_account.py   # Unificado: WhatsApp, Messenger, Instagram
│   │   ├── conversation.py       # Unificado
│   │   ├── message.py            # Unificado
│   │   └── template.py           # Unificado
│   └── ...
├── marketing/               # Campanhas, automações
│   ├── models/
│   │   ├── campaign.py     # Campanhas (email, WhatsApp, etc)
│   │   ├── template.py     # Templates de marketing
│   │   └── automation.py   # Automações
│   └── ...
├── automation/              # Automação e perfis
│   ├── models/
│   │   ├── company_profile.py
│   │   ├── scheduled_message.py
│   │   ├── auto_message.py
│   │   └── customer_session.py
│   └── ...
├── agents/                  # IA/LLM agents
├── analytics/               # Relatórios consolidados
├── conversations/           # Conversas unificadas (pode ser mergeado com messaging)
├── whatsapp/                # APENAS API clients e webhooks
├── instagram/               # APENAS API clients e webhooks
└── deprecated/              # Apps legados movidos
    ├── commerce/
    ├── messenger/
    ├── messaging_v2/
    ├── marketing_v2/
    └── core_v2/
```

---

## 5. PLANO DE MIGRAÇÃO

### Fase 1: Preparação (Imediato)
1. Criar pasta `deprecated/`
2. Mover apps duplicados para deprecated (sem deletar)
3. Criar models unificados em `messaging/models/`

### Fase 2: Unificação de Contas (Semana 1)
1. Criar `messaging.models.PlatformAccount` unificado
2. Criar script de migração de dados
3. Atualizar serializers e views
4. Atualizar frontend

### Fase 3: Unificação de Conversas/Mensagens (Semana 2)
1. Unificar `Conversation` e `Message`
2. Migrar dados históricos
3. Atualizar APIs

### Fase 4: Limpeza (Semana 3)
1. Remover imports de apps deprecated
2. Atualizar admin
3. Testes completos

---

## 6. MODELS UNIFICADOS - ESPECIFICAÇÃO

### 6.1 PlatformAccount (Unificado)

```python
class PlatformAccount(BaseModel):
    class PlatformType(models.TextChoices):
        WHATSAPP = 'whatsapp', 'WhatsApp'
        INSTAGRAM = 'instagram', 'Instagram'
        MESSENGER = 'messenger', 'Messenger'
    
    # Relacionamentos
    store = models.ForeignKey('stores.Store', ...)
    user = models.ForeignKey(User, ...)
    
    # Identificação
    platform = models.CharField(choices=PlatformType.choices)
    name = models.CharField()
    
    # IDs da plataforma
    external_id = models.CharField()  # page_id, instagram_business_id, phone_number_id
    parent_id = models.CharField()    # waba_id, facebook_page_id
    
    # Credenciais (encriptadas)
    access_token_encrypted = models.TextField()
    
    # Status
    status = models.CharField()  # active, inactive, pending, error
    is_verified = models.BooleanField()
    
    # Metadados
    metadata = models.JSONField()  # followers_count, phone_number, etc
    
    # Timestamps
    last_sync_at = models.DateTimeField()
```

### 6.2 UnifiedConversation

```python
class UnifiedConversation(BaseModel):
    # Relacionamentos
    platform_account = models.ForeignKey(PlatformAccount, ...)
    store = models.ForeignKey('stores.Store', ...)
    
    # Identificação
    platform = models.CharField()  # whatsapp, instagram, messenger
    external_id = models.CharField()  # ID na plataforma
    
    # Participante
    customer_phone = models.CharField()
    customer_name = models.CharField()
    customer_profile_pic = models.URLField()
    
    # Status
    is_active = models.BooleanField()
    unread_count = models.IntegerField()
    last_message_at = models.DateTimeField()
```

### 6.3 UnifiedMessage

```python
class UnifiedMessage(BaseModel):
    # Relacionamentos
    conversation = models.ForeignKey(UnifiedConversation, ...)
    
    # Conteúdo
    platform = models.CharField()
    direction = models.CharField()  # inbound, outbound
    message_type = models.CharField()  # text, image, video, etc
    content = models.JSONField()
    text_body = models.TextField()
    
    # IDs externos
    external_id = models.CharField()
    
    # Status
    status = models.CharField()  # pending, sent, delivered, read, failed
    
    # Timestamps
    sent_at = models.DateTimeField()
    delivered_at = models.DateTimeField()
    read_at = models.DateTimeField()
```

---

## 7. AÇÕES IMEDIATAS

### 7.1 Corrigir Erro 500

O erro em `/messaging/messenger/accounts/` pode ser causado por:
1. Serializer tentando acessar campo que não existe
2. Permissão incorreta
3. Queryset errado

**Verificar:**
- `MessengerAccountSerializer` - campos correspondem ao model?
- `MessengerAccountViewSet.get_queryset()` - filtro correto?
- `permission_classes` - usuário autenticado?

### 7.2 Sincronizar Dados do Painel

Criar endpoint que retorna dados de `whatsapp.WhatsAppAccount`:
```python
# Novo endpoint: /api/v1/whatsapp/accounts/
class WhatsAppAccountViewSet(viewsets.ModelViewSet):
    queryset = WhatsAppAccount.objects.all()
    serializer_class = WhatsAppAccountSerializer
    
    def get_queryset(self):
        return self.queryset.filter(owner=self.request.user)
```

### 7.3 Limpar Admin

Remover do admin:
- `messaging_v2` models
- `marketing_v2` models
- `commerce` models (depois de migrar dados)

---

## 8. CHECKLIST DE IMPLEMENTAÇÃO

- [ ] Criar estrutura de pastas para models unificados
- [ ] Criar `PlatformAccount` unificado
- [ ] Criar script de migração de contas
- [ ] Atualizar serializers
- [ ] Atualizar views
- [ ] Atualizar URLs
- [ ] Atualizar frontend
- [ ] Mover apps duplicados para `deprecated/`
- [ ] Atualizar admin.py
- [ ] Testar criação de conta
- [ ] Testar listagem de contas
- [ ] Testar envio de mensagens
- [ ] Verificar dados no painel
