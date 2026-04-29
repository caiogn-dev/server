# WhatsApp Chat, Graph API, Persistencia e Melhorias

Data: 2026-04-27  
Escopo analisado: `server2` e `pastita-dash`

## Resumo executivo

O sistema ja persiste conversas e mensagens no banco. Ele nao funciona apenas em cache.

Hoje existem tres camadas principais:

- `whatsapp_webhook_events`: log/idempotencia dos webhooks recebidos da Meta.
- `whatsapp_messages`: historico persistente de mensagens inbound e outbound.
- `conversations`: conversa agregada por conta WhatsApp + telefone.

O cache/Redis aparece em pontos especificos:

- Celery broker/result backend.
- Locks distribuidos para evitar processamento duplicado de webhook/mensagem.
- Django Channels para WebSocket/realtime.
- Memoria do agente LLM via `RedisChatMessageHistory`, com TTL configuravel por agente.

Ponto importante: a memoria do LLM nao e a fonte permanente do chat. O chat permanente e `whatsapp_messages`. A memoria do LLM hoje e temporaria em Redis e pode expirar.

Principais lacunas para o objetivo de persistencia e chat profissional:

1. Midias recebidas podem ficar apenas com `media_id` e metadata se o download permanente falhar ou nao rodar.
2. Foto de perfil do usuario nao existe no contrato atual do backend. A Cloud API normalmente entrega nome do perfil no webhook, mas nao oferece foto do perfil do cliente como um endpoint oficial estavel.
3. O frontend ja tem campo `profilePictureUrl` no componente, mas o backend nao fornece esse campo em `ConversationSerializer`.
4. Historico do chat carrega so as ultimas 100 mensagens por telefone via `conversation_history`, sem cursor/infinite scroll robusto por `conversation_id`.
5. `WebhookEvent` e limpo a cada 30 dias; isso e aceitavel como log tecnico, mas nao deve ser confundido com historico permanente de mensagens.
6. `MessageRepository.delete_old_messages(days=90)` existe, mas nao achei agendamento chamando isso. Se alguem usar esse metodo em uma task futura, ele apagaria historico e quebraria a promessa de persistencia total.

## Como a Graph API / WhatsApp Cloud API entra no sistema

Configuracao:

- `config/settings/base.py`
  - `WHATSAPP_API_VERSION`, default `v22.0`
  - `WHATSAPP_API_BASE_URL = https://graph.facebook.com/{WHATSAPP_API_VERSION}`
  - `WHATSAPP_WEBHOOK_VERIFY_TOKEN`
  - `WHATSAPP_APP_SECRET`
  - flags de LLM: `WHATSAPP_ENABLE_LLM_FALLBACK`, `WHATSAPP_FORCE_DISABLE_LLM`, `WHATSAPP_ORCHESTRATOR_TIMEOUT`

Conta:

- Modelo: `apps/whatsapp/models.py::WhatsAppAccount`
- Guarda `phone_number_id`, `waba_id`, telefone, token criptografado, agente padrao, `auto_response_enabled`, `human_handoff_enabled`.

Servico Graph API:

- Arquivo: `apps/whatsapp/services/whatsapp_api_service.py`
- Usa `POST /{phone_number_id}/messages` para enviar:
  - texto
  - template
  - botoes interativos
  - listas interativas
  - product list/catalogo
  - imagem, audio, video, documento
  - localizacao
  - reaction
  - marcar como lida
- Usa `GET /{media_id}` para recuperar URL temporaria de midia.
- Usa download com `Authorization: Bearer <token>` para baixar a midia.
- Usa `GET /{phone_number_id}/whatsapp_business_profile` para o perfil da empresa, incluindo `profile_picture_url`.
- Usa `GET /{waba_id}/message_templates` para sincronizar templates.
- Usa `GET /{waba_id}/phone_numbers` para telefones da WABA.

Fontes oficiais/primarias consultadas:

- Meta Postman - Messages: `https://www.postman.com/meta/whatsapp-business-platform/folder/13382743-6162ac5d-de2e-42aa-9ff9-f77a3dcbd3f8`
- Meta Postman - Statuses: `https://www.postman.com/meta/whatsapp-business-platform/folder/pahjoza/statuses`
- Meta Postman - Media: `https://www.postman.com/meta/whatsapp-business-platform/folder/nb1o38v/media`
- Meta Postman - Retrieve Media URL: `https://www.postman.com/meta/whatsapp-business-platform/request/fpj02x0/retrieve-media-url`
- Meta Postman - Download Media: `https://www.postman.com/meta/whatsapp-business-platform/request/ked0afm/download-media`
- Meta Postman - Contacts object: `https://www.postman.com/meta/whatsapp-business-platform/folder/a607p22/contacts`

