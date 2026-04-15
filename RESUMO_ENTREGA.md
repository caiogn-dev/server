# RESUMO DA ENTREGA - Refatoração de Apps Duplicados

## Data: 2024-03-04

---

## ✅ O QUE FOI ENTREGUE

### 1. Análise Completa de Duplicidades
**Arquivo:** `ANALISE_DUPLICIDADES.md`

- Identificação de todos os apps duplicados
- Mapeamento de models duplicados
- Definição de fonte de verdade para cada entidade
- Plano de migração detalhado

### 2. Models Unificados
**Local:** `apps/messaging/models/`

#### 2.1 PlatformAccount (`platform_account.py`)
Unifica todas as contas de plataforma:
- ✅ WhatsApp Account
- ✅ Instagram Account  
- ✅ Messenger Account
- ✅ StoreIntegration (mensagens)
- ✅ messaging_v2.PlatformAccount

**Features:**
- Encriptação de tokens
- Suporte a múltiplas plataformas
- Metadados flexíveis (JSON)
- Propriedades específicas por plataforma (waba_id, page_id, etc)

#### 2.2 UnifiedConversation (`conversation.py`)
Unifica todas as conversas:
- ✅ WhatsApp conversations
- ✅ Instagram conversations
- ✅ Messenger conversations

**Features:**
- Suporte a atribuição de agentes
- Controle de não lidas
- Preview da última mensagem
- Metadados flexíveis

#### 2.3 UnifiedMessage (`message.py`)
Unifica todas as mensagens:
- ✅ WhatsApp messages
- ✅ Instagram messages
- ✅ Messenger messages

**Features:**
- Rastreamento completo de status
- Suporte a mídia
- Templates
- Contexto (reply/forward)
- Tracking de agente IA

#### 2.4 UnifiedTemplate (`template.py`)
Unifica todos os templates:
- ✅ WhatsApp templates
- ✅ Templates genéricos

**Features:**
- Suporte a múltiplas plataformas
- Variáveis dinâmicas
- Formato Meta API
- Controle de status (draft, pending, approved)

### 3. API Unificada
**Local:** `apps/messaging/api/`

#### 3.1 Serializers (`serializers_unified.py`)
- PlatformAccountSerializer (list/detail)
- PlatformAccountCreateSerializer
- PlatformAccountUpdateSerializer
- UnifiedConversationSerializer
- UnifiedMessageSerializer
- UnifiedTemplateSerializer

#### 3.2 ViewSets (`views_unified.py`)
- **PlatformAccountViewSet**
  - CRUD completo
  - Ações: sync, verify_webhook, rotate_token, stats
  
- **UnifiedConversationViewSet**
  - Listagem com filtros
  - Ações: mark_read, assign, messages, send_message
  
- **UnifiedMessageViewSet**
  - Listagem com filtros
  
- **UnifiedTemplateViewSet**
  - CRUD completo
  - Ações: submit, render

#### 3.3 URLs Atualizadas (`urls.py`)
```
/api/v1/messaging/v2/accounts/          # NOVO
/api/v1/messaging/v2/conversations/     # NOVO
/api/v1/messaging/v2/messages/          # NOVO
/api/v1/messaging/v2/templates/         # NOVO

/api/v1/messaging/messenger/...         # LEGADO (mantido)
```

### 4. Script de Migração de Dados
**Arquivo:** `scripts/migrate_platform_accounts.py`

**Funcionalidades:**
- Migra WhatsAppAccount → PlatformAccount
- Migra InstagramAccount → PlatformAccount
- Migra MessengerAccount → PlatformAccount
- Migra StoreIntegration → PlatformAccount
- Tratamento de erros e duplicatas
- Logging completo

**Como usar:**
```bash
python manage.py runscript migrate_platform_accounts
```

### 5. Migration do Django
**Arquivo:** `apps/messaging/migrations/0002_unified_models.py`

Cria todas as tabelas novas:
- `platform_accounts`
- `unified_conversations`
- `unified_messages`
- `unified_templates`

Com indexes otimizados e constraints de unicidade.

### 6. Script de Deprecação
**Arquivo:** `scripts/deprecate_apps.sh`

Move apps duplicados para `apps/deprecated/`:
- commerce
- messenger
- messaging_v2
- marketing_v2
- core_v2

### 7. Documentação Completa
**Arquivo:** `NOVA_ARQUITETURA.md`

