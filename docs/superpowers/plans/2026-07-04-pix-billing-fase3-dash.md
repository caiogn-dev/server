# PIX Billing — Fase 3: tela de fatura + aviso de reativação no dash

**Origem:** seção 7 do design `docs/superpowers/specs/2026-07-04-pix-monthly-billing-design.md`.
**Depende de:** Fase 1 (backend) COMPLETA — endpoints `GET /stores/{slug}/invoices/`, `GET /stores/{slug}/invoices/current/`, `annual_price` em `/public/plans/`, campo `StoreSubscription.downgraded_for_nonpayment`.

## Objetivo

Dar ao dono da loja, no painel, a fatura PIX mensal/anual (QR + copia-e-cola), o histórico
de faturas, um toggle mensal/anual de exibição de preço, e — o "aviso" que o usuário exigiu —
um **banner não-dismissível de reativação** quando a loja caiu pro Grátis por inadimplência.

## Contexto real (verificado no código, não no design)

- **Endpoint de fatura já retorna** (Task 7): `{ id, amount, status, kind, pix_code, pix_qr_code,
  ticket_url, expires_at, period_key, paid_at }`. **NÃO** retorna `period_start`/`period_end`/`due_date`
  do design — o `Invoice` do dash reconcilia com os campos reais (`expires_at` como vencimento,
  `period_key` `YYYY-MM`/`YYYY` como rótulo do período).
- **`/subscription/` NÃO expõe `downgraded_for_nonpayment` hoje** (`apps/stores/api/views/subscription_views.py:62-68`).
  O banner de aviso depende disso → **Task 1 (backend)** adiciona o campo.
- **Não existe endpoint para trocar o ciclo (mensal↔anual)** na Fase 1. `annual_price` já vem no
  `/public/plans/`. Portanto o toggle mensal/anual é **só de exibição de preço** (anual = mensal×10,
  "2 meses grátis"). Persistir o ciclo escolhido fica fora desta fase (Fase 2 / subscribe-time).
- **Markup PIX já existe** em `OrderDetailContent.tsx:826-866` (copia-e-cola + `<img>` do QR base64
  com fallback `data:image/png;base64,` + botão Copiar + link ticket) — é a fonte do `PixInvoicePanel`.
- **Faturas das 4 lojas reais (billing_exempt)** = `generate_invoice` retorna `None` → endpoint devolve
  `{"invoice": null}` → o painel simplesmente não mostra seção de fatura. Deploy é seguro/no-op pra elas.
- Rotas dash: `/assinatura` → `SubscriptionManagementPage` (`src/App.tsx:189`). Navegação real = `Navbar.tsx`.

## Harness de teste

- **server2:** `docker compose exec -T web python manage.py test <modulo> -v 2` (de `/home/graco/WORK/server2`).
  Rodar módulos nomeados (discovery do pacote inteiro tem bug pré-existente).
- **dash:** `cd /home/graco/WORK/pastita-dash && npm test -- <arquivo>` (Jest). `npm run build` p/ checar TS.
  `vite.config.ts` local fica **não-commitado** (padrão do repo).

## Convenções

- TDD Iron Law: teste primeiro → RED → código mínimo → GREEN → zero regressão.
- Commits em português. server2 → branch `development`; pastita-dash → branch `main`.
- Não hardcodar slug de tenant; usar `useStore()`.
- Item de nav novo (se houver) vai na `Navbar.tsx`, nunca na `Sidebar.tsx` (legado morto).

---

## Task 1 (server2): `/subscription/` expõe `downgraded_for_nonpayment`

**Files:**
- Modify: `apps/stores/api/views/subscription_views.py` (`StoreSubscriptionDetailView.get`, dict de resposta L62-68)
- Test: `apps/stores/tests/test_subscription_management.py` (ou `test_subscription.py` — usar o que já tem classe de detail)

**Step 1 — teste que falha:**
```python
def test_subscription_detail_expoe_downgraded_flag(self):
    sub = StoreSubscription.objects.create(store=self.store, plan="pro",
                                            downgraded_for_nonpayment=True)
    self.client.force_authenticate(self.owner)
    r = self.client.get(f"/api/v1/stores/{self.store.slug}/subscription/")
    self.assertEqual(r.status_code, 200)
    self.assertTrue(r.data["downgraded_for_nonpayment"])
```
(reusar o setUp da classe de detail existente: User + Store(owner=user); confirmar nome real do campo no model `StoreSubscription`.)

**Step 2 — RED:** `docker compose exec -T web python manage.py test apps.stores.tests.test_subscription_management -v 2` → falha (KeyError).

**Step 3 — código mínimo:** adicionar `'downgraded_for_nonpayment': sub.downgraded_for_nonpayment,` ao dict retornado em L62-68. (Confirmar o nome exato do campo no model antes.)

