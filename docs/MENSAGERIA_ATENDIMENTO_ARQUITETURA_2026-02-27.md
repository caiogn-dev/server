# Arquitetura de Mensageria, Atendimento e Automação

## Escopo
- `server/apps/whatsapp`
- `server/apps/messaging`
- `server/apps/conversations`
- `server/apps/handover`
- `server/apps/automation`
- `server/apps/agents`
- `server/apps/stores`
- `pastita-dash/src/pages/automation`
- `pastita-dash/src/pages/conversations`
- `pastita-dash/src/services/{automation,conversations,handover,whatsapp}`

## Diagnóstico técnico

### Problemas estruturais confirmados
- `Store` já possui praticamente todos os dados de negócio, mas `CompanyProfile` ainda aparece como pseudo-fonte de verdade em vários fluxos.
- O contexto operacional fica espalhado entre `Store`, `WhatsAppAccount`, `Conversation`, `CompanyProfile` e `CustomerSession`, sem um resolvedor canônico.
- `Conversation.mode` e o app dedicado de `handover` evoluem separados, o que gera divergência entre estado visual e estado operacional.
- O frontend trata `CompanyProfile` como entidade principal, quando na prática ele deveria ser uma camada de automação da loja.
- Existem duplicações perigosas no backend:
  - `ConversationHandover` em `apps/conversations/models.py` e `apps/handover/models.py`
  - `AgentFlow`/`FlowSession`/`FlowExecutionLog` em `apps/automation/models.py` e `apps/automation/models/flow.py`
- O fluxo de criação de perfil no frontend estava quebrado: `/automation/companies/new` abria a tela de detalhe, mas só existia lógica de update.

### Efeito prático
- Alto risco de inconsistência entre atendimento humano/bot.
- Sessões e automações podem resolver o contexto errado da empresa/loja.
- Refatorações ficam caras porque o mesmo conceito aparece em mais de um app.
- UX ruim porque a interface expõe objetos intermediários em vez da entidade de negócio principal.

## Arquitetura alvo

### Fonte de verdade
- `Store`: entidade principal de negócio.
- `WhatsAppAccount` / demais contas de canal: adaptadores de canal ligados ao negócio.
- `CompanyProfile`: manter por compatibilidade, mas tratá-lo como `AutomationProfile` lógico.
  - Papel: configurações de automação.
  - Não deve duplicar identidade da empresa quando houver `store` vinculado.

### Entidades canônicas
- `Store`: marca, operação, catálogo, logística, cobrança, identidade.
- `ChannelAccount`: conta do canal (`WhatsAppAccount`, `MessengerAccount`, etc.).
- `Conversation`: sessão de atendimento por canal/contato.
- `ConversationHandover`: estado canônico de ownership bot/humano.
- `CustomerSession`: contexto transacional do cliente durante pedido/pagamento.
- `AutoMessage`: templates e regras automatizadas.
- `ScheduledMessage`: fila unificada de envio futuro.
- `Agent`: capacidade de IA.
- `AgentFlow`: fluxo visual/orquestração de atendimento.

### Regras de ownership
- Dados de negócio: `Store`
- Configuração de automação: `CompanyProfile`
- Estado de conversa: `Conversation`
- Ownership de atendimento: `apps.handover.ConversationHandover`
- Contexto transacional de cliente: `CustomerSession`
- Execução de IA: `Agent` + `AgentConversation`

## Plano de execução

### Fase 1
- Introduzir resolvedor de contexto único para `Store` / `CompanyProfile` / `WhatsAppAccount` / `Conversation`.
- Sincronizar `Conversation.mode` com `ConversationHandover`.
- Corrigir bugs de unread/read.
- Corrigir fluxo de criação de perfil no frontend.

### Fase 2
- Migrar UI de “Company Profile” para “Perfil de Automação da Loja”.
- Expor `store` como pivô visual nas páginas de automação.
- Consolidar `CustomerSession` e `AutoMessage` em torno de `store` + `account`.

### Fase 3
- Eliminar duplicações de modelos mortos/legados.
- Deprecar a cópia de `ConversationHandover` em `apps/conversations.models`.
- Deprecar a árvore paralela `apps/automation/models/flow.py` se continuar sem uso.
- Consolidar envio multicanal atrás de `apps.messaging.dispatcher` com adapters reais.

## Corte implementado nesta rodada
- Criado `AutomationContextService` para resolver contexto canônico.
- `SessionManager` agora aceita `Store`, `CompanyProfile` ou `WhatsAppAccount`.
- `WhatsAppOrderService` deixou de buscar `CompanyProfile` por nome da loja.
- `ConversationService` agora sincroniza `mode` com o app de `handover`.
- `ConversationSerializer` agora expõe `handover_status` e atribuição.
- `mark_as_read` passou a gravar `read_at`, corrigindo contagem de não lidas.
- `CompanyProfileDetailPage` ganhou modo real de criação com seleção de loja + conta WhatsApp.

## Próximos passos recomendados
1. Renomear a camada visual e semântica de `CompanyProfile` para `AutomationProfile` no frontend.
2. Adicionar `store` e `account` explicitamente nos serializers de `CustomerSession` e `AutoMessage`.
3. Centralizar a política bot/humano em `apps.handover` e deixar `Conversation.mode` apenas como campo derivado/compatível.
4. Revisar o app `messaging` para torná-lo orquestrador multicanal real, não apenas módulo paralelo.
5. Criar testes para:
   - sync `Conversation.mode` ↔ `handover`
   - contexto de sessão por loja/conta
   - criação de perfil de automação
