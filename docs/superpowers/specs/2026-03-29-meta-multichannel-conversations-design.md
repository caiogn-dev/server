# Meta Multichannel Conversations Design

Date: 2026-03-29
Owner: Codex
Status: Approved in chat, pending user review of written spec

## Context

The current Meta messaging implementation is split across multiple apps and multiple dashboard pages:

- WhatsApp conversations live in `apps.conversations` and are rendered in `/conversations` and `/whatsapp/inbox`.
- Instagram DMs live in `apps.instagram` and are rendered in `/instagram/inbox`.
- Messenger conversations live in `apps.messaging` and are rendered in `/messenger/inbox`.

The current problems are:

- Instagram webhook delivery is reaching the backend and persisting messages, but the `pastita-dash` inbox is not rendering them reliably due to inconsistent response-shape handling.
- `/conversations` is currently tied to the WhatsApp conversation shape and crashes when the frontend expects arrays but receives paginated or differently-shaped responses.
- `/conversations` is not a true multichannel activity hub yet.
- The WhatsApp quick interaction flow inside `/conversations` is too administrative and not operational enough for fast triage.

## Goals

1. Fix Instagram inbox rendering, message loading, and message sending in `pastita-dash`.
2. Keep platform inboxes separate:
   - `/whatsapp/inbox`
   - `/instagram/inbox`
   - `/messenger/inbox`
3. Turn `/conversations` into a centralized multichannel activity list with one row per conversation.
4. Show platform identity visually in `/conversations` using a platform icon for WhatsApp, Instagram, or Messenger.
5. Sort the unified list by last message timestamp so active conversations rise to the top immediately.
6. Keep WhatsApp operational detail in `/conversations` via a better quick-action modal.
7. Preserve existing data models; add a read-only aggregation layer instead of forcing a schema merger.

## Non-goals

This delivery does not attempt to finish every possible Meta API surface. It explicitly excludes:

- Meta Ads campaign management
- Full OAuth connection flows for every Meta surface
- Deep Instagram shopping/catalog enhancements beyond what is needed for inbox stability
- Replacing platform-specific inbox pages with a fully merged inbox UI
- A hard migration of all messaging models into a single database model

## User-facing Product Decisions

### Platform inboxes remain separate

Detailed service and response flows remain in platform-specific inboxes:

- WhatsApp operations stay in `/whatsapp/inbox`
- Instagram DM operations stay in `/instagram/inbox`
- Messenger operations stay in `/messenger/inbox`

### `/conversations` becomes a unified activity hub

`/conversations` will display one row per conversation, not one row per message/event.

Each row will show:

- Platform icon
- Primary display name
- Secondary identifier
- Last message preview
- Relative or short timestamp
- Unread count when present
- Platform-specific activity state when useful

Ordering rule:

- Always sort by `last_message_at desc`

Behavior when a new message arrives:

- The affected conversation must move upward immediately because its `last_message_at` changed.

### Click behavior

Clicking a conversation row depends on the platform:

- WhatsApp: open an improved quick-action modal inside `/conversations`
- Instagram: redirect to `/instagram/inbox` with the correct account and conversation in the query string
- Messenger: redirect to `/messenger/inbox` with the correct account and conversation in the query string

## Current-state Summary

### Backend

- `apps.conversations` exposes WhatsApp-centric conversation actions and list endpoints.
- `apps.instagram` stores conversations and messages separately from WhatsApp.
- `apps.messaging` stores Messenger conversations and messages separately from WhatsApp.
- The webhook layer now has handlers for WhatsApp, Instagram, and Messenger, but the dashboard contract is still fragmented.

### Frontend

- `InstagramAccountsPage` and `InstagramInbox` currently assume inconsistent list shapes.
- `MessengerInbox` was drifting away from the actual backend serializer contract.
- `ConversationsPage` consumes a WhatsApp-centric contract and contains UI/actions that are too specific for a multichannel list.
- The separate WhatsApp inbox experience in `WhatsAppInboxPage` is serviceable, but the `/conversations` quick interaction surface is not optimized for triage.

## Proposed Architecture

### 1. Backend read-only aggregation layer

Add a unified read model under the existing `apps.conversations` API surface without changing the underlying persistence models.

Recommended endpoint:

- `GET /api/v1/conversations/universal/`

Recommended implementation pieces:

- a read-only service in `apps.conversations.services` that aggregates from:
  - `Conversation` for WhatsApp
  - `InstagramConversation` for Instagram
  - `MessengerConversation` for Messenger
- a dedicated serializer for normalized output
- a lightweight viewset action or dedicated API view that returns a paginated normalized list

### 2. Normalized conversation contract

The universal endpoint returns a normalized row per conversation with these fields:

- `id`
- `platform`
- `platform_icon_key`
- `source_conversation_id`
- `account_id`
- `display_name`
- `secondary_identifier`
- `last_message_preview`
- `last_message_at`
- `unread_count`
- `status`
- `route`
- `route_params`
- `is_actionable`

Definitions:

- `id`: stable synthetic ID for the aggregated list, for example `<platform>:<source_conversation_id>`
- `platform`: `whatsapp`, `instagram`, or `messenger`
- `platform_icon_key`: UI lookup key for the platform icon
- `source_conversation_id`: actual ID in the platform-specific model
- `account_id`: platform account identifier needed for redirection
- `display_name`: best available human-readable participant name
- `secondary_identifier`:
  - WhatsApp: phone number
  - Instagram: `@username` if available, otherwise participant ID
  - Messenger: participant name or PSID fallback
- `last_message_preview`: short text preview for the newest message
- `last_message_at`: normalized activity timestamp
- `unread_count`: per-platform unread count
- `status`: platform-specific coarse status mapped into a stable display set
- `route`: target frontend route
- `route_params`: frontend parameters needed to open the correct inbox context
- `is_actionable`: whether the row supports in-place quick actions in `/conversations`

### 3. Platform mapping rules

#### WhatsApp

Source:

- `apps.conversations.models.Conversation`

Mapped values:

- `platform = "whatsapp"`
- `source_conversation_id = Conversation.id`
- `display_name = contact_name or phone_number`
- `secondary_identifier = phone_number`
- `route = "/whatsapp/inbox"`
- `route_params = { "conversation": Conversation.id }`
- `is_actionable = true`

#### Instagram

Source:

- `apps.instagram.models.InstagramConversation`

Mapped values:

- `platform = "instagram"`
- `source_conversation_id = InstagramConversation.id`
- `display_name = participant_name or participant_username or participant_id`
- `secondary_identifier = "@participant_username"` when available, otherwise `participant_id`
- `route = "/instagram/inbox"`
- `route_params = { "account": account_id, "conversation": InstagramConversation.id }`
- `is_actionable = false`

#### Messenger

Source:

- `apps.messaging.models.MessengerConversation`

Mapped values:

- `platform = "messenger"`
- `source_conversation_id = MessengerConversation.id`
- `display_name = participant_name or psid`
- `secondary_identifier = psid`
- `route = "/messenger/inbox"`
- `route_params = { "account": account_id, "conversation": MessengerConversation.id }`
- `is_actionable = false`

## Frontend Design

### 1. Fix Instagram inbox first

`InstagramAccountsPage` and `InstagramInbox` must be stabilized before the multichannel hub is introduced, because the webhook is already working and the user is blocked on operations today.

Required changes:

- Normalize paginated and non-paginated responses consistently.
- Ensure account lists always become arrays before `.map()` or `.filter()`.
- Ensure conversation and message lists always become arrays before rendering.
- Make `InstagramInbox` read `account` and `conversation` from the URL.
- On page load:
  - load accounts
  - select account from query string if present
  - load conversations for that account
  - select the requested conversation if present
  - load messages for the selected conversation
- Mark messages as read when the conversation is opened.
- Keep list ordering based on latest activity.

### 2. Introduce universal conversations service in `pastita-dash`

Add a dedicated frontend service for the universal list rather than overloading the current WhatsApp-only `conversationsService`.

Recommended frontend service:

- `getUniversalConversations(params?)`

The existing WhatsApp-only service remains for WhatsApp-specific actions and detail views.

### 3. Refactor `/conversations`

`ConversationsPage` will stop assuming the WhatsApp `Conversation` type for the list.

Instead it will:

- consume the new universal conversations endpoint
- render a simpler, multichannel-oriented row layout
- use platform icons in-line
- remove WhatsApp-only heavy columns from the main table
- on click:
  - open WhatsApp modal when `platform === "whatsapp"`
  - redirect to platform inbox when `platform === "instagram"` or `platform === "messenger"`

### 4. Improve WhatsApp quick-action modal in `/conversations`

The modal should become a triage surface rather than a record-management popup.

New modal structure:

- Header:
  - contact name
  - phone number
  - conversation status
  - current mode (`auto` / `human`)
- Primary action bar:
  - open full WhatsApp inbox
  - toggle `auto` / `human`
  - mark as read
  - close or reopen when relevant
- Recent message preview area:
  - show latest messages in chronological order
  - use compact message bubbles
  - show timestamps
- Secondary info area:
  - notes
  - tags
  - compact order summary

This modal stays WhatsApp-only by design.

### 5. Messenger inbox alignment

Messenger support is not required to be fully active today, but the frontend contract must be aligned so the page stops drifting away from the backend serializer.

Required changes:

- align conversation and message interfaces with actual serializer fields
- normalize paginated list responses consistently
- accept `account` and `conversation` from query string for future redirection from `/conversations`

## Data Flow

### Instagram received message

1. Meta sends webhook to backend.
2. Instagram webhook handler persists message and updates `InstagramConversation`.
3. `InstagramInbox` fetches normalized conversation list and messages.
4. The conversation appears in the inbox.
5. The universal conversations endpoint includes that Instagram conversation using the new normalized shape.
6. `/conversations` shows the conversation row with Instagram icon and latest preview.

### WhatsApp received message

1. Existing WhatsApp flow persists message and updates conversation.
2. The existing WhatsApp inbox keeps working.
3. The universal endpoint includes the updated WhatsApp row.
4. `/conversations` reorders the row by `last_message_at`.

### Redirect flow from `/conversations`

1. User clicks a universal conversation row.
2. Frontend checks `platform`.
3. WhatsApp opens modal immediately.
4. Instagram/Messenger route to the platform inbox using `route + route_params`.
5. The target inbox reads query params and opens the intended conversation.

## Update Strategy

### Immediate implementation strategy

Use controlled polling for the dashboard list and the Instagram inbox to stabilize the experience quickly.

Recommended initial behavior:

- `/conversations`: polling every 5 seconds
- `InstagramInbox`: polling every 3 to 5 seconds while the page is open
- `WhatsAppInbox`: keep existing real-time behavior where available

This is intentionally pragmatic. It avoids blocking the current fix on a full cross-platform realtime event layer.

### Future upgrade path

The normalized universal contract can later be connected to websocket or SSE events without changing the list UI contract.

## Error Handling

### Backend

- If one platform source fails during aggregation, the universal endpoint should degrade gracefully and still return rows from the remaining platforms when possible.
- Log source-level aggregation failures with platform context.
- Do not let a Messenger issue break WhatsApp or Instagram listing.

### Frontend

- Always normalize arrays before list operations.
- Treat missing previews and missing secondary identifiers as expected states, not fatal states.
- Show empty states rather than crash when a platform has no connected accounts or no conversations.
- Preserve route stability even if a platform-specific conversation no longer exists.

## Testing Strategy

### Backend tests

- Unit tests for universal normalization:
  - WhatsApp row mapping
  - Instagram row mapping
  - Messenger row mapping
- Ordering test by `last_message_at`
- Graceful handling test when one platform has no data
- Permission/access tests to ensure only accessible account data is returned

### Frontend tests

- `InstagramAccountsPage` renders with paginated response
- `InstagramInbox` renders with paginated and direct-array responses
- `InstagramInbox` opens a conversation from query string
- `/conversations` renders unified rows and icons
- `/conversations` redirects correctly for Instagram and Messenger rows
- WhatsApp modal opens and shows recent messages/actions without crashing

### Manual acceptance checks

- An Instagram message received by webhook appears in `InstagramInbox`
- Sending a message from `InstagramInbox` appears in the panel without breaking the page
- `/conversations` opens without runtime errors
- `/conversations` shows WhatsApp and Instagram rows together
- A new incoming message causes the conversation to rise to the top
- Clicking an Instagram row opens the correct conversation in `/instagram/inbox`
- Clicking a WhatsApp row opens the improved quick-action modal

## Implementation Order

1. Fix frontend response normalization for Instagram pages.
2. Add query-param-driven selection for Instagram and Messenger inboxes.
3. Implement backend universal conversations endpoint.
4. Add frontend universal conversations service.
5. Refactor `/conversations` to the new normalized list.
6. Improve WhatsApp modal and quick-action behavior in `/conversations`.
7. Verify sorting, redirection, unread counts, and no-crash behavior.

## Risks and Mitigations

### Risk: different models expose different preview fields

Mitigation:

- normalize previews in the backend service and never let the frontend infer them ad hoc.

### Risk: current `/conversations` UI depends on WhatsApp-only fields

Mitigation:

- narrow the aggregated list to universal fields only
- keep WhatsApp-only detail inside the modal

### Risk: Instagram inbox remains inconsistent due to mixed response shapes

Mitigation:

- explicitly normalize `response.data?.results ?? response.data ?? []` in one place per fetch path
- avoid raw `.filter()` or `.map()` on unknown values

### Risk: Messenger not enabled yet but must not break the aggregated list

Mitigation:

- treat Messenger as an optional source during aggregation
- return zero rows for Messenger cleanly when not configured

## Success Criteria

This design is successful when:

- the Instagram inbox works for real received messages already persisted by the backend
- `/conversations` becomes a stable multichannel activity hub
- WhatsApp remains operational and gets a better quick-action modal
- platform-specific inboxes stay separate
- the architecture can absorb Messenger cleanly when enabled later