## Fluxo de entrada de mensagem

1. Meta chama `POST /webhook/whatsapp/`:
   - Arquivo: `apps/whatsapp/webhooks/views.py`
   - View: `WhatsAppWebhookView.post`
   - Valida assinatura `X-Hub-Signature-256` usando `WHATSAPP_APP_SECRET`.
   - Em producao rejeita assinatura invalida.
   - Cria eventos via `WebhookService.process_webhook`.
   - Retorna HTTP 200 para a Meta mesmo se algum processamento interno falhar, para reduzir retry externo.

2. O webhook vira `WebhookEvent`:
   - Arquivo: `apps/whatsapp/services/webhook_service.py`
   - Para cada `messages[]`, cria evento `message:{wamid}`.
   - Para cada `statuses[]`, cria evento `status:{wamid}:{status}:{timestamp}`.
   - Para `errors[]`, cria evento de erro.
   - O payload bruto do webhook fica salvo em `WebhookEvent.payload`.

3. Celery processa o evento:
   - Task: `apps.whatsapp.tasks.process_webhook_event`
   - Usa lock Redis `process_webhook_event:{event_id}`.
   - Chama `WebhookService.process_event(event, post_process_inbound=True)`.

4. Mensagem inbound e persistida:
   - Metodo: `MessageService.process_inbound_message`
   - Cria `whatsapp_messages` com:
     - `whatsapp_message_id`
     - `direction=inbound`
     - `message_type`
     - `status=delivered`
     - `from_number`
     - `to_number`
     - `content` JSON
     - `text_body`
     - `media_id`
     - `context_message_id`
   - Tipos tratados: text, image, video, audio, document, sticker, location, contacts, interactive, button, order, reaction, unknown.

5. Conversa e criada/atualizada:
   - Modelo: `apps/conversations/models.py::Conversation`
   - Chave unica: `account + phone_number`.
   - `post_process_inbound_message` chama `ConversationService.get_or_create_conversation`.
   - Nome do contato vem de `contacts[0].profile.name`, quando a Meta envia.
   - Se nao houver nome, tenta extrair de texto por heuristica.

6. Pipeline automatico roda:
   - Se conversa esta em `human`, automacao e pulada.
   - Se payload e pedido de catalogo nativo, trata deterministicamente.
   - Senao executa `LLMOrchestratorService` / `UnifiedService`.
   - Timeout padrao: minimo 30s, default env 90s.
   - Se UnifiedService nao responder e LLM estiver habilitado, agenda fallback direto para `process_message_with_agent`.

7. Realtime:
   - `WhatsAppBroadcastService` envia evento pelo Channels.
   - `pastita-dash` recebe em `useWhatsAppWS`.
   - Eventos principais: `message_received`, `message_sent`, `status_updated`, `conversation_updated`, `typing`.

## Fluxo de saida de mensagem

Frontend:

- `src/components/chat/ChatWindow.tsx`
  - Usa `whatsappService.sendTextMessage` para texto.
  - Usa `sendFile` para arquivo.
  - Faz optimistic UI com mensagem temporaria.

Backend:

- `POST /api/v1/whatsapp/messages/send_text/`
- `POST /api/v1/whatsapp/messages/send_file/`
- `POST /api/v1/whatsapp/messages/send_image/`, `send_audio`, `send_video`, `send_document`
- `MessageService._create_outbound_message` cria mensagem `pending` antes de chamar a Graph API.
- Se a Graph API retorna sucesso, `_update_message_sent` troca `pending_*` pelo `wamid` real, status `sent` e salva `sent_at`.
- Status posteriores (`delivered`, `read`, `failed`) chegam por webhook de status e atualizam a mesma linha.

## Persistencia: o que fica salvo hoje

Persistente:

- Mensagens inbound e outbound: sim, em `whatsapp_messages`.
- Conteudo textual: sim, em `text_body` e/ou `content`.
- Payload especial: sim, em `content` JSON.
- Status de entrega/leitura/falha: sim, na propria mensagem.
- Conversas: sim, em `conversations`.
- Nome do contato: sim, se recebido da Meta ou extraido.
- Webhook bruto: sim, mas por tempo limitado.
- AgentConversation: sim, mas hoje e mais indice/ponte de sessao que historico completo.

Parcial ou fragil:

