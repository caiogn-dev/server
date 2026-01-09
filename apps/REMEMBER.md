Apps Principais:
core - Modelos base, utilitários, exceções, middleware
whatsapp - Integração com WhatsApp Business API (contas, mensagens, templates, webhooks)
conversations - Gerenciamento de conversas e notas
orders - Sistema de pedidos completo
payments - Sistema de pagamentos com múltiplos gateways
langflow - Integração com LLM/Langflow para automação
Arquitetura:
API REST com Django REST Framework
Autenticação por Token
Celery para processamento assíncrono
Redis para cache e filas
PostgreSQL/SQLite para banco de dados
Documentação OpenAPI (Swagger/ReDoc)
O que precisa ser integrado no Dashboard Frontend:
PRIORIDADE ALTA (Core Business):
Dashboard Principal

Métricas em tempo real (mensagens, conversas, pedidos)
Gráficos de performance
Alertas e notificações
Gerenciamento de Contas WhatsApp

CRUD de contas
Ativação/desativação
Rotação de tokens
Sincronização de templates
Perfil de negócio
Central de Mensagens

Inbox unificado
Envio de mensagens (texto, template, interativas, mídia)
Histórico de conversas
Status de mensagens em tempo real
Marcar como lida
Gerenciamento de Conversas

Lista de conversas ativas
Alternância humano/automático
Atribuição de agentes
Notas e tags
Contexto da conversa
PRIORIDADE MÉDIA (Operacional):
Sistema de Pedidos

Lista de pedidos com filtros
Criação de pedidos
Fluxo de status (confirmar, pagar, enviar, entregar, cancelar)
Itens do pedido
Eventos/histórico
Estatísticas
Sistema de Pagamentos

Lista de pagamentos
Criação de pagamentos
Processamento (confirmar, falhar, cancelar, reembolsar)
Gateways de pagamento (CRUD)
Webhooks de pagamento
Templates de Mensagem

Lista de templates
Sincronização com Meta
Visualização de componentes
PRIORIDADE ESPECIAL (LLM/Langflow - Separado):
Integração Langflow
CRUD de flows
Associação de flows a contas
Processamento manual de mensagens
Sessões de conversa
Histórico de interações
Estatísticas de uso
Logs de execução
Configuração de tweaks e contexto
PRIORIDADE BAIXA (Administração):
Configurações

Usuários e permissões
Tokens de API
Configurações de webhook
Rate limiting
Monitoramento

Health check
Logs de webhook
Eventos de erro
Métricas de sistema
APIs Disponíveis para Integração:
WhatsApp:
GET/POST/PUT/DELETE /api/v1/whatsapp/accounts/
POST /api/v1/whatsapp/accounts/{id}/activate/
POST /api/v1/whatsapp/accounts/{id}/deactivate/
POST /api/v1/whatsapp/accounts/{id}/rotate_token/
POST /api/v1/whatsapp/accounts/{id}/sync_templates/
GET /api/v1/whatsapp/accounts/{id}/business_profile/
GET /api/v1/whatsapp/messages/
POST /api/v1/whatsapp/messages/send_text/
POST /api/v1/whatsapp/messages/send_template/
POST /api/v1/whatsapp/messages/send_interactive_buttons/
POST /api/v1/whatsapp/messages/send_interactive_list/
POST /api/v1/whatsapp/messages/send_image/
POST /api/v1/whatsapp/messages/send_document/
POST /api/v1/whatsapp/messages/mark_as_read/
POST /api/v1/whatsapp/messages/conversation_history/
POST /api/v1/whatsapp/messages/stats/
GET /api/v1/whatsapp/templates/
Conversations:
GET/POST/PUT/DELETE /api/v1/conversations/
POST /api/v1/conversations/{id}/switch_to_human/
POST /api/v1/conversations/{id}/switch_to_auto/
POST /api/v1/conversations/{id}/assign_agent/
POST /api/v1/conversations/{id}/unassign_agent/
POST /api/v1/conversations/{id}/close/
POST /api/v1/conversations/{id}/resolve/
POST /api/v1/conversations/{id}/reopen/
GET /api/v1/conversations/{id}/notes/
POST /api/v1/conversations/{id}/add_note/
POST /api/v1/conversations/{id}/update_context/
POST /api/v1/conversations/{id}/add_tag/
POST /api/v1/conversations/{id}/remove_tag/
GET /api/v1/conversations/stats/
Orders:
GET/POST/PUT/DELETE /api/v1/orders/
POST /api/v1/orders/{id}/confirm/
POST /api/v1/orders/{id}/awaiting_payment/
POST /api/v1/orders/{id}/mark_paid/
POST /api/v1/orders/{id}/ship/
POST /api/v1/orders/{id}/deliver/
POST /api/v1/orders/{id}/cancel/
POST /api/v1/orders/{id}/add_item/
DELETE /api/v1/orders/{id}/items/{item_id}/
POST /api/v1/orders/{id}/update_shipping/
POST /api/v1/orders/{id}/add_note/
GET /api/v1/orders/{id}/events/
GET /api/v1/orders/stats/
GET /api/v1/orders/by_customer/
Payments:
GET/POST/PUT/DELETE /api/v1/payments/
POST /api/v1/payments/{id}/process/
POST /api/v1/payments/{id}/confirm/
POST /api/v1/payments/{id}/fail/
POST /api/v1/payments/{id}/cancel/
POST /api/v1/payments/{id}/refund/
GET /api/v1/payments/by_order/
GET/POST/PUT/DELETE /api/v1/payments/gateways/
Langflow:
GET/POST/PUT/DELETE /api/v1/langflow/flows/
POST /api/v1/langflow/flows/process/
POST /api/v1/langflow/flows/{id}/assign_accounts/
POST /api/v1/langflow/flows/{id}/remove_accounts/
GET /api/v1/langflow/flows/{id}/stats/
GET /api/v1/langflow/flows/{id}/logs/
GET /api/v1/langflow/sessions/
GET /api/v1/langflow/sessions/{id}/history/
POST /api/v1/langflow/sessions/{id}/update_context/
POST /api/v1/langflow/sessions/{id}/clear_history/
Core:
GET /api/v1/health/
GET /api/v1/info/