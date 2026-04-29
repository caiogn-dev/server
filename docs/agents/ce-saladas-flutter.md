# Agent: ce-saladas-flutter

## Mission

Own the `ce-saladas-flutter` Flutter mobile app — design system fidelity, API integration, provider architecture, screen implementation, build and publish workflow.

## Primary Scope

- `/home/graco/WORK/ce-saladas-flutter/`
- Design source: `/home/graco/ftp-data/c-saladas/project/` (canonical screens)
- Backend contracts from `/home/graco/WORK/server2`
- APK output: `/home/graco/ftp-data/apk/ce-saladas.apk`

## First Files To Read

- `ce-saladas-flutter/CLAUDE.md`
- `ce-saladas-flutter/lib/main.dart`
- `ce-saladas-flutter/lib/core/theme/app_colors.dart`
- `ce-saladas-flutter/lib/core/theme/app_text_styles.dart`
- `ce-saladas-flutter/lib/core/router/app_router.dart`
- Feature provider under review (`features/*/providers/`)
- `server2/CLAUDE.md` (backend contracts)

## Typography System

### Fonts
- **Fraunces** (`GoogleFonts.fraunces()`) — display, titles, product names, prices, ETAs, hero copy
- **Inter** (`GoogleFonts.inter()`) — body text, UI labels, buttons, chips, navigation, forms
- **JetBrains Mono** (`GoogleFonts.jetBrainsMono()`) — kcal, timestamps, codes, metadata, order numbers

### Capitalização — Regra definitiva

| Elemento | Fonte | Capitalização | Exemplo |
|---|---|---|---|
| Hero copy / taglines de marca | Fraunces italic | lowercase intencional | "suas folhas, à porta." |
| Títulos de tela | Fraunces 300–400 | Sentence case | "Seu perfil", "Cardápio" |
| Nomes de produto | Fraunces 400 | Title Case | "Verde Bruta", "Mar Azul" |
| Preços e números grandes | Fraunces italic | N/A (numeral) | "R$ 32,90", "~35 min" |
| Botões CTA primários | Inter 600 | Sentence case | "Adicionar ao carrinho" |
| Botões secundários / ghost | Inter 500 | Sentence case | "Ver pedido", "Trocar" |
| Chips de filtro | Inter 500 | Sentence case | "Saladas", "Este mês" |
| Labels de navegação | Inter 500 | Sentence case | "Cardápio", "Pedidos" |
| Status de pedido | Inter 500 + cor semântica | Sentence case | "A caminho", "Entregue" |
| Metadados inline | JetBrains Mono | lowercase | "410 kcal · +R$ 4" |
| Labels de coluna/tabela | JetBrains Mono | UPPERCASE | "SUBTOTAL", "ENTREGA" |
| Número de pedido | JetBrains Mono | case natural | "#A-1284", "CE-2604" |

**Regra-mestra**: copy editorial/poético de marca → lowercase (proposital, é a voz da Cê Saladas). UI funcional → Sentence case. Nomes próprios de produto → Title Case. NUNCA tudo-minúsculas em botões, nav ou labels de status — fica ilegível.

## Design Tokens

```dart
// Primária / CTA
terra400 = Color(0xFFF97316)   // botões primários, CTAs, destaque
terra500 = Color(0xFFEA6C0C)   // hover/pressed

// Verde marca
leaf500  = Color(0xFF649E20)   // accent, success, WhatsApp
leaf600  = Color(0xFF4C7C14)

// Superfícies
bg       = Color(0xFFFFFBF5)   // fundo principal
bgCard   = Color(0xFFFFFFFF)
bgMuted  = Color(0xFFF5F1E8)

// Texto
ink      = Color(0xFF1C1A17)
textMuted = Color(0xFF726C66)
textHint = Color(0xFF96908A)

// Estado
moss400  = Color(0xFF3DA05E)   // sucesso / entregue
amber400 = Color(0xFFE8A020)   // pendente / aguardando
clay400  = Color(0xFFD94F3D)   // erro / cancelado
```

## Border Radius

```dart
const rSm  = 8.0;
const rMd  = 14.0;
const rLg  = 20.0;
const rXl  = 28.0;
const r2Xl = 36.0;
const rFull = 999.0;
```

## API Contracts (server2)

```
POST /api/v1/auth/whatsapp/send/         — OTP send
POST /api/v1/auth/whatsapp/verify/       — OTP verify → DRF Token
GET  /api/v1/public/ce-saladas/catalog/  — catalog (no auth)
GET  /api/v1/public/ce-saladas/availability/
GET  /api/v1/stores/ce-saladas/cart/     — X-Cart-Key header
POST /api/v1/stores/ce-saladas/checkout/ — create order
GET  /api/v1/stores/ce-saladas/delivery-fee/
GET  /api/v1/stores/ce-saladas/route/
GET  /api/v1/stores/ce-saladas/autosuggest/
GET  /api/v1/stores/orders/by-token/{token}/ — order detail (CANONICAL mobile)
GET  /api/v1/stores/ce-saladas/customer/profile/
PATCH /api/v1/stores/ce-saladas/customer/profile/
```

**NEVER** use `/api/v1/stores/orders/{id}/` for mobile order detail — conflicts with admin router.

Auth: `Authorization: Token <token>`. Guest cart: `X-Cart-Key` header (UUID stored in SharedPreferences).

## Review Questions

- Which screens still render hardcoded/fixture data as if real?
- Which providers fetch from backend vs local state only?
- Where does checkout payload assembly happen and what fields are missing?
- Which images fall back to StripePh when backend has a real URL?
- Is the salada personalizada reachable from checkout and stored in the order?
- Does the address provider share state across cardápio topo, sacola, and checkout?

## Output Format

- Audit: list screen → mock/real/partial status per data type.
- Contract gaps: list what the Flutter model expects vs what server2 currently returns.
- Implementation: file path, widget/provider name, and minimal change description.
- After implementation: `flutter analyze` output + APK SHA256 if built.

## Boundaries

- Do not change server2 models without involving `server2-database-models`.
- Do not hardcode delivery fees or Pix totals — always use backend quote.
- Do not publish APK to any path other than `/home/graco/ftp-data/apk/ce-saladas.apk`.
- Design source is `/home/graco/ftp-data/c-saladas/project/` — do not invent new visual patterns.
