# Model Field Redundancy Appendix

Generated from source on 2026-02-27.

## Repeated fields across models (count >= 8)

- `created_at`: 60
- `id`: 55
- `status`: 45
- `updated_at`: 44
- `name`: 38
- `account`: 26
- `is_active`: 26
- `error_message`: 23
- `store`: 23
- `description`: 21
- `conversation`: 15
- `metadata`: 15
- `sent_at`: 13
- `content`: 11
- `user`: 11
- `created_by`: 10
- `message_type`: 9
- `scheduled_at`: 9
- `event_type`: 8
- `media_url`: 8
- `payload`: 8
- `phone_number`: 8

## Near-duplicate model pairs (shared fields >= 8 and jaccard >= 0.45)

- `server/apps/automation/models.py:AgentFlow` <-> `server/apps/automation/models/flow.py:AgentFlow` | jaccard=1.00
  shared: description, flow_json, is_active, is_default, name, store, success_rate, total_executions, version
- `server/apps/automation/models.py:FlowSession` <-> `server/apps/automation/models/flow.py:FlowSession` | jaccard=1.00
  shared: context, conversation, current_node_id, flow, input_type_expected, is_expired, is_waiting_input, last_interaction, node_history
- `server/apps/automation/models.py:FlowExecutionLog` <-> `server/apps/automation/models/flow.py:FlowExecutionLog` | jaccard=1.00
  shared: context_snapshot, error_message, execution_time_ms, flow, input_message, node_id, node_type, output_message, session, success, tokens_used
- `server/apps/campaigns/models.py:CampaignRecipient` <-> `server/apps/marketing/models.py:EmailRecipient` | jaccard=0.48
  shared: campaign, created_at, delivered_at, error_code, error_message, id, sent_at, status, updated_at, variables
- `server/apps/instagram/models.py:InstagramConversation` <-> `server/apps/messaging/models.py:MessengerConversation` | jaccard=0.64
  shared: account, created_at, id, is_active, last_message_at, participant_name, participant_profile_pic, unread_count, updated_at
- `server/apps/marketing/models.py:EmailTemplate` <-> `server/apps/marketing/models.py:EmailAutomation` | jaccard=0.45
  shared: created_at, created_by, description, html_content, id, is_active, name, store, subject, updated_at
- `server/apps/webhooks/models.py:WebhookEvent` <-> `server/apps/webhooks/models.py:WebhookDeadLetter` | jaccard=0.48
  shared: error_message, error_traceback, event_id, event_type, headers, payload, provider, query_params, retry_count, status, store
- `server/apps/whatsapp/models.py:WebhookEvent` <-> `server/apps/stores/models/payment.py:StorePaymentWebhookEvent` | jaccard=0.62
  shared: error_message, event_id, event_type, headers, payload, processed_at, processing_status, retry_count
- `server/apps/stores/models/category.py:StoreCategory` <-> `server/apps/stores/models/combo.py:StoreCombo` | jaccard=0.65
  shared: created_at, description, id, image, image_url, is_active, name, slug, sort_order, store, updated_at
- `server/apps/stores/models/category.py:StoreCategory` <-> `server/apps/stores/models/product.py:StoreProductType` | jaccard=0.67
  shared: created_at, description, id, image, is_active, name, slug, sort_order, store, updated_at
- `server/apps/stores/models/combo.py:StoreCombo` <-> `server/apps/stores/models/product.py:StoreProductType` | jaccard=0.53
  shared: created_at, description, id, image, is_active, name, slug, sort_order, store, updated_at
- `server/apps/stores/models/combo.py:StoreCombo` <-> `server/apps/stores/models/product.py:StoreProductVariant` | jaccard=0.55
  shared: compare_at_price, created_at, id, image, image_url, is_active, name, price, sort_order, stock_quantity, updated_at

## Serializer duplication by model

- `MessengerAccount`
  - `MessengerAccountSerializer` -> `server/apps/messaging/api/serializers.py`
  - `MessengerAccountSerializer` -> `server/apps/messenger/serializers.py`
  - `MessengerAccountCreateSerializer` -> `server/apps/messenger/serializers.py`
- `MessengerBroadcast`
  - `MessengerBroadcastSerializer` -> `server/apps/messaging/api/serializers.py`
  - `MessengerBroadcastSerializer` -> `server/apps/messenger/serializers.py`
- `MessengerConversation`
  - `MessengerConversationSerializer` -> `server/apps/messaging/api/serializers.py`
  - `MessengerConversationSerializer` -> `server/apps/messenger/serializers.py`
- `MessengerMessage`
  - `MessengerMessageSerializer` -> `server/apps/messaging/api/serializers.py`
  - `MessengerMessageSerializer` -> `server/apps/messenger/serializers.py`
- `MessengerSponsoredMessage`
  - `MessengerSponsoredMessageSerializer` -> `server/apps/messaging/api/serializers.py`
  - `MessengerSponsoredSerializer` -> `server/apps/messenger/serializers.py`
