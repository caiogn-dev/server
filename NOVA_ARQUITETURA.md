# Nova Arquitetura de Mensagens - Documentação

## Visão Geral

Esta documentação descreve a nova arquitetura unificada para mensagens, consolidando WhatsApp, Instagram e Messenger em uma única estrutura consistente.

---

## Estrutura de Apps

```
apps/
├── core/                    # Configurações base, usuários, auth
│   └── models.py           # BaseModel, User
├── stores/                  # Lojas, produtos, pedidos, pagamentos
│   └── models/
│       ├── base.py         # Store, StoreIntegration, StoreWebhook
│       ├── product.py      # StoreProduct, StoreCategory
│       ├── order.py        # StoreOrder, StoreOrderItem
│       ├── customer.py     # StoreCustomer
│       └── payment.py      # StorePayment
├── messaging/               # TODAS as plataformas unificadas
│   ├── models/
│   │   ├── __init__.py
│   │   ├── platform_account.py   # PlatformAccount (WhatsApp, IG, Messenger)
│   │   ├── conversation.py       # UnifiedConversation
│   │   ├── message.py            # UnifiedMessage
│   │   └── template.py           # UnifiedTemplate
│   ├── api/
│   │   ├── views_unified.py      # ViewSets unificados
│   │   └── serializers_unified.py # Serializers unificados
│   └── urls.py
├── marketing/               # Campanhas de marketing
├── automation/              # Automação e perfis
├── agents/                  # IA/LLM agents
├── whatsapp/                # APENAS API clients e webhooks
├── instagram/               # APENAS API clients e webhooks
└── deprecated/              # Apps legados (não usar)
    ├── commerce/
    ├── messenger/
    ├── messaging_v2/
    ├── marketing_v2/
    └── core_v2/
```

---

## Models Unificados

### 1. PlatformAccount

**Arquivo:** `apps/messaging/models/platform_account.py`

**Propósito:** Única fonte de verdade para todas as contas de plataforma de mensagens.

**Substitui:**
- `whatsapp.WhatsAppAccount`
- `instagram.InstagramAccount`
- `messaging.MessengerAccount`
- `messaging_v2.PlatformAccount`
- `stores.StoreIntegration` (para plataformas de mensagem)

**Campos Principais:**
```python
- id: UUID
- user: ForeignKey(User)
- store: ForeignKey(Store) - opcional
- platform: ChoiceField['whatsapp', 'instagram', 'messenger']
- name: CharField
- external_id: CharField - ID na plataforma
- parent_id: CharField - WABA ID, Facebook Page ID
- phone_number: CharField
- access_token_encrypted: TextField
- status: ChoiceField['active', 'inactive', 'pending', 'suspended', 'error']
- is_active: BooleanField
- is_verified: BooleanField
- metadata: JSONField - followers_count, quality_rating, etc
```

**Propriedades Úteis:**
```python
account.is_whatsapp      # True se plataforma é WhatsApp
account.is_instagram     # True se plataforma é Instagram
account.is_messenger     # True se plataforma é Messenger
account.waba_id          # Retorna parent_id para WhatsApp
account.phone_number_id  # Retorna external_id para WhatsApp
account.page_id          # Retorna external_id para Messenger
account.followers_count  # Retorna do metadata
account.access_token     # Propriedade desencriptada
account.masked_token     # Token mascarado para display
```

---

### 2. UnifiedConversation

**Arquivo:** `apps/messaging/models/conversation.py`

**Propósito:** Única fonte de verdade para todas as conversas.

**Substitui:**
- `conversations.Conversation`
- `messaging.MessengerConversation`
- `instagram.InstagramConversation`

**Campos Principais:**
```python
- id: UUID
- platform_account: ForeignKey(PlatformAccount)
- store: ForeignKey(Store) - opcional
- platform: ChoiceField['whatsapp', 'instagram', 'messenger']
- external_id: CharField - ID da conversa na plataforma
- customer_phone: CharField - Número/ID do cliente
- customer_name: CharField
- customer_platform_id: CharField - PSID, IGSID
- status: ChoiceField['active', 'archived', 'blocked']
- unread_count: IntegerField
- assigned_to: ForeignKey(User) - opcional
- last_message_at: DateTimeField
- last_message_preview: TextField
```