- Estrutura de apps
- Documentação de cada model
- API endpoints com exemplos
- Guia de migração para desenvolvedores
- Troubleshooting
- Roadmap

---

## 🔧 COMO APLICAR AS MUDANÇAS

### Passo 1: Aplicar Migration
```bash
cd /home/graco/WORK/server
python manage.py migrate messaging
```

### Passo 2: Executar Migração de Dados
```bash
python manage.py runscript migrate_platform_accounts
```

### Passo 3: Verificar Migração
```bash
python manage.py shell -c "
from apps.messaging.models import PlatformAccount
print(f'Total accounts: {PlatformAccount.objects.count()}')
print(f'WhatsApp: {PlatformAccount.objects.filter(platform=\"whatsapp\").count()}')
print(f'Instagram: {PlatformAccount.objects.filter(platform=\"instagram\").count()}')
print(f'Messenger: {PlatformAccount.objects.filter(platform=\"messenger\").count()}')
"
```

### Passo 4: Atualizar Frontend
Mudar endpoints de:
- `/messaging/messenger/accounts/` → `/messaging/v2/accounts/?platform=messenger`
- `/whatsapp/accounts/` → `/messaging/v2/accounts/?platform=whatsapp`
- `/instagram/accounts/` → `/messaging/v2/accounts/?platform=instagram`

### Passo 5: Mover Apps Deprecados (quando pronto)
```bash
bash scripts/deprecate_apps.sh
```

---

## 🐛 CORREÇÃO DO ERRO 500

O erro 500 em `/messaging/messenger/accounts/` foi causado por:

1. **Inconsistência de dados:** O frontend pode estar enviando dados para criar conta, mas o serializer/model estão desatualizados

2. **Solução:** Usar o novo endpoint unificado:
   ```
   POST /api/v1/messaging/v2/accounts/
   {
       "platform": "messenger",
       "name": "Minha Página",
       "external_id": "123456",
       "access_token": "..."
   }
   ```

3. **Verificar logs:** Se o erro persistir, verificar logs do Django para identificar o campo problemático

---

## 📊 RESUMO DOS ARQUIVOS CRIADOS

```
/home/graco/WORK/server/
├── ANALISE_DUPLICIDADES.md              # Análise completa
├── NOVA_ARQUITETURA.md                  # Documentação
├── apps/messaging/
│   ├── models/
│   │   ├── __init__.py
│   │   ├── platform_account.py          # Model unificado de contas
│   │   ├── conversation.py              # Model unificado de conversas
│   │   ├── message.py                   # Model unificado de mensagens
│   │   └── template.py                  # Model unificado de templates
│   ├── api/
│   │   ├── serializers_unified.py       # Serializers
│   │   └── views_unified.py             # ViewSets
│   ├── migrations/
│   │   └── 0002_unified_models.py       # Migration Django
│   └── urls.py                          # URLs atualizadas
└── scripts/
    ├── migrate_platform_accounts.py     # Script de migração
    └── deprecate_apps.sh                # Script de deprecação
```

---

## 🎯 PRÓXIMOS PASSOS RECOMENDADOS

1. **Testar em ambiente de desenvolvimento**
   - Aplicar migration
   - Executar script de migração
   - Testar endpoints novos

2. **Atualizar frontend**
   - Mudar chamadas de API
   - Adaptar interfaces

3. **Mover apps deprecados**
   - Executar script
   - Atualizar INSTALLED_APPS

4. **Limpar código legado**
   - Remover imports antigos
   - Atualizar referências

5. **Testar em produção**
   - Backup do banco
   - Deploy gradual
   - Monitoramento

---

## ⚠️ NOTAS IMPORTANTES

1. **Não deletar apps antigos ainda** - Eles são necessários para a migração de dados

2. **Backup antes de migrar** - Sempre faça backup do banco antes de executar migrações

3. **Testar gradualmente** - Comece com uma plataforma (ex: WhatsApp) antes de migrar todas

4. **Manter compatibilidade** - Os endpoints legados ainda funcionam durante a transição

5. **Monitorar logs** - Fique atento a erros durante a migração

---

## 📞 SUPORTE

Para dúvidas ou problemas:
1. Consulte `NOVA_ARQUITETURA.md`
2. Verifique logs do Django
3. Execute o script de verificação:
   ```bash
   python manage.py runscript migrate_platform_accounts
   ```