- Midia recebida:
  - O webhook salva `media_id`, mime/sha dentro de `content`.
  - A persistencia ideal exige baixar a midia e salvar em storage proprio, porque URL da Meta e temporaria.
  - Existe comando `refetch_missing_media`, sinal de que o problema ja aconteceu.
- Memoria LLM:
  - Redis com TTL (`Agent.memory_ttl`, default 86400s).
  - `AgentConversation` persiste `session_id`, mas o conteudo da memoria ativa e Redis.
  - `AgentMessage` existe, mas o caminho principal do WhatsApp nao aparenta gravar cada turno nele. O historico real para auditoria deve ser `whatsapp_messages`.

Temporario/nao permanente:

- WebSocket events.
- Typing indicators.
- Redis locks.
- Redis memory do LLM apos TTL.
- URL temporaria da midia da Meta.

## Foto de perfil do usuario

Estado atual:

- `Conversation` nao tem `profile_picture_url`.
- `ConversationSerializer` nao retorna foto.
- `ContactList` no dash ja aceita `profilePictureUrl`, mas `conversationToContact` nao preenche.
- `users.UnifiedUser.profile_picture` existe, mas nao esta conectado diretamente ao WhatsApp Cloud API nem ao chat.

Limite da Cloud API:

- O webhook de `contacts` fornece `profile.name` e `wa_id`.
- A documentacao oficial/colecao Meta mostra `contacts.profile` como informacao do remetente, mas nao ha um endpoint oficial claro para buscar foto de perfil do usuario final do WhatsApp Cloud API.
- `get_business_profile()` no seu codigo busca foto do perfil da empresa, nao do cliente.

Conclusao pratica:

- Foto de perfil real do cliente pelo WhatsApp Cloud API nao deve ser tratada como recurso garantido.
- O caminho correto e implementar avatar persistente proprio:
  - upload manual pelo atendente;
  - importacao de CRM/site;
  - usar foto do usuario logado do site, se existir consentimento/contexto;
  - fallback visual com iniciais/telefone.
- Nao recomendo scraping ou bibliotecas nao oficiais para foto do WhatsApp. Isso cria risco de bloqueio e instabilidade.

## O que a API pode oferecer para melhorar o chat

Ja usado ou parcialmente usado:

- Envio de texto livre dentro da janela de atendimento.
- Templates para mensagens iniciadas pela empresa ou fora da janela permitida.
- Botoes interativos.
- Listas interativas.
- Mensagens de catalogo/produto.
- Midias: imagem, audio, video, documento, sticker recebido.
- Localizacao.
- Contacts.
- Reactions.
- Status: sent, delivered, read, failed.
- Marcar mensagem como lida.
- Perfil da empresa.
- Templates da WABA.

Oportunidades:

- Persistir download de toda midia inbound automaticamente no processamento do webhook, nao apenas por comando posterior.
- Guardar `media_mime_type`, `media_sha256`, `file_size`, `filename`, `caption` em campos de primeira classe ou metadata padronizada.
- Guardar `wa_id` separado do telefone normalizado.
- Guardar `profile_name_source`, `profile_name_last_seen_at`.
- Guardar objetos de status/pricing/conversation da Meta em metadata da mensagem para auditoria.
- Criar endpoint por conversa com cursor:
  - `GET /api/v1/conversations/{id}/messages/?before=<created_at|id>&limit=50`
  - sempre ordenado, estavel, sem depender de telefone.
- Implementar envio de read receipt real quando atendente abre a conversa:
  - chamar `MessageService.mark_as_read(account_id, whatsapp_message_id)`;
  - depois marcar `read_at` local.

## Chat do dashboard: estado atual

Arquivos principais:

- `pastita-dash/src/components/chat/ChatWindow.tsx`
- `pastita-dash/src/components/chat/ContactList.tsx`
- `pastita-dash/src/components/chat/MessageBubble.tsx`
- `pastita-dash/src/components/chat/MessageInput.tsx`
- `pastita-dash/src/hooks/useWhatsAppWS.ts`
- `pastita-dash/src/services/whatsapp.ts`
- `pastita-dash/src/services/conversations.ts`

Funciona hoje:

- Lista conversas por conta.
- Abre conversa.
- Carrega ultimas 100 mensagens.
- Recebe mensagens novas por WebSocket.
- Envia texto e arquivo.
- Mostra bolhas inbound/outbound.
- Mostra status visual de enviado/entregue/lido/falhou.
- Mostra preview de imagem, video, audio, documento, localizacao, contato, order, reaction, button, interactive.
- Alterna modo humano/auto via handover.

Problemas de produto/UX:

