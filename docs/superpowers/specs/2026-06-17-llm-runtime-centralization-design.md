# Spec — Centralização e Modularização da Camada LLM/Bot (server2)

**Data:** 2026-06-17
**Objetivo:** Matar o cérebro Langchain legado, unificar 100% no LangGraph, e modularizar contexto/tools/memória/prompts num pacote limpo — com o **mínimo de código** e **zero regressão** no fluxo de WhatsApp (receita).

Baseado em: `docs/MESSAGING_BOT_ARCHITECTURE.md` + 3 descobertas exaustivas (callers, contexto/tools/memória, orquestrador/chat/intent) — jun/2026.

---

## 1. Estado atual (a bagunça)

- **2 cérebros vivos:** caminho GRAFO (LangGraph, vivo no WhatsApp) e caminho LEGADO (`LangchainService.process_message`, loop manual) — alcançado por 4 vias: fallback do webhook, Instagram, Messenger, endpoint REST de teste.
- **1 god-class:** `LangchainService` (1830 linhas) faz LLM + tools + contexto + memória, e o LangGraph **reusa** ela (`LangGraphService._lc`). "Legado" e "compartilhado" estão entrelaçados no mesmo arquivo.
- **Duplicação:** menu construído 3x, entrega 3x, prompts/guardrails 2x (CONDUTA vs REGRAS ABSOLUTAS), get-or-create de conversa 3x, 2 LLM clients (agente + detector de intenção).
- **Divergências/bugs:** grafo ignora `agent.system_prompt`; `agent.persona_name` não existe; gate de provider str vs enum; `_resolve_allowed_tools` (narrowing de tools) só no legado; IG/Messenger furam o UnifiedService (sem intents/handlers/templates/guardrails); thread daemon com timeout que não cancela → **risco de resposta dupla**.
- **Crítico:** o contexto de **carrinho/PIX/último-pedido** existe **só** no legado (`_build_dynamic_context:852-984`); o grafo não injeta isso. Deletar o legado sem portar = bot perde o carrinho.

## 2. Arquitetura-alvo

Um pacote novo **`apps/agents/runtime/`** (módulos pequenos, 1 responsabilidade, interface clara, testáveis isolados). Pipeline final:

```
inbound (WhatsApp/IG/Messenger) → UnifiedService.process_message (orquestrador único)
   → [intents/handlers/handover/auto-message: colaboradores, não absorvidos]
   → AgentRuntime.process_message (cérebro único = grafo LangGraph)
        → runtime.factory (LLM client cacheado)
        → runtime.context (builder único: store/menu/cliente/knowledge/sessão+PIX)
        → runtime.prompts (system prompt único, honra agent.system_prompt)
        → runtime.tools (11 tools + 1 tool-gate)
        → runtime.memory (Redis history + AgentConversation)
        → runtime.graph (StateGraph compilado 1x/agent)
   → outbound (adapters por canal)
```

| Módulo | Vira (folds in) |
|---|---|
| `runtime/factory.py` | `_create_llm` + `_create_redis_client` (langchain:48,43); absorve o client NVIDIA do detector (detector.py:302); fonte única de provider/base-url (mata a triplicação em views.py:213) |
| `runtime/context.py` | `_build_customer_context` (339), `_get_store_for_context` (1429), `_catalog_summary`/`_delivery_summary`/`_load_knowledge_context` (nodes), **+ PORTAR** carrinho/PIX/último-pedido (`_build_dynamic_context:852-984`). Menu→1, entrega→1. |
| `runtime/prompts.py` | `_SYSTEM_TEMPLATE`+`_build_system_prompt` (nodes:88-189) **merge com agent.system_prompt/context_prompt** (fix bug); intent prompt (detector:271). Deleta bloco CONDUTA (langchain:747-760). |
| `runtime/tools.py` | `_build_tools` (997-1427) + `_get_pending_pix_payment` (609); 1 loop de execução (o do grafo: max iters + confirmation guard + safe-error); `_resolve_allowed_tools` (593) vira **node do grafo** (fecha o gap). |
| `runtime/memory.py` | `_get_memory` (165) + load/save único (colapsa langgraph_service vs legado); helper de `AgentConversation` exposto p/ todos os canais. |
| `runtime/graph.py` | grafo atual (`build_agent_graph`, nodes, state) — o único caminho. |
| `runtime/service.py` | `AgentRuntime.process_message(...)` — entrada única (substitui `LangGraphService` + `LangchainService.process_message` + `AgentService.get_agent_response`). |

## 3. KEEP / DELETE / REPOINT / FIX (o veredito)

### KEEP — necessário pra funcionar (vira módulo ou colaborador)
- Helpers compartilhados: `_create_llm`, `_create_redis_client`, `_build_customer_context`, `_get_store_for_context`, `_build_tools`, `_get_pending_pix_payment`, `_get_memory` → movem pros módulos `runtime/*`.
- Grafo (`agents/graph/`), `_catalog_summary`/`_delivery_summary`/`_load_knowledge_context`, `_SYSTEM_TEMPLATE`/`_build_system_prompt`.
- **PORTAR (não deletar):** estado de carrinho/PIX/último-pedido de `_build_dynamic_context:852-984` → `runtime/context.py`.
- Colaboradores (mantidos onde estão, orquestrador chama): `IntentDetector` + 17 handlers (`whatsapp/intents/`), `apps/handover` (orquestrador lê o estado), `AutoMessage`/`ScheduledMessage`/`CustomerSession` + tasks agendadas, os 4 modelos de conversa (channel-specific), adapters de envio por canal.
- `UnifiedService.process_message` (o orquestrador de 9 passos) — fica como orquestrador único.
- legacy_tasks.py: **mover** `process_pending_webhook_events` + `retry_failed_webhook_events` (VIVAS, no Beat) p/ outro arquivo antes de apagar o legacy_tasks.py.

