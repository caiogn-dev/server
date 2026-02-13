# ESTADO REAL DO BACKEND - pastita-server

## 📊 RESUMO GERAL

Data da análise: 09/02/2026
Repositório: caiogn-dev/server

---

## ✅ O QUE EXISTE (Já implementado)

### 1. WhatsApp (90% completo)
**Local:** `apps/whatsapp/`

**O que existe:**
- ✅ Models (WhatsAppAccount, Message, WebhookEvent)
- ✅ Webhook service completo
- ✅ API endpoints
- ✅ Celery tasks
- ✅ WebSocket consumers
- ✅ AI Agent integration

**Problema encontrado:**
- ❌ NÃO verifica `agent.is_active` no webhook (linha 373-376 de webhook_service.py)
- ✅ Task verifica corretamente (linha 228-230 de tasks.py)

**Código problemático:**
```python
# apps/whatsapp/services/webhook_service.py (linha 373-376)
if event.account.auto_response_enabled and not message.processed_by_agent:
    if hasattr(event.account, 'default_agent') and event.account.default_agent:
        # ❌ FALTA: and event.account.default_agent.is_active
        current_app.send_task('apps.whatsapp.tasks.process_message_with_agent', ...)
```

---

### 2. Instagram (85% completo)
**Local:** `apps/instagram/`

**O que existe:**
- ✅ Models (InstagramAccount, InstagramConversation, InstagramMessage)
- ✅ API endpoints completos:
  - GET /api/v1/instagram/accounts/
  - GET /api/v1/instagram/conversations/
  - GET /api/v1/instagram/messages/
  - POST /api/v1/instagram/accounts/{id}/sync_conversations/
  - POST /api/v1/instagram/accounts/{id}/sync_profile/
  - POST /api/v1/instagram/typing/
- ✅ Webhook handler
- ✅ OAuth flow

**Endpoints que o frontend espera:**
- ✅ GET /instagram/conversations/?account_id={id}
- ✅ GET /instagram/messages/?conversation_id={id}
- ⚠️ POST /instagram/send-message/ (VERIFICAR se existe)
- ✅ POST /instagram/typing/
- ⚠️ POST /instagram/mark-seen/ (VERIFICAR se existe)

**Status:** Funcional para DM, mas precisa verificar endpoints específicos

---

### 3. Agents (100% completo)
**Local:** `apps/agents/`

**O que existe:**
- ✅ Models (Agent, AgentSession)
- ✅ Langchain integration
- ✅ Service layer
- ✅ API endpoints
- ✅ Status field (is_active)

---

### 4. Conversations (100% completo)
**Local:** `apps/conversations/`

**O que existe:**
- ✅ Models (Conversation, ConversationParticipant)
- ✅ API endpoints
- ✅ WebSocket support
- ❌ Handover/transfer logic

---

## ❌ O QUE NÃO EXISTE (Precisa criar)

### 1. Handover Protocol (0% - NÃO EXISTE)
**Status:** 🚨 CRÍTICO - Não existe

**O que falta:**
- ❌ App `apps/handover/` não existe
- ❌ Models (ConversationHandover, HandoverRequest, HandoverLog)
- ❌ API endpoints (/conversations/{id}/handover/bot/)
- ❌ WebSocket consumers
- ❌ Lógica de transferência Bot ↔ Humano

**Impacto:** 
- Não é possível transferir conversas entre Bot e Humano
- Dashboard mostra controles de handover que não funcionam

**Solução:**
Copiar arquivos de `docs/` do frontend:
```bash
mkdir -p apps/handover
cp docs/backend_handover_*.py apps/handover/
# Renomear arquivos e ajustar imports
# Adicionar a INSTALLED_APPS
# Migrar
```

---

### 2. Messenger (0% - NÃO EXISTE)
**Status:** 🚨 CRÍTICO - Não existe

**O que falta:**
- ❌ App `apps/messenger/` não existe
- ❌ Models (MessengerAccount, MessengerConversation, MessengerMessage)
- ❌ API endpoints (/messenger/accounts/, /messenger/conversations/)
- ❌ Webhook handler
- ❌ Broadcast/Sponsored messages

**Impacto:**
- Frontend tem interface completa do Messenger
- Mas backend não tem endpoints para atender
- Messenger inbox não vai funcionar