**Step 4 — GREEN:** rodar o módulo + `test_subscription` p/ garantir zero regressão.

**Step 5 — commit:**
```bash
git commit -am "feat(billing): expoe downgraded_for_nonpayment no endpoint de assinatura"
```

---

## Task 2 (dash): `billing.ts` — tipo `Invoice` + clientes de fatura + flag no status

**Files:**
- Modify: `src/services/billing.ts`
- Test: `src/services/__tests__/billing.test.ts` (criar se não existir; mockar `./api` como os outros testes de serviço)

**Interfaces a produzir:**
```ts
export interface Invoice {
  id: string;
  amount: number;
  status: string;            // ex.: 'pending' | 'completed' | 'expired'
  kind: 'monthly' | 'annual' | null;
  pix_code: string | null;       // copia-e-cola (qr_code)
  pix_qr_code: string | null;    // base64 (qr_code_base64)
  ticket_url: string | null;
  expires_at: string | null;     // vencimento
  period_key: string | null;     // 'YYYY-MM' | 'YYYY'
  paid_at: string | null;
}

export async function getCurrentInvoice(storeSlug: string): Promise<Invoice | null> {
  const { data } = await api.get(`/stores/${storeSlug}/invoices/current/`);
  return data?.invoice ?? null;
}

export async function listInvoices(storeSlug: string): Promise<Invoice[]> {
  const { data } = await api.get(`/stores/${storeSlug}/invoices/`);
  return Array.isArray(data?.invoices) ? data.invoices : [];
}
```
Também: adicionar `downgraded_for_nonpayment?: boolean` em `SubscriptionStatus`; adicionar
`annual_price?: number` em `Plan` (só planos pagos vêm com o campo).

**Step 1 — teste que falha:** mockar `api.get`; assertar que `getCurrentInvoice` desembrulha `data.invoice`
(inclusive `null`), que `listInvoices` desembrulha `data.invoices` e devolve `[]` quando ausente.

**Step 2 — RED:** `npm test -- billing.test` → falha (exports inexistentes).

**Step 3 — código mínimo:** implementar tipos + funções acima.

**Step 4 — GREEN:** `npm test -- billing.test` verde; `npm run build` sem erro TS.

**Step 5 — commit:**
```bash
git commit -am "feat(billing): cliente de faturas PIX (getCurrentInvoice/listInvoices) + tipo Invoice"
```

---

## Task 3 (dash): componente `PixInvoicePanel` (extração do markup PIX)

**Files:**
- Create: `src/components/billing/PixInvoicePanel.tsx`
- Test: `src/components/billing/__tests__/PixInvoicePanel.test.tsx`

**Contrato do componente:**
```ts
interface PixInvoicePanelProps {
  pixCode?: string | null;
  pixQrCode?: string | null;    // base64; aplicar fallback data:image/png;base64,
  ticketUrl?: string | null;
  amount?: number | null;
  status?: string | null;       // renderiza badge: pago / pendente / expirado
  expiresAt?: string | null;    // vencimento formatado pt-BR
  onCopy?: (code: string) => void;  // default: navigator.clipboard + toast
}
```
Markup reaproveitado de `OrderDetailContent.tsx:826-866`: bloco copia-e-cola (`<code>` + botão "Copiar"),
`<img>` do QR com fallback `startsWith('data:') ? src : 'data:image/png;base64,'+src`, link ticket.
Adicionar: valor formatado (`R$ x,xx`), vencimento pt-BR, e **badge de status**
(pago=verde / pendente=âmbar / expirado=cinza). Theme-aware (tokens `border-token`, `bg-surface`, etc.).

**Step 1 — teste que falha:** renderiza panel com `pixCode`, `pixQrCode`, `status='completed'` →
assertar copia-e-cola visível, `<img>` com `src` começando em `data:image/png;base64,`, badge "Pago".
Clicar "Copiar" chama `onCopy` com o código.

**Step 2 — RED:** `npm test -- PixInvoicePanel` → falha (componente inexistente).

**Step 3 — código mínimo:** implementar o componente.

**Step 4 — GREEN:** teste verde; `npm run build` ok.

**Step 5 — commit:**
```bash
git commit -am "feat(billing): componente reutilizavel PixInvoicePanel (QR + copia-e-cola + badge)"
```

---

## Task 4 (dash): `/assinatura` — fatura atual (polling) + histórico + toggle mensal/anual

**Files:**
- Modify: `src/pages/plano/SubscriptionManagementPage.tsx`
- Test: `src/pages/plano/__tests__/SubscriptionManagementPage.test.tsx` (criar; mockar `../../services/billing` e `useStore`)