### DELETE — morto/duplicado (após repoint/porte)
- `LangchainService.process_message` (loop manual, 1451-1694) + `_build_dynamic_context` (666, após portar carrinho/PIX) + bloco CONDUTA (747-760) + menu/entrega duplicados (763-807).
- `LangchainService.process_message_stream` (1746) — **morto, deletar já**.
- `AgentService.get_agent_response` (após repoint) — `create_order_from_conversation` (sem LLM) fica.
- `FlowExecutor` + `AgentFlow`/`FlowSession`/`FlowExecutionLog` + stub 501 — morto. **DECISÃO: deletar** (não é roadmap).
- `ProductNotFoundHandler` (catalog.py:276) — fora do HANDLER_MAP.
- legacy_tasks.py: `send_message_async`, `send_campaign_message`, `schedule_campaign_messages` (import-only).
- Delegators deprecados (`automation/tasks/__init__.py:54,108`).

### REPOINT — pro caminho único (`UnifiedService` → `AgentRuntime`)
- `instagram/tasks.py:13` e `messaging/tasks.py:13` (IG/Messenger) → `UnifiedService` (ganham intents/handlers/templates/guardrails — fim da maior divergência).
- `webhook_service.py:790` fallback → re-entra pelo UnifiedService (ou removido) → mata o 2º cérebro.
- `agents/views.py` process/history/clear_memory → `AgentRuntime` (e cria AgentConversation p/ paridade de memória).
- get-or-create de conversa: `WebhookService`/`MessageService` → `ConversationService.get_or_create_conversation`. contact_name → 1 helper.

### FIX — corrigir no caminho (estrutural + correções, conforme decidido)
- Grafo passa a honrar `agent.system_prompt`/`context_prompt` (bug: hoje só IG/Messenger/REST respeitam).
- `agent.persona_name`: **DECISÃO: adicionar campo `persona_name` no model Agent** (+ migration) p/ nomear a persona pelo dash.
- Gate de provider unificado (str).
- `_resolve_allowed_tools` aplicado no grafo (fecha gap de guardrail).
- **Resposta dupla:** colapsar `_run_orchestrator_with_timeout` (thread daemon) + fallback num caminho único guardado (flag Redis atômica ou Celery soft-timeout).
- **Perf:** cachear grafo+LLM client por `agent.id`; cachear contexto store/menu/knowledge por `store.id`/conversa (TTL); LLM fora da `@transaction.atomic`; memória Redis 1 conexão + leitura limitada.

## 4. Migração (strangler, incremental, cada passo PROVADO)

1. **Extrair módulos** `runtime/factory|context|tools|memory|prompts` a partir de `LangchainService` — comportamento preservado. Provar com **harness diferencial** (estilo geo): mesmo input → mesma saída (contexto, tools, prompt, payload).
2. **Portar** carrinho/PIX/último-pedido pro `runtime/context.py` e ligar no grafo (o grafo passa a ter paridade com o legado). Provar paridade de contexto.
3. **`runtime/service.py`** (`AgentRuntime`) repontando o grafo pros módulos novos. UnifiedService passa a chamar `AgentRuntime`.
4. **Repoint** IG, Messenger, fallback, agents/views → `AgentRuntime`/UnifiedService.
5. **Deletar** legado (process_message loop, _build_dynamic_context, stream, AgentService.get_agent_response, blocos duplicados) — só depois que os substitutos estão provados e sem callers.
6. **FIX** aplicados (system_prompt, narrowing, double-send guard, cache, LLM-fora-da-transação) — cada um verificado.
7. Limpeza: mover tasks vivas do legacy_tasks.py, deletar mortos, FlowExecutor (se confirmado).

## 5. Verificação
- Harness diferencial por módulo extraído (original vs novo, byte-a-byte) antes de deletar qualquer legado.
- Suíte de testes existente do whatsapp/agents verde em cada passo.
- Nova suíte `apps/agents/runtime/tests/` (characterization de contexto/tools/prompt/memória).
- Nada deletado enquanto houver caller; `grep` de callers a cada deleção.

## 6. Riscos
- Perder contexto de carrinho/PIX (mitigado: portar antes de deletar — passo 2).
- Mudar comportamento do bot ao unificar prompts (mitigado: merge agent.system_prompt + diferencial).
- IG/Messenger ganham guardrails/handlers que não tinham (mudança de comportamento *intencional* — validar com user).
- Deploy: imagem baked; mudanças só ativam no deploy do user. Migrations (persona_name) concurrent se em tabela grande.

## 7. Fora de escopo (agora)
- Reescrever o grafo LangGraph em si (mantemos o atual).
- Unificar os 4 modelos de conversa (channel-specific, ok).
