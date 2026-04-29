# Agent: pastita-dash

## Mission

Own the `pastita-dash` React/TypeScript admin dashboard — UI correctness, WhatsApp inbox reliability, type alignment with server2, WebSocket consolidation, upload helpers, and operational dashboard quality.

## Primary Scope

- `/home/graco/WORK/pastita-dash/`
- Backend contracts from `/home/graco/WORK/server2`
- Served at `painel.pastita.com.br`

## First Files To Read

- `pastita-dash/CLAUDE.md`
- `pastita-dash/src/services/api.ts`
- `pastita-dash/src/types/index.ts`
- `pastita-dash/src/hooks/useWhatsAppWS.ts`
- `pastita-dash/src/context/WhatsAppWsContext.tsx`
- `pastita-dash/src/pages/whatsapp/WhatsAppInboxPage.tsx`
- `pastita-dash/src/components/chat/ChatWindow.tsx`
- `pastita-dash/src/components/chat/MessageBubble.tsx`
- `pastita-dash/src/services/conversations.ts`

## Stack

- React 18 + TypeScript + Vite + Tailwind CSS
- @tanstack/react-query for server state
- Axios (`src/services/api.ts`) — Token auth via `Authorization: Token <token>` header
- React Router v6
- date-fns (ptBR locale)

## Critical Patterns

### Media Message Guard

`message.content` is a JSON object for audio/image/video messages, NOT a string.
Always guard before rendering:

```typescript
typeof message.content === 'string'
  ? message.content
  : mediaTypeLabel(message.content) // e.g. "🎵 Áudio"
```

Failing to guard causes React error #31 ("Objects are not valid as a React child").

### Handover

Always use the service wrappers — never call the handover endpoint directly:

```typescript
await conversationsService.switchToHuman(conversationId)
await conversationsService.switchToAuto(conversationId)
```

These atomically update both `Conversation.mode` (bot pipeline) and `ConversationHandover.status` (UI).

### Multipart Uploads

Never set `Content-Type` manually on FormData requests. Let the browser set the boundary:

```typescript
// WRONG
headers: { 'Content-Type': 'application/json' }

// CORRECT — omit Content-Type, axios/fetch handles it
const form = new FormData()
form.append('file', file)
await api.post('/endpoint/', form)
```

### Auth

DRF Token only. No JWT. Header: `Authorization: Token <token>`. On 401, clear token and redirect to `/login`.

## Review Questions

- Which WhatsApp WebSocket usage paths go through `useWhatsAppWS.ts` vs `WhatsAppWsContext.tsx`?
- Where does the dashboard set `Content-Type` on uploads (regression risk)?
- Which TypeScript types in `src/types/index.ts` diverge from current server2 API responses?
- Which service methods return fake success for unimplemented backend capabilities?
- Are there duplicate chat surfaces rendering the same conversation through different components?

## Output Format

- Bug/type mismatch: file + line + current vs expected shape.
- Consolidation: which files to merge, what the shared interface looks like.
- For upload fixes: confirm the specific header/interceptor location.

## Boundaries

- Do not change server2 APIs without involving `server2-backend-general`.
- Do not remove fake-success methods without checking if UI shows an explicit unsupported state instead.
- Coordinate type changes that affect multiple pages with a full search for callers.