**O que adicionar:**
1. **Seção "Fatura atual"**: no load, `getCurrentInvoice(slug)` (gera idempotente no backend). Se `!= null`
   e `status` pendente → renderizar `<PixInvoicePanel .../>`. Se pago → estado "em dia". Se `null` (ex.:
   loja isenta / sem assinatura) → não mostra a seção.
2. **Polling**: enquanto a fatura atual estiver pendente, refetch a cada ~15s (`setInterval`, limpar no
   unmount) para virar "pago" quando o webhook aplicar. Parar o polling ao ficar pago/expirado.
3. **Histórico**: `listInvoices(slug)` → lista compacta (período `period_key`, valor, status, data paga).
4. **Toggle mensal/anual (só exibição)**: estado local `cycle: 'monthly'|'annual'`. Na grade de planos,
   quando `annual`, mostrar `annual_price` (=`monthly_price×10`) com selo "2 meses grátis" e "/ano".
   Não altera o backend (persistência de ciclo fora de escopo).

**Step 1 — teste que falha:** mock `getCurrentInvoice` → fatura pendente; assertar que `PixInvoicePanel`
aparece. Mock com `paid_at` setado → assertar estado "em dia". Toggle p/ "anual" → assertar preço anual
exibido. `listInvoices` → assertar linha do histórico.

**Step 2 — RED:** `npm test -- SubscriptionManagementPage` → falha.

**Step 3 — código mínimo:** implementar seções + polling + toggle.

**Step 4 — GREEN:** teste verde; `npm run build` ok; rodar suíte tocada p/ zero regressão.

**Step 5 — commit:**
```bash
git commit -am "feat(assinatura): fatura PIX atual com polling + historico + toggle mensal/anual"
```

---

## Task 5 (dash): TrialBanner — aviso não-dismissível de reativação (downgraded)

**Files:**
- Modify: `src/components/layout/TrialBanner.tsx`
- Test: `src/components/layout/__tests__/TrialBanner.test.tsx`

**Comportamento:** buscar o status já é feito (`getSubscription`). Guardar também
`downgraded_for_nonpayment` do retorno. **Nova prioridade nº 1** (acima de suspended):
se `downgraded_for_nonpayment === true` → faixa vermelha **sem botão de dispensar**
(não-dismissível): "Você voltou pro plano Grátis por falta de pagamento. Reative o {plano} pra
recuperar seus recursos." + CTA `<Link to="/assinatura">Reativar</Link>`. `role="alert"`,
`aria-live="assertive"`. Não gravar/ler `DISMISS_KEY` nesse caso.

**Step 1 — teste que falha:** mock `getSubscription` resolvendo `{ status:'active',
downgraded_for_nonpayment:true, plan:'pro' }`; assertar que a faixa de reativação aparece,
que **não há** botão "Dispensar", e que o CTA aponta pra `/assinatura`. Mock com
`downgraded_for_nonpayment:false` → não aparece essa faixa (cai nos casos existentes).

**Step 2 — RED:** `npm test -- TrialBanner` → falha (caso novo inexistente).

**Step 3 — código mínimo:** adicionar o novo caso e guardar a flag no state.

**Step 4 — GREEN:** teste verde; `npm run build` ok; suíte do TrialBanner sem regressão.

**Step 5 — commit:**
```bash
git commit -am "feat(assinatura): banner nao-dismissivel de reativacao quando caiu pro Gratis"
```

---

## Task 6 (dash, OPCIONAL): dedup — `OrderDetailContent` reusa `PixInvoicePanel`

Refatorar `OrderDetailContent.tsx:826-866` para renderizar `<PixInvoicePanel/>` em vez do markup inline,
removendo a duplicação. **Comportamento idêntico** — guardado pelos testes existentes de `OrderDetailContent`.
Só fazer se as Tasks 1-5 passarem e sobrar folga; é higiene, não requisito. Rodar a suíte de
`OrderDetailContent` inteira antes/depois. Commit: `refactor(pedidos): OrderDetailContent reusa PixInvoicePanel`.

---

## Ordem e verificação final

1. Task 1 (server2) primeiro — desbloqueia o aviso.
2. Tasks 2→3→4→5 no dash (2 e 3 são fundação de 4 e 5).
3. Task 6 opcional.
4. **Verificação:** `npm run build` (TS) + suíte tocada verde no dash; módulos de assinatura verdes no server2.
   Nada é deployável com efeito real até `BILLING_PIX_ENABLED=true` no backend — dash é no-op enquanto o
   endpoint devolver `invoice: null` (lojas isentas / flag off).
5. Deploy dash = push na `main` → Vercel auto-deploy. Deploy server2 = fluxo `development`.
