# Fase 2 — Checklist "Primeiros Passos" (Onboarding Guide) — Design

**Data:** 2026-06-30
**Programa:** Cardapidex SaaS, sequência dinheiro-primeiro. Fase 1 (cobrança) está no ar; esta é a **Fase 2 (Guide)** — ajudar o dono NOVO a deixar a loja pronta pra vender depois do cadastro.

## Objetivo

Um dono que acabou de se cadastrar (trial) vê, no topo do painel, um card **"Primeiros passos"** com as tarefas que faltam pra loja vender de verdade. Cada item marca sozinho conforme o dono completa a tarefa real (não há "marcar à mão"). O card some quando tudo está feito.

## Decisões travadas (do brainstorm)

1. **Forma:** checklist fixo no dashboard (não wizard forçado, não tour de tooltips). Sempre visível enquanto incompleto, não bloqueia nada.
2. **Detecção:** 100% **derivada de dados reais** — sem model novo, sem migration, sem flag manual, sem drift. Um passo só fica ✅ se a tarefa foi feita de verdade.
3. **WhatsApp:** o passo deriva apenas de **ter o número de celular** configurado (`whatsapp_number`), NÃO do Meta Embedded Signup / coexistence.
4. **Entrega:** deriva de **existir ≥1 zona de entrega** (`delivery_zones.exists()`). Não usar `default_delivery_fee` (tem default 10.00 → sempre "preenchido") nem `pickup_enabled` (default True).
5. **Dispensar:** flag em **localStorage** (por navegador). Sem endpoint de escrita; YAGNI.

## Passos do checklist (derivação)

Todos derivados de campos já existentes no `Store` (`apps/stores/models/base.py`) e relações:

| key | label | regra (done quando) |
|---|---|---|
| `account` | Conta criada | sempre `true` (motivador — começa em 1/6) |
| `logo` | Adicionar logo | `bool(store.logo or store.logo_url)` |
| `product` | Cadastrar 1º produto | `store.products.exists()` (related_name `products`) |
| `delivery` | Configurar entrega | `store.delivery_zones.exists()` (related_name `delivery_zones`, model `StoreDeliveryZone`) |
| `hours` | Definir horário | `bool(store.operating_hours)` (JSONField dict não-vazio) |
| `whatsapp` | Informar WhatsApp | `bool(store.whatsapp_number)` |

`total = 6`. `completed = nº de done`. `all_done = completed == total`.

Cada passo carrega um `action_path` (rota no painel) pra onde o link leva quando incompleto. Os paths reais serão lidos do roteador do `pastita-dash` no momento da implementação (ex.: produtos, configurações de entrega, horário, marca/identidade, contato/whatsapp). NÃO inventar rota — confirmar no `App.tsx`.

## Arquitetura

### Backend (server2)
- **Função pura** `apps/stores/services/onboarding_checklist.py:build_checklist(store) -> list[ChecklistStep]`.
  - Só leituras ORM; cada passo é uma função de derivação isolada e testável.
  - `ChecklistStep` = dataclass `{key: str, label: str, done: bool, action_path: str}`.
- **Endpoint** `GET /api/v1/stores/<slug>/onboarding/checklist/`
  - View em `apps/stores/api/views/` (nova ou arquivo de onboarding), permissão = mesmo `_can_manage(store, user)` usado pelas views de assinatura (owner / staff da loja / superuser; **`is_staff` NÃO dá acesso cross-tenant**).
  - Resposta: `{ "steps": [{key,label,done,action_path}], "completed": int, "total": int, "all_done": bool }`.
  - Rota em `apps/stores/urls.py`, no mesmo nível de `subscription/` (prefixo `<slug:store_slug>/`).

### Frontend (pastita-dash)
- **Service** `src/services/onboarding.ts`: adicionar `getChecklist(storeSlug) -> Promise<OnboardingChecklist>` + tipos `ChecklistStep`/`OnboardingChecklist`. (arquivo já existe; só estende.)
- **Componente** `src/components/onboarding/OnboardingChecklist.tsx`:
  - Busca o checklist no mount (via `useStore()` p/ o slug).
  - Renderiza card com barra de progresso `N/6`, lista de passos (✅ feitos / ⬜ pendentes com link pro `action_path`).
  - **Auto-some** quando `all_done`. Link "dispensar" grava `localStorage['onboarding_dismissed_<slug>']='1'` e esconde o card.
  - Estados: loading (skeleton discreto), erro (silencioso — `.catch` e não renderiza, igual ao TrialBanner), vazio.
  - Tokens do tema dark-luxe (`bg-surface-token`/`text-fg-token`/`bg-brand`/`border-border-token`), consistente com SubscriptionManagementPage/TrialBanner.
- **Montagem:** no topo do dashboard home (rota inicial logada — confirmar o componente/página real no `App.tsx`/layout). Renderiza só se `!all_done && !dismissed`.

## Fluxo de dados

```
Dashboard home monta
  → GET /stores/<slug>/onboarding/checklist/
  → render card (progresso + passos)
  → clica passo pendente → navega pro action_path (Link react-router)
  → dono completa a tarefa real (cria produto, define horário, etc.)
  → ao voltar pro home, refetch → passo vira ✅
  → quando completed == total → card some
```

Sem realtime; refetch no mount do home é suficiente.

## Isolamento / unidades

- `build_checklist(store)` — função pura, uma responsabilidade (derivar estado), testável sem HTTP.
- Endpoint/view — só auth + serialização do retorno da função.
- `OnboardingChecklist.tsx` — só apresentação + dismissal local; consome o service.
- `onboarding.ts` getChecklist — só o contrato HTTP.

Cada unidade entendível e testável isolada; trocar a regra de um passo não quebra o front (contrato `{key,label,done,action_path}` estável).

## Erros e bordas

- Loja sem nada → `completed=1` (só `account`), card aparece com 5 pendências.
- Loja já estabelecida (as 3 isentas) → provavelmente `all_done` → card não aparece; se faltar 1 (ex.: `whatsapp_number` vazio), o dono pode "dispensar".
- Endpoint sem permissão → 403 (igual às views de assinatura).
- Falha de rede no front → card não renderiza (não quebra o layout do home).

## Testes

**Backend** (Docker harness `bash scripts/sdd-test.sh ... --reuse-db`):
- `build_checklist`: loja vazia → só `account` done; cada passo vira done ao preencher o dado correspondente (logo, produto, zona de entrega, operating_hours, whatsapp_number); `all_done` quando todos.
- Endpoint: 200 com shape correto pro owner; 403 pra usuário sem permissão (não-owner/não-superuser).

**Frontend** (jest):
- `OnboardingChecklist`: renderiza N/6 e os passos; passo pendente tem link pro `action_path`; some quando `all_done`; some quando localStorage dismissed. Output pristine (sem warning act()).

## Fora de escopo (YAGNI)

- Sem `StoreOnboarding` model / migration / flags manuais.
- Sem tour de tooltips, sem wizard modal forçado.
- Sem endpoint de escrita pra dismissal (localStorage basta).
- Sem realtime/websocket.
- Sem gamificação além da barra de progresso.

## Constraints globais (herdadas)

- TDD obrigatório; zero regressão.
- `is_staff` NÃO dá acesso cross-tenant (só owner/staff-da-loja/superuser).
- Commits em português, terminando com `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Dash: runner jest; `vite.config.ts` NÃO commitado; build `tsc && vite build` verde (Vercel).
- server2: harness Docker `scripts/sdd-test.sh`; deploy `deploy.sh` (imagem baked).