**Métodos Úteis:**
```python
conversation.mark_read()           # Marca como lida
conversation.increment_unread()    # Incrementa não lidas
conversation.update_last_message(preview, timestamp)
conversation.assign_to(user)       # Atribui a usuário
conversation.unassign()            # Remove atribuição
```

---

### 3. UnifiedMessage

**Arquivo:** `apps/messaging/models/message.py`

**Propósito:** Única fonte de verdade para todas as mensagens.

**Substitui:**
- `whatsapp.Message`
- `messaging.MessengerMessage`
- `instagram.InstagramMessage`
- `messaging_v2.UnifiedMessage`

**Campos Principais:**
```python
- id: UUID
- conversation: ForeignKey(UnifiedConversation)
- platform_account: ForeignKey(PlatformAccount)
- platform: ChoiceField['whatsapp', 'instagram', 'messenger']
- direction: ChoiceField['inbound', 'outbound']
- message_type: ChoiceField['text', 'image', 'video', 'audio', ...]
- text_body: TextField
- content: JSONField - Conteúdo estruturado
- media_url: URLField
- template_name: CharField
- external_id: CharField - ID da mensagem na plataforma
- status: ChoiceField['pending', 'sent', 'delivered', 'read', 'failed']
- sent_at, delivered_at, read_at, failed_at: DateTimeFields
- error_code, error_message: Campos de erro
- processed_by_agent: BooleanField
- source: CharField - 'manual', 'automation', 'campaign', 'api', 'webhook'
```

**Métodos Úteis:**
```python
message.mark_sent(external_id)
message.mark_delivered()
message.mark_read()
message.mark_failed(error_code, error_message)
message.mark_processed_by_agent(agent_id)
```

---

### 4. UnifiedTemplate

**Arquivo:** `apps/messaging/models/template.py`

**Propósito:** Templates de mensagem unificados.

**Substitui:**
- `whatsapp.MessageTemplate`
- `messaging_v2.MessageTemplate`
- `marketing_v2.Template`

**Campos Principais:**
```python
- id: UUID
- platform_account: ForeignKey(PlatformAccount) - opcional
- name: CharField
- platform: ChoiceField['whatsapp', 'instagram', 'messenger', 'email', 'sms']
- template_type: ChoiceField['standard', 'carousel', 'lto', 'auth', 'order', 'catalog']
- external_id: CharField - ID do template na plataforma
- language: CharField - default 'pt_BR'
- category: ChoiceField['marketing', 'utility', 'authentication', 'custom']
- status: ChoiceField['draft', 'pending', 'approved', 'rejected', 'paused']
- header: JSONField - Cabeçalho
- body: TextField - Corpo com {{variáveis}}
- footer: TextField
- buttons: JSONField - Definição de botões
- components: JSONField - Formato completo da API Meta
- variables: JSONField - Lista de variáveis
```

**Métodos Úteis:**
```python
template.render(variables)              # Renderiza com variáveis
template.get_components_for_api()       # Retorna formato API
template.mark_approved(external_id)
template.mark_rejected(reason)
template.mark_submitted()
```

---

## API Endpoints

### Base URL
```
/api/v1/messaging/v2/   # NOVO - API Unificada (recomendado)
/api/v1/messaging/      # LEGADO - Será removido
```