- Lista de conversas nao usa `unread_count` real; `conversationToContact` fixa `unreadCount: 0`.
- Header mostra "Online/Offline" baseado na conexao WebSocket do atendente, nao no cliente.
- Nao ha painel lateral com dados do cliente, pedidos, tags, notas e contexto.
- Nao ha infinite scroll para historico antigo.
- Busca local filtra apenas conversas carregadas; nao faz busca backend.
- Nao ha fila/atribuicao visivel de atendentes.
- Nao ha composer avancado com templates, respostas rapidas, catalogo, pedido, pagamento, localizacao.
- Nao ha separacao clara entre mensagem enviada pelo humano, pelo bot, por template, por sistema.
- Nao ha indicador robusto de origem (`metadata.source`) no UI.
- Nao ha SLA, prioridade, "aguardando cliente", "aguardando atendente".
- Nao ha timeline de eventos de pedido/pagamento junto da conversa.

## Melhorias recomendadas para ficar mais perto de WhatsApp Web / WhatsApp Business / plataformas de atendimento

Prioridade 1 - Base de persistencia e confiabilidade:

1. Criar `ContactProfile` ou expandir `Conversation`:
   - `wa_id`
   - `display_name`
   - `profile_picture_url`
   - `profile_picture_file`
   - `profile_name_last_seen_at`
   - `last_seen_at` se algum canal proprio fornecer
   - `metadata`
2. Baixar midia inbound automaticamente:
   - no `process_inbound_message`, se `media_id`, chamar `get_media_url`, `download_media`, salvar em `default_storage`.
   - salvar URL propria permanente em `media_url`.
   - fallback: se download falhar, manter `media_id` e agendar retry.
3. Endpoint de historico por conversa com cursor:
   - nao usar apenas `phone_number`.
   - retornar `next_before`, `has_more`.
4. Politica explicita de retencao:
   - mensagens: permanente por padrao.
   - webhook events: 30 dias ok.
   - midia: permanente ou periodo configuravel.
   - LLM memory: cache operacional, reconstruivel a partir de mensagens.
5. Persistir turnos do agente:
   - criar/atualizar `AgentMessage` para user/assistant em cada resposta.
   - ou padronizar que `whatsapp_messages.metadata.source` e a trilha oficial.

Prioridade 2 - Atendimento humano:

1. Inbox com filas:
   - Todas
   - Nao lidas
   - Minhas
   - Sem responsavel
   - Bot
   - Humano
   - Resolvidas
2. Estados operacionais:
   - aberto
   - aguardando cliente
   - aguardando atendente
   - em preparo/pedido ativo
   - resolvido
3. Atribuicao:
   - assumir conversa
   - transferir atendente
   - transferir para bot
   - motivo do handover
4. Painel do cliente:
   - nome, telefone, tags
   - pedidos recentes
   - carrinho/session atual
   - pagamentos pendentes
   - endereco recente
   - notas internas
5. Notas internas e mensagens internas:
   - nao enviar para cliente.
   - registrar no timeline.
6. Respostas rapidas:
   - saudacao
   - taxa de entrega
   - horario
   - status do pedido
   - pedir endereco
   - PIX
7. Templates:
   - selector com busca.
   - preview.
   - validacao de variaveis.
   - bloqueio quando fora da janela de 24h para texto livre.

Prioridade 3 - Experiencia de chat:

1. Infinite scroll com preservacao de posicao.
2. Busca no historico da conversa.
3. Reply/quote por mensagem usando `context_message_id`.
4. Encaminhar/baixar/copiar mensagens.
5. Melhor renderizacao de catalog orders:
   - mostrar itens, quantidades, total estimado.
6. Melhor preview de midia:
   - imagem full screen.
   - audio com waveform simples/duracao.
   - documento com tamanho e tipo.
7. Status real:
   - enviado, entregue, lido, falhou, motivo.
8. Separadores de eventos:
   - pedido criado.
   - PIX gerado.
   - pagamento aprovado.
   - modo humano/auto alterado.
9. Composer:
   - anexar arquivo.
   - enviar template.
   - enviar produto/catalogo.
   - enviar localizacao da loja.
   - criar pedido.
   - gerar PIX.
10. Mobile responsivo mais proximo de app de chat:
   - lista/conversa em telas separadas.
   - header fixo.
   - composer fixo.

Prioridade 4 - Bot/LLM e atendimento com IA

Arquitetura atual:

- `UnifiedService` primeiro tenta intents e handlers deterministicos.
- Templates de banco entram antes do LLM, exceto intents consultivas com agente ativo.
- LLM so deve cuidar de consultas/recomendacoes/FAQ, nao transacoes criticas.
- PIX ja tem caminho deterministico para nao misturar codigo com texto.
- `LangchainService` usa contexto dinamico de loja, cardapio, entrega, horarios, sessao atual e ultimo pedido.
- Ferramentas disponiveis:
  - `buscar_produto`
  - `listar_categorias`
  - `verificar_pedido_pendente`
  - `consultar_historico_pedidos`
  - `informacoes_entrega`
  - `consultar_pagamento`

Melhorias recomendadas:

1. Separar motor de atendimento em estados:
   - saudacao
   - descoberta de intencao
   - montagem de pedido
   - endereco/localizacao
   - confirmacao
   - pagamento
   - pos-venda
   - handover humano
2. Criar "policy layer" antes do LLM:
   - LLM nunca cria pedido diretamente sem ferramenta deterministica.
   - LLM nunca informa PIX sem ferramenta deterministica.
   - LLM nunca inventa taxa de entrega.
   - LLM nunca promete disponibilidade sem checar estoque.
3. Transformar respostas criticas em `whatsapp_response` estruturado:
   - botoes
   - lista
   - template de copia PIX
   - catalogo
   - mensagem de handover
4. Persistir avaliacao de cada atendimento:
   - intent detectada
   - source: handler/template/llm/fallback
   - latencia
   - confidence
   - erro
   - ferramenta usada
5. Criar dashboard de qualidade do bot:
   - mensagens sem resposta
   - fallback rate
   - tempo medio
   - intents mais frequentes
   - handovers por motivo
   - pedidos criados pelo bot
   - falhas de pagamento/catalogo
6. Usar historico persistente como memoria longa:
   - resumir conversa a cada N mensagens.
   - salvar `conversation.context.summary`.
   - injetar resumo curto no prompt.
   - manter Redis so para memoria curta.
7. Melhorar handover:
   - gatilhos automaticos: reclamacao, baixa confianca, erro de ferramenta, cliente pede humano, mensagem repetida.
   - bot para de responder em modo humano.
   - atendente pode devolver para bot com contexto.
8. Criar simulador/testes:
   - suite de conversas reais anonimizadas.
   - esperado: resposta, ferramenta, source.
   - regressao para PIX, entrega, catalogo, pedido, humano.
9. Human-in-the-loop:
   - sugestao de resposta da IA para o atendente aprovar.
   - especialmente em modo humano.
10. Voz e audio:
   - transcrever audio inbound antes de enviar ao bot.
   - salvar transcricao em `metadata.transcript`.
   - renderizar audio + texto transcrito no dash.

## Roadmap de implementacao sugerido

Sprint 1 - Persistencia real e contrato de chat:

- Adicionar campos de contato/avatar.
- Criar endpoint `GET /conversations/{id}/messages/`.
- Fazer ChatWindow usar `conversationsService.getMessages(conversationId)` em vez de `conversation_history` por telefone.
- Corrigir `unreadCount`.
- Ao abrir conversa, chamar backend para marcar mensagens como lidas e enviar read receipt para Meta.
- Baixar midia inbound automaticamente e salvar em storage.

Sprint 2 - Inbox profissional:

- Filtros de fila.
- Assumir/transferir/resolver.
- Painel lateral do cliente.
- Tags e notas no fluxo principal.
- Eventos de pedido/pagamento no timeline.

Sprint 3 - Composer e recursos WhatsApp:

- Picker de templates.
- Respostas rapidas.
- Enviar catalogo/produto.
- Enviar localizacao.
- Reply/quote.
- Melhor viewer de midia.

Sprint 4 - IA operacional:

- Persistir `AgentMessage`/traces.
- Resumo persistente por conversa.
- Dashboard de qualidade.
- Sugestao de resposta para atendente.
- Gatilhos de handover.
- Testes de conversas reais.

## Decisao recomendada

Para o objetivo "quero persistencia", trate `whatsapp_messages` como fonte de verdade permanente e Redis apenas como acelerador/memoria curta.

Nao dependa da Meta para reconstituir historico antigo nem para manter midia acessivel. Webhook recebido deve virar registro local duravel imediatamente. Midia deve ser baixada para storage proprio. Contexto do bot deve ser reconstruivel a partir do banco, nao depender do TTL do Redis.

Para foto de perfil do cliente, implemente avatar proprio e aceite que a Cloud API nao entrega isso de forma garantida. O frontend ja esta parcialmente preparado para exibir avatar; falta o backend e a estrategia de origem.