**Solução:**
Copiar arquivos de `docs/` do frontend:
```bash
mkdir -p apps/messenger
cp docs/backend_messenger_views.py apps/messenger/views.py
# Criar models.py, serializers.py, urls.py
# Adicionar a INSTALLED_APPS
# Migrar
```

---

## 🔧 FIXES NECESSÁRIOS

### Fix 1: Agente respondendo quando inativo (CRÍTICO)
**Arquivo:** `apps/whatsapp/services/webhook_service.py`
**Linha:** 373-376

**Código atual (PROBLEMÁTICO):**
```python
if event.account.auto_response_enabled and not message.processed_by_agent:
    try:
        if hasattr(event.account, 'default_agent') and event.account.default_agent:
            current_app.send_task('apps.whatsapp.tasks.process_message_with_agent', ...)
```

**Código correto:**
```python
if event.account.auto_response_enabled and not message.processed_by_agent:
    try:
        agent = event.account.default_agent
        if agent and agent.is_active:  # ✅ ADICIONAR is_active
            current_app.send_task('apps.whatsapp.tasks.process_message_with_agent', ...)
        else:
            logger.info(f"Agente inativo ou não configurado para conta {event.account.id}")
```

---

### Fix 2: Handover Protocol (CRÍTICO)
Criar app completo `apps/handover/`

**Arquivos necessários:**
1. `apps/handover/__init__.py`
2. `apps/handover/apps.py`
3. `apps/handover/models.py` (copiar de docs/backend_handover_models.py)
4. `apps/handover/serializers.py`
5. `apps/handover/views.py`
6. `apps/handover/urls.py`
7. `apps/handover/consumers.py`

**Configuração:**
- Adicionar `'apps.handover'` em `INSTALLED_APPS`
- Adicionar URLs em `config/urls.py`
- Migrar: `python manage.py migrate`

---

### Fix 3: Messenger (CRÍTICO)
Criar app completo `apps/messenger/`

**Arquivos necessários:**
1. `apps/messenger/__init__.py`
2. `apps/messenger/apps.py`
3. `apps/messenger/models.py`
4. `apps/messenger/serializers.py`
5. `apps/messenger/views.py` (copiar de docs/backend_messenger_views.py)
6. `apps/messenger/urls.py`
7. `apps/messenger/consumers.py`

---

## 📋 PRIORIDADES

| Prioridade | Item | Esforço | Impacto |
|------------|------|---------|---------|
| 🚨 P0 | Fix agente inativo | 5 min | Alto |
| 🚨 P0 | Instalar Handover | 2 horas | Alto |
| 🚨 P0 | Criar Messenger | 3 horas | Alto |
| ⚠️ P1 | Verificar Instagram endpoints | 30 min | Médio |
| ⚠️ P1 | Testar integrações | 1 hora | Médio |

---

## 🎯 PRÓXIMOS PASSOS IMEDIATOS

### 1. Corrigir agente inativo (5 minutos)
```bash
# Editar arquivo
vim apps/whatsapp/services/webhook_service.py

# Na linha 375, adicionar verificação de is_active
# Salvar e restartar container
docker-compose restart web
```

### 2. Instalar Handover Protocol (2 horas)
```bash
# Criar estrutura
mkdir -p apps/handover

# Copiar arquivos do docs/ do frontend
# (você precisa fazer upload dos arquivos primeiro)

# Configurar e migrar
python manage.py makemigrations handover
python manage.py migrate
docker-compose restart web
```

### 3. Criar Messenger (3 horas)
```bash
# Criar estrutura
mkdir -p apps/messenger

# Copiar arquivos e configurar
# Similar ao Handover
```

---

## 📝 CONCLUSÃO

**Estado atual:**
- WhatsApp: 90% (só precisa do fix do agente)
- Instagram: 85% (endpoints existem, precisa verificar)
- Handover: 0% (não existe - CRÍTICO)
- Messenger: 0% (não existe - CRÍTICO)

**Para o dashboard funcionar 100%:**
1. ✅ Frontend está completo
2. 🚨 Backend precisa dos fixes acima
3. 🚨 Prioridade máxima: Handover e Messenger

**Todos os arquivos necessários estão em:**
`caiogn-dev/pastita-dash/docs/`