### PlatformAccount Endpoints

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/accounts/` | Listar contas do usuário |
| POST | `/accounts/` | Criar nova conta |
| GET | `/accounts/{id}/` | Detalhes da conta |
| PUT | `/accounts/{id}/` | Atualizar conta |
| PATCH | `/accounts/{id}/` | Atualização parcial |
| DELETE | `/accounts/{id}/` | Deletar conta |
| POST | `/accounts/{id}/sync/` | Sincronizar com plataforma |
| POST | `/accounts/{id}/verify_webhook/` | Verificar webhook |
| POST | `/accounts/{id}/rotate_token/` | Rotacionar token |
| GET | `/accounts/stats/` | Estatísticas de contas |

**Exemplo - Criar Conta WhatsApp:**
```json
POST /api/v1/messaging/v2/accounts/
{
    "platform": "whatsapp",
    "name": "Minha Loja",
    "external_id": "123456789",
    "parent_id": "987654321",
    "phone_number": "5511999999999",
    "display_phone_number": "+55 11 99999-9999",
    "access_token": "EAA...",
    "webhook_verify_token": "meu_token"
}
```

**Exemplo - Resposta:**
```json
{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "platform": "whatsapp",
    "platform_display": "WhatsApp",
    "name": "Minha Loja",
    "external_id": "123456789",
    "parent_id": "987654321",
    "phone_number": "5511999999999",
    "display_phone_number": "+55 11 99999-9999",
    "status": "pending",
    "status_display": "Pending Verification",
    "is_active": true,
    "is_verified": false,
    "masked_token": "EAA...xxx",
    "created_at": "2024-01-01T00:00:00Z"
}
```

---

### Conversation Endpoints

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/conversations/` | Listar conversas |
| GET | `/conversations/{id}/` | Detalhes da conversa |
| POST | `/conversations/{id}/mark_read/` | Marcar como lida |
| POST | `/conversations/{id}/assign/` | Atribuir a usuário |
| GET | `/conversations/{id}/messages/` | Listar mensagens |
| POST | `/conversations/{id}/send_message/` | Enviar mensagem |

**Filtros Disponíveis:**
- `?platform=whatsapp` - Filtrar por plataforma
- `?status=active` - Filtrar por status
- `?assigned_to={user_id}` - Filtrar por atribuição
- `?search=termo` - Buscar por nome/telefone

**Exemplo - Enviar Mensagem:**
```json
POST /api/v1/messaging/v2/conversations/{id}/send_message/
{
    "text": "Olá! Como posso ajudar?",
    "type": "text"
}
```

---

### Message Endpoints

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/messages/` | Listar mensagens |
| GET | `/messages/{id}/` | Detalhes da mensagem |

**Filtros Disponíveis:**
- `?conversation={id}` - Filtrar por conversa
- `?direction=inbound` - Entrada/Saída
- `?status=sent` - Status da mensagem
- `?message_type=text` - Tipo de mensagem

---

### Template Endpoints

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/templates/` | Listar templates |
| POST | `/templates/` | Criar template |
| GET | `/templates/{id}/` | Detalhes do template |
| PUT | `/templates/{id}/` | Atualizar template |
| DELETE | `/templates/{id}/` | Deletar template |
| POST | `/templates/{id}/submit/` | Submeter para aprovação |
| POST | `/templates/{id}/render/` | Renderizar com variáveis |

**Exemplo - Criar Template:**
```json
POST /api/v1/messaging/v2/templates/
{
    "platform_account": "550e8400-e29b-41d4-a716-446655440000",
    "name": "boas_vindas",
    "platform": "whatsapp",
    "language": "pt_BR",
    "category": "utility",
    "body": "Olá {{nome}}! Bem-vindo à {{loja}}.",
    "variables": ["nome", "loja"]
}
```

---

## Migração de Dados

### Script de Migração

**Arquivo:** `scripts/migrate_platform_accounts.py`

**O que faz:**
1. Migra `whatsapp.WhatsAppAccount` → `PlatformAccount`
2. Migra `instagram.InstagramAccount` → `PlatformAccount`
3. Migra `messaging.MessengerAccount` → `PlatformAccount`
4. Migra `stores.StoreIntegration` (mensagens) → `PlatformAccount`

**Como executar:**
```bash
# Via Django runscript
python manage.py runscript migrate_platform_accounts

# Ou diretamente
python scripts/migrate_platform_accounts.py
```

**Verificação:**
```bash
# Verificar contas migradas
python manage.py shell -c "
from apps.messaging.models import PlatformAccount
print(f'Total: {PlatformAccount.objects.count()}')
print(f'WhatsApp: {PlatformAccount.objects.filter(platform=\"whatsapp\").count()}')
print(f'Instagram: {PlatformAccount.objects.filter(platform=\"instagram\").count()}')
print(f'Messenger: {PlatformAccount.objects.filter(platform=\"messenger\").count()}')
"
```

---

## Guia de Atualização para Desenvolvedores

### 1. Atualizar Imports

**Antes:**
```python
from apps.whatsapp.models import WhatsAppAccount
from apps.instagram.models import InstagramAccount
from apps.messaging.models import MessengerAccount
```

**Depois:**
```python
from apps.messaging.models import PlatformAccount

# Filtrar por plataforma
whatsapp_accounts = PlatformAccount.objects.filter(platform='whatsapp')
instagram_accounts = PlatformAccount.objects.filter(platform='instagram')
```

### 2. Atualizar Queries

**Antes:**
```python
# WhatsApp
account = WhatsAppAccount.objects.get(phone_number_id='123')
messages = account.messages.all()

# Instagram
account = InstagramAccount.objects.get(instagram_business_id='456')
conversations = account.conversations.all()
```

**Depois:**
```python
# Todas as plataformas
account = PlatformAccount.objects.get(external_id='123')
messages = account.messages.all()
conversations = account.conversations.all()

# Verificar plataforma
if account.is_whatsapp:
    # Lógica específica WhatsApp
    waba_id = account.waba_id
elif account.is_instagram:
    # Lógica específica Instagram
    pass
```

### 3. Atualizar Criação

**Antes:**
```python
WhatsAppAccount.objects.create(
    name='Minha Loja',
    phone_number_id='123',
    waba_id='456',
    phone_number='5511999999999',
    owner=user,
)
```

**Depois:**
```python
PlatformAccount.objects.create(
    platform='whatsapp',
    name='Minha Loja',
    external_id='123',
    parent_id='456',
    phone_number='5511999999999',
    user=user,
)
```

---

## Configuração do Django

### INSTALLED_APPS

```python
INSTALLED_APPS = [
    # Core
    'apps.core',
    'apps.users',
    'apps.stores',
    
    # Messaging (NOVO - unificado)
    'apps.messaging',
    
    # Platform APIs (apenas clients/webhooks)
    'apps.whatsapp',
    'apps.instagram',
    
    # Outros
    'apps.marketing',
    'apps.automation',
    'apps.agents',
    'apps.conversations',  # Será gradualmente migrado para messaging
    
    # REMOVER daqui para frente:
    # 'apps.commerce',       # -> deprecated
    # 'apps.messenger',      # -> deprecated (merge com messaging)
    # 'apps.messaging_v2',   # -> deprecated
    # 'apps.marketing_v2',   # -> deprecated
    # 'apps.core_v2',        # -> deprecated
]
```

---

## Troubleshooting

### Erro: "Table 'platform_accounts' doesn't exist"

**Solução:**
```bash
python manage.py migrate messaging
```

### Erro: "Duplicate entry for key 'unique_platform_external_id'"

**Causa:** Tentando criar conta com mesmo external_id já existente.

**Solução:**
```python
# Verificar se já existe
if PlatformAccount.objects.filter(
    platform='whatsapp',
    external_id='123'
).exists():
    # Atualizar existente ou retornar erro
    pass
```

### Dados não aparecem no painel

**Verificar:**
1. Migração foi executada?
   ```bash
   python scripts/migrate_platform_accounts.py
   ```

2. Frontend está usando endpoint correto?
   - NOVO: `/api/v1/messaging/v2/accounts/`
   - LEGADO: `/api/v1/messaging/messenger/accounts/` (deprecado)

3. Permissões do usuário:
   ```python
   # Verificar se usuário é owner das contas
   PlatformAccount.objects.filter(user=request.user)
   ```

---

## Roadmap

### Fase 1: Migração (Atual)
- ✅ Criar models unificados
- ✅ Criar serializers e views
- ✅ Criar script de migração
- ⏳ Executar migração de dados
- ⏳ Atualizar frontend

### Fase 2: Transição (Próxima)
- ⏳ Mover apps duplicados para deprecated
- ⏳ Atualizar todos os imports
- ⏳ Remover referências a models antigos
- ⏳ Atualizar documentação

### Fase 3: Limpeza (Futuro)
- ⏳ Deletar apps deprecated
- ⏳ Remover tabelas antigas do banco
- ⏳ Otimizar queries

---

## Contato

Para dúvidas ou problemas com a migração, consulte:
- Documentação completa: `ANALISE_DUPLICIDADES.md`
- Script de migração: `scripts/migrate_platform_accounts.py`
- Models unificados: `apps/messaging/models/`
