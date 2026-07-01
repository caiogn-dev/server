# Onboarding Fase B — Wizard de Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wizard full-screen que, no 1º login de loja incompleta, conduz o dono pelos 5 passos de setup (logo, produto, entrega, horário, WhatsApp) com mini-forms embutidos sobre os services existentes — auto-abre uma vez, retomável pelo card.

**Architecture:** Backend ganha 1 flag (`Store.onboarding_wizard_seen`) exposta no endpoint de checklist + um endpoint de escrita. Frontend ganha um shell (`OnboardingWizard`, headlessui Dialog + framer-motion) que orquestra 5 step-forms dedicados; cada step chama um service existente. Progresso segue derivado do `build_checklist` (Fase 2). O card (Fase A) ganha o CTA que abre o wizard.

**Tech Stack:** Django 4 + DRF (server2, harness Docker); React + Vite + TS + jest, `@headlessui/react` (Dialog), `framer-motion` (transições), `lucide-react` (ícones) — todos já instalados.

## Global Constraints

- **TDD**; zero regressão. `is_staff` NÃO cross-tenant (`_can_manage`). Sem dependência nova.
- **Backend:** harness `bash scripts/sdd-test.sh <path> --reuse-db -q`. Migration de 1 campo (additive, nullable/default).
- **Dash:** runner **jest**; `npx tsc --noEmit` 0; output pristine (zero `act()` warning — para framer-motion nos testes, mockar `framer-motion` com um stub que renderiza `children`, ver Task B4). `vite.config.ts` NUNCA em commit.
- **Tokens dark-luxe** (`bg-surface-token`/`text-fg-token`/`text-fg-muted-token`/`bg-brand`/`brand`/`border-border-token`/`surface-muted-token`). Não inventar token.
- Commits PT + `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Contrato wizard_seen:** o endpoint `GET .../onboarding/checklist/` passa a devolver `{..., wizard_seen: bool}`. Escrita só via `POST .../onboarding/seen/`.
- Services de escrita (confirmados): `storesApi.updateStore(id, data)`, `storesApi.updateStoreWithFiles(id, {logo: File, ...})`, `productsService.createProduct(CreateProduct)` (campos obrig.: `name, price, sku, stock_quantity`), `deliveryService.createZone(CreateDeliveryZone)` (obrig.: `name, delivery_fee`). `useStore()` → `{ storeId, storeSlug, store }`.

---

## File Structure

**server2:**
- `apps/stores/models/base.py` — MODIFY: campo `onboarding_wizard_seen`.
- migration (autogerada).
- `apps/stores/api/views/onboarding_views.py` — MODIFY: incluir `wizard_seen` no GET; nova `StoreOnboardingSeenView` (POST).
- `apps/stores/urls.py` — MODIFY: rota `onboarding/seen/`.
- testes: `test_onboarding_checklist_api.py` (estende), `test_onboarding_seen_api.py` (novo).

**pastita-dash** (`src/components/onboarding/wizard/`):
- `src/services/onboarding.ts` — MODIFY: `markWizardSeen` + `wizard_seen` no tipo.
- `wizard/OnboardingWizard.tsx` — shell (Dialog + framer-motion + progresso + nav).
- `wizard/useOnboardingWizard.ts` — hook de orquestração (passo atual, primeiro pendente, navegação).
- `wizard/steps/StepLogo.tsx`, `StepProduct.tsx`, `StepDelivery.tsx`, `StepHours.tsx`, `StepWhatsApp.tsx` — mini-forms.
- `OnboardingChecklist.tsx` — MODIFY: CTA "Continuar configuração" abre o wizard.
- `src/pages/dashboard/DashboardPage.tsx` — MODIFY: monta o wizard + auto-open.
- testes jest correspondentes.

---

## Task B1: Backend — campo `onboarding_wizard_seen` + expor no checklist

**Files:**
- Modify: `apps/stores/models/base.py` (após `onboarding_completed`)
- Modify: `apps/stores/api/views/onboarding_views.py`
- Create: migration
- Test: `apps/stores/tests/test_onboarding_checklist_api.py` (estende)

**Interfaces:**
- Produces: `Store.onboarding_wizard_seen: BooleanField(default=False)`; o GET do checklist devolve `wizard_seen: bool`.

- [ ] **Step 1: Escrever o teste falhando** — adicionar ao `test_onboarding_checklist_api.py`:

```python
    def test_checklist_inclui_wizard_seen(self):
        self.client.force_authenticate(self.owner)
        r = self.client.get('/api/v1/stores/loja/onboarding/checklist/')
        self.assertIn('wizard_seen', r.json())
        self.assertFalse(r.json()['wizard_seen'])  # default
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `bash scripts/sdd-test.sh apps/stores/tests/test_onboarding_checklist_api.py::OnboardingChecklistAPITest::test_checklist_inclui_wizard_seen --reuse-db -q`
Expected: FAIL — `KeyError: 'wizard_seen'` (ou AttributeError no campo).

- [ ] **Step 3: Adicionar o campo no modelo**

Em `apps/stores/models/base.py`, logo após o campo `onboarding_completed`:

```python
    onboarding_wizard_seen = models.BooleanField(
        default=False,
        help_text="True após o dono ver/fechar o wizard de setup a 1ª vez (controla o auto-open).",
    )
```

- [ ] **Step 4: Gerar e aplicar a migration**

Run:
```bash
docker compose exec -T web python manage.py makemigrations stores
bash scripts/sdd-test.sh --collect-only -q  # noop p/ garantir import; ou pular
docker compose exec -T web python manage.py migrate stores
```
Expected: cria `00XX_store_onboarding_wizard_seen.py` e aplica.

- [ ] **Step 5: Expor no GET do checklist**

Em `apps/stores/api/views/onboarding_views.py`, no `get` da `StoreOnboardingChecklistView`, trocar o `return Response(build_checklist(store))` por:

```python
        data = build_checklist(store)
        data['wizard_seen'] = store.onboarding_wizard_seen
        return Response(data)
```

- [ ] **Step 6: Rodar e ver passar**

Run: `bash scripts/sdd-test.sh apps/stores/tests/test_onboarding_checklist_api.py --reuse-db -q`
Expected: PASS (todos).

- [ ] **Step 7: Commit**

```bash
git add apps/stores/models/base.py apps/stores/migrations/ apps/stores/api/views/onboarding_views.py apps/stores/tests/test_onboarding_checklist_api.py
git commit -m "feat(onboarding): campo onboarding_wizard_seen + expor wizard_seen no checklist"
```

---

## Task B2: Backend — endpoint `POST onboarding/seen/`

**Files:**
- Modify: `apps/stores/api/views/onboarding_views.py` (nova view)
- Modify: `apps/stores/urls.py`
- Test: `apps/stores/tests/test_onboarding_seen_api.py` (novo)

**Interfaces:**
- Consumes: `_can_manage` (de subscription_views), campo da B1.
- Produces: `POST /api/v1/stores/<slug>/onboarding/seen/` → seta `onboarding_wizard_seen=True`, 200 `{wizard_seen: true}`; 403 não-owner. Idempotente.

- [ ] **Step 1: Escrever o teste falhando**

```python
# apps/stores/tests/test_onboarding_seen_api.py
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from apps.stores.models import Store

User = get_user_model()


class OnboardingSeenAPITest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono', email='d@t.local', password='x')
        self.store = Store.objects.create(name='Loja', slug='loja', owner=self.owner)
        self.client = APIClient()

    def test_owner_marca_seen(self):
        self.client.force_authenticate(self.owner)
        r = self.client.post('/api/v1/stores/loja/onboarding/seen/')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['wizard_seen'])
        self.store.refresh_from_db()
        self.assertTrue(self.store.onboarding_wizard_seen)

    def test_idempotente(self):
        self.client.force_authenticate(self.owner)
        self.client.post('/api/v1/stores/loja/onboarding/seen/')
        r = self.client.post('/api/v1/stores/loja/onboarding/seen/')
        self.assertEqual(r.status_code, 200)

    def test_nao_owner_403(self):
        outro = User.objects.create_user(username='o2', email='o2@t.local', password='x')
        self.client.force_authenticate(outro)
        r = self.client.post('/api/v1/stores/loja/onboarding/seen/')
        self.assertEqual(r.status_code, 403)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `bash scripts/sdd-test.sh apps/stores/tests/test_onboarding_seen_api.py --reuse-db -q`
Expected: FAIL — 404 (rota não existe).

- [ ] **Step 3: Implementar a view** — em `onboarding_views.py`, adicionar:

```python
class StoreOnboardingSeenView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, store_slug):
        store = get_object_or_404(Store, slug=store_slug)
        if not _can_manage(store, request.user):
            return Response({'detail': 'Sem permissão.'}, status=403)
        if not store.onboarding_wizard_seen:
            store.onboarding_wizard_seen = True
            store.save(update_fields=['onboarding_wizard_seen'])
        return Response({'wizard_seen': True})
```

(garanta que `permissions`, `get_object_or_404`, `APIView`, `Response`, `Store`, `_can_manage` já estão importados no arquivo — a B1/Fase 2 já os trouxe.)

- [ ] **Step 4: Registrar a rota** — em `apps/stores/urls.py`, ao lado de `onboarding/checklist/`:

```python
from .api.views.onboarding_views import StoreOnboardingChecklistView, StoreOnboardingSeenView
# ...
    path('onboarding/seen/', StoreOnboardingSeenView.as_view(), name='store-onboarding-seen'),
```

- [ ] **Step 5: Rodar e ver passar**

Run: `bash scripts/sdd-test.sh apps/stores/tests/test_onboarding_seen_api.py --reuse-db -q`
Expected: PASS (3 testes).

- [ ] **Step 6: Commit**

```bash
git add apps/stores/api/views/onboarding_views.py apps/stores/urls.py apps/stores/tests/test_onboarding_seen_api.py
git commit -m "feat(onboarding): endpoint POST onboarding/seen marca wizard visto"
```

---

## Task B3: Dash — service `markWizardSeen` + tipo

**Files:**
- Modify: `src/services/onboarding.ts`
- Test: `src/services/__tests__/onboarding.test.ts` (estende)

**Interfaces:**
- Produces: `markWizardSeen(slug): Promise<void>`; `OnboardingChecklist` ganha `wizard_seen?: boolean`.

- [ ] **Step 1: Teste falhando** — adicionar ao `onboarding.test.ts`:

```ts
  it('markWizardSeen faz POST no endpoint seen', async () => {
    (api.post as jest.Mock).mockResolvedValue({ data: { wizard_seen: true } });
    await markWizardSeen('loja');
    expect(api.post).toHaveBeenCalledWith('/stores/loja/onboarding/seen/');
  });
```

E no topo do arquivo, garantir o import: `import { getChecklist, markWizardSeen } from '../onboarding';` e que o mock de `../api` expõe `post: jest.fn()` (ver o mock existente; se só tiver `get`, adicionar `post`).

- [ ] **Step 2: Rodar e ver falhar**

Run: `npm test -- onboarding`
Expected: FAIL — `markWizardSeen is not a function`.

- [ ] **Step 3: Implementar** — em `src/services/onboarding.ts`:

Adicionar `wizard_seen?: boolean;` à interface `OnboardingChecklist`, e ao fim do arquivo:

```ts
export async function markWizardSeen(storeSlug: string): Promise<void> {
  await api.post(`/stores/${storeSlug}/onboarding/seen/`);
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `npm test -- onboarding`
Expected: PASS. Depois `npx tsc --noEmit` → 0.

- [ ] **Step 5: Commit**

```bash
git add src/services/onboarding.ts src/services/__tests__/onboarding.test.ts
git commit -m "feat(dash): service markWizardSeen + tipo wizard_seen"
```

---

## Task B4: Dash — shell `OnboardingWizard` + hook

**Files:**
- Create: `src/components/onboarding/wizard/useOnboardingWizard.ts`
- Create: `src/components/onboarding/wizard/OnboardingWizard.tsx`
- Test: `src/components/onboarding/wizard/__tests__/OnboardingWizard.test.tsx`

**Interfaces:**
- Produces:
  - `useOnboardingWizard(steps: WizardStepDef[], initialKey?: string)` → `{ index, current, total, isFirst, isLast, next, back, goToFirstPending }`.
  - `WizardStepDef = { key: string; title: string; render: (props: { onSaved: () => void }) => ReactNode }`.
  - `OnboardingWizard({ open, steps, onClose, startKey })` — Dialog full-screen com progresso e navegação. Voltar / Pular / (cada step chama `onSaved` → avança). Fecha via `onClose`.

- [ ] **Step 1: Teste falhando**

```tsx
// src/components/onboarding/wizard/__tests__/OnboardingWizard.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import OnboardingWizard from '../OnboardingWizard';

// framer-motion: stub que só renderiza children (evita timers/act no jsdom)
jest.mock('framer-motion', () => ({
  motion: new Proxy({}, { get: () => (p: any) => <div>{p.children}</div> }),
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

const steps = [
  { key: 'a', title: 'Passo A', render: ({ onSaved }: any) => <button onClick={onSaved}>salvar-a</button> },
  { key: 'b', title: 'Passo B', render: ({ onSaved }: any) => <button onClick={onSaved}>salvar-b</button> },
];

describe('OnboardingWizard', () => {
  it('mostra o passo atual e avança ao salvar', () => {
    render(<OnboardingWizard open steps={steps} onClose={() => {}} />);
    expect(screen.getByText('Passo A')).toBeTruthy();
    fireEvent.click(screen.getByText('salvar-a'));
    expect(screen.getByText('Passo B')).toBeTruthy();
  });

  it('Pular avança sem salvar', () => {
    render(<OnboardingWizard open steps={steps} onClose={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /pular/i }));
    expect(screen.getByText('Passo B')).toBeTruthy();
  });

  it('não renderiza quando open=false', () => {
    const { container } = render(<OnboardingWizard open={false} steps={steps} onClose={() => {}} />);
    expect(container.textContent).not.toMatch(/passo a/i);
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `npm test -- OnboardingWizard`
Expected: FAIL — módulo não existe.

- [ ] **Step 3: Implementar o hook**

```ts
// src/components/onboarding/wizard/useOnboardingWizard.ts
import { useState, type ReactNode } from 'react';

export interface WizardStepDef {
  key: string;
  title: string;
  render: (props: { onSaved: () => void }) => ReactNode;
}

export function useOnboardingWizard(steps: WizardStepDef[], startKey?: string) {
  const startIndex = Math.max(0, startKey ? steps.findIndex((s) => s.key === startKey) : 0);
  const [index, setIndex] = useState(startIndex === -1 ? 0 : startIndex);
  const total = steps.length;
  const next = () => setIndex((i) => Math.min(total - 1, i + 1));
  const back = () => setIndex((i) => Math.max(0, i - 1));
  return {
    index,
    current: steps[index],
    total,
    isFirst: index === 0,
    isLast: index === total - 1,
    next,
    back,
  };
}
```

- [ ] **Step 4: Implementar o shell**

```tsx
// src/components/onboarding/wizard/OnboardingWizard.tsx
import { Fragment, type FC } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, ArrowLeft } from 'lucide-react';
import { useOnboardingWizard, type WizardStepDef } from './useOnboardingWizard';

interface OnboardingWizardProps {
  open: boolean;
  steps: WizardStepDef[];
  onClose: () => void;
  startKey?: string;
}

const OnboardingWizard: FC<OnboardingWizardProps> = ({ open, steps, onClose, startKey }) => {
  const { index, current, total, isFirst, isLast, next, back } = useOnboardingWizard(steps, startKey);
  const pct = total > 0 ? ((index + 1) / total) * 100 : 0;

  function handleSaved() {
    if (isLast) onClose();
    else next();
  }

  if (!open) return null;

  return (
    <Transition appear show={open} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <div className="fixed inset-0 bg-black/60" aria-hidden="true" />
        <div className="fixed inset-0 flex items-center justify-center p-4">
          <Dialog.Panel className="flex max-h-[90vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-border-token bg-surface-token shadow-2xl">
            <div className="border-b border-border-token px-6 py-4">
              <div className="flex items-center justify-between">
                {!isFirst ? (
                  <button onClick={back} aria-label="Voltar" className="text-fg-muted-token hover:text-fg-token">
                    <ArrowLeft className="h-5 w-5" />
                  </button>
                ) : <span className="w-5" />}
                <span className="text-sm text-fg-muted-token">{index + 1}/{total}</span>
                <button onClick={onClose} aria-label="Fechar" className="text-fg-muted-token hover:text-fg-token">
                  <X className="h-5 w-5" />
                </button>
              </div>
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-surface-muted-token">
                <div className="h-full rounded-full bg-brand transition-all duration-500" style={{ width: `${pct}%` }} />
              </div>
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-6">
              <h2 className="mb-4 text-lg font-semibold text-fg-token">{current.title}</h2>
              <AnimatePresence mode="wait">
                <motion.div
                  key={current.key}
                  initial={{ opacity: 0, x: 16 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -16 }}
                  transition={{ duration: 0.2 }}
                >
                  {current.render({ onSaved: handleSaved })}
                </motion.div>
              </AnimatePresence>
            </div>

            <div className="flex items-center justify-end gap-3 border-t border-border-token px-6 py-4">
              <button onClick={handleSaved} className="text-sm text-fg-muted-token hover:text-fg-token">
                {isLast ? 'Concluir' : 'Pular'}
              </button>
            </div>
          </Dialog.Panel>
        </div>
      </Dialog>
    </Transition>
  );
};

export default OnboardingWizard;
```

> Nota: o botão "Pular/Concluir" chama `handleSaved` (avança/fecha); cada step renderiza seu próprio botão "Salvar e continuar" que também chama `onSaved`. O teste mocka `framer-motion` (Step 1) — mantenha o uso de `motion.div`/`AnimatePresence` compatível com esse stub (só `children`).

- [ ] **Step 5: Rodar e ver passar**

Run: `npm test -- OnboardingWizard`
Expected: PASS (3 testes). `npx tsc --noEmit` → 0.

- [ ] **Step 6: Commit**

```bash
git add src/components/onboarding/wizard/useOnboardingWizard.ts src/components/onboarding/wizard/OnboardingWizard.tsx src/components/onboarding/wizard/__tests__/OnboardingWizard.test.tsx
git commit -m "feat(onboarding): shell do wizard (Dialog + progresso + navegacao) e hook"
```

---

## Task B5: Dash — os 5 mini-forms (steps)

**Files:**
- Create: `src/components/onboarding/wizard/steps/{StepLogo,StepProduct,StepDelivery,StepHours,StepWhatsApp}.tsx`
- Test: `src/components/onboarding/wizard/steps/__tests__/steps.test.tsx`

**Interfaces:**
- Cada step: `({ storeId, onSaved }: { storeId: string; onSaved: () => void }) => JSX.Element`. Valida o mínimo, chama o service, e ao sucesso chama `onSaved()`. Erro vira mensagem inline (não avança).
- Consumes: `storesApi.updateStore`/`updateStoreWithFiles`, `productsService.createProduct`, `deliveryService.createZone`.

- [ ] **Step 1: Teste falhando (um por step, mockando os services)**

```tsx
// src/components/onboarding/wizard/steps/__tests__/steps.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { act } from 'react';
import StepWhatsApp from '../StepWhatsApp';
import StepProduct from '../StepProduct';
import * as storesApi from '../../../../../services/storesApi';
import productsService from '../../../../../services/products';

jest.mock('../../../../../services/storesApi');
jest.mock('../../../../../services/products');

describe('wizard steps', () => {
  it('StepWhatsApp salva o número e chama onSaved', async () => {
    (storesApi.updateStore as jest.Mock).mockResolvedValue({});
    const onSaved = jest.fn();
    render(<StepWhatsApp storeId="s1" onSaved={onSaved} />);
    fireEvent.change(screen.getByLabelText(/whatsapp/i), { target: { value: '5563999998888' } });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /salvar/i })); });
    await waitFor(() => expect(storesApi.updateStore).toHaveBeenCalledWith('s1', { whatsapp_number: '5563999998888' }));
    expect(onSaved).toHaveBeenCalled();
  });

  it('StepProduct cria produto com sku auto + stock default', async () => {
    (productsService.createProduct as jest.Mock).mockResolvedValue({});
    const onSaved = jest.fn();
    render(<StepProduct storeId="s1" onSaved={onSaved} />);
    fireEvent.change(screen.getByLabelText(/nome/i), { target: { value: 'Coxinha' } });
    fireEvent.change(screen.getByLabelText(/preço|preco/i), { target: { value: '8.5' } });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /salvar/i })); });
    await waitFor(() => expect(productsService.createProduct).toHaveBeenCalled());
    const arg = (productsService.createProduct as jest.Mock).mock.calls[0][0];
    expect(arg.name).toBe('Coxinha');
    expect(arg.price).toBe(8.5);
    expect(arg.sku).toBeTruthy();           // auto
    expect(arg.stock_quantity).toBe(0);     // default
    expect(onSaved).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `npm test -- steps`
Expected: FAIL — módulos não existem.

- [ ] **Step 3: Implementar os 5 steps**

`StepWhatsApp.tsx`:
```tsx
import { useState, type FC } from 'react';
import { updateStore } from '../../../../services/storesApi';

const StepWhatsApp: FC<{ storeId: string; onSaved: () => void }> = ({ storeId, onSaved }) => {
  const [num, setNum] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true); setErr(null);
    try { await updateStore(storeId, { whatsapp_number: num.replace(/\D/g, '') }); onSaved(); }
    catch { setErr('Não foi possível salvar.'); } finally { setBusy(false); }
  }
  return (
    <div className="space-y-4">
      <p className="text-sm text-fg-muted-token">O número que recebe os pedidos da loja.</p>
      <label className="block text-sm">
        <span className="text-fg-token">WhatsApp</span>
        <input aria-label="WhatsApp" value={num} onChange={(e) => setNum(e.target.value)}
          placeholder="(63) 99999-8888"
          className="mt-1 w-full rounded-lg border border-border-token bg-surface-muted-token px-3 py-2 text-fg-token" />
      </label>
      {err && <p className="text-sm text-red-500">{err}</p>}
      <button onClick={save} disabled={busy || !num}
        className="w-full rounded-lg bg-brand px-4 py-2 font-medium text-white disabled:opacity-50">
        Salvar e continuar
      </button>
    </div>
  );
};
export default StepWhatsApp;
```

`StepProduct.tsx`:
```tsx
import { useState, type FC } from 'react';
import productsService from '../../../../services/products';

function slugify(s: string) {
  return s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '').slice(0, 40) || 'produto';
}

const StepProduct: FC<{ storeId: string; onSaved: () => void }> = ({ storeId, onSaved }) => {
  const [name, setName] = useState('');
  const [price, setPrice] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true); setErr(null);
    try {
      await productsService.createProduct({
        name, price: Number(price), sku: `${slugify(name)}-${Date.now().toString(36)}`,
        stock_quantity: 0, is_active: true, store: storeId,
      });
      onSaved();
    } catch { setErr('Não foi possível salvar o produto.'); } finally { setBusy(false); }
  }
  return (
    <div className="space-y-4">
      <p className="text-sm text-fg-muted-token">Cadastre um item pra sua loja começar a vender.</p>
      <label className="block text-sm"><span className="text-fg-token">Nome</span>
        <input aria-label="Nome" value={name} onChange={(e) => setName(e.target.value)}
          className="mt-1 w-full rounded-lg border border-border-token bg-surface-muted-token px-3 py-2 text-fg-token" />
      </label>
      <label className="block text-sm"><span className="text-fg-token">Preço (R$)</span>
        <input aria-label="Preço" type="number" step="0.01" value={price} onChange={(e) => setPrice(e.target.value)}
          className="mt-1 w-full rounded-lg border border-border-token bg-surface-muted-token px-3 py-2 text-fg-token" />
      </label>
      {err && <p className="text-sm text-red-500">{err}</p>}
      <button onClick={save} disabled={busy || !name || !price}
        className="w-full rounded-lg bg-brand px-4 py-2 font-medium text-white disabled:opacity-50">
        Salvar e continuar
      </button>
    </div>
  );
};
export default StepProduct;
```

`StepWhatsApp` pattern repetido pros outros (cada um com seus campos + service):

`StepLogo.tsx` (logo via `updateStoreWithFiles`):
```tsx
import { useState, type FC } from 'react';
import { updateStoreWithFiles } from '../../../../services/storesApi';

const StepLogo: FC<{ storeId: string; onSaved: () => void }> = ({ storeId, onSaved }) => {
  const [file, setFile] = useState<File | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function save() {
    if (!file) return;
    setBusy(true); setErr(null);
    try { await updateStoreWithFiles(storeId, { logo: file }); onSaved(); }
    catch { setErr('Não foi possível enviar a logo.'); } finally { setBusy(false); }
  }
  return (
    <div className="space-y-4">
      <p className="text-sm text-fg-muted-token">A marca que aparece no topo da sua loja.</p>
      <input aria-label="Logo" type="file" accept="image/*"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        className="block w-full text-sm text-fg-muted-token" />
      {file && <p className="text-sm text-fg-token">{file.name}</p>}
      {err && <p className="text-sm text-red-500">{err}</p>}
      <button onClick={save} disabled={busy || !file}
        className="w-full rounded-lg bg-brand px-4 py-2 font-medium text-white disabled:opacity-50">
        Salvar e continuar
      </button>
    </div>
  );
};
export default StepLogo;
```

`StepDelivery.tsx` (cria 1 zona simples OU "só retirada"):
```tsx
import { useState, type FC } from 'react';
import deliveryService from '../../../../services/delivery';
import { updateStore } from '../../../../services/storesApi';

const StepDelivery: FC<{ storeId: string; onSaved: () => void }> = ({ storeId, onSaved }) => {
  const [fee, setFee] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function saveZone() {
    setBusy(true); setErr(null);
    try { await deliveryService.createZone({ store: storeId, name: 'Padrão', delivery_fee: Number(fee || 0), is_active: true }); onSaved(); }
    catch { setErr('Não foi possível salvar a entrega.'); } finally { setBusy(false); }
  }
  async function pickupOnly() {
    setBusy(true); setErr(null);
    try { await updateStore(storeId, { delivery_enabled: false, pickup_enabled: true } as any); onSaved(); }
    catch { setErr('Não foi possível salvar.'); } finally { setBusy(false); }
  }
  return (
    <div className="space-y-4">
      <p className="text-sm text-fg-muted-token">Defina a taxa de entrega ou marque só retirada.</p>
      <label className="block text-sm"><span className="text-fg-token">Taxa de entrega (R$)</span>
        <input aria-label="Taxa de entrega" type="number" step="0.01" value={fee} onChange={(e) => setFee(e.target.value)}
          className="mt-1 w-full rounded-lg border border-border-token bg-surface-muted-token px-3 py-2 text-fg-token" />
      </label>
      {err && <p className="text-sm text-red-500">{err}</p>}
      <button onClick={saveZone} disabled={busy || !fee}
        className="w-full rounded-lg bg-brand px-4 py-2 font-medium text-white disabled:opacity-50">
        Salvar e continuar
      </button>
      <button onClick={pickupOnly} disabled={busy}
        className="w-full text-sm text-fg-muted-token hover:text-fg-token">
        Minha loja é só retirada
      </button>
    </div>
  );
};
export default StepDelivery;
```

`StepHours.tsx` (horário padrão simples seg–dom):
```tsx
import { useState, type FC } from 'react';
import { updateStore } from '../../../../services/storesApi';

const DIAS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];

const StepHours: FC<{ storeId: string; onSaved: () => void }> = ({ storeId, onSaved }) => {
  const [open, setOpen] = useState('09:00');
  const [close, setClose] = useState('18:00');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true); setErr(null);
    const hours = Object.fromEntries(DIAS.map((d) => [d, { open, close }]));
    try { await updateStore(storeId, { operating_hours: hours } as any); onSaved(); }
    catch { setErr('Não foi possível salvar o horário.'); } finally { setBusy(false); }
  }
  return (
    <div className="space-y-4">
      <p className="text-sm text-fg-muted-token">Um horário padrão pra todos os dias (ajuste depois nas configurações).</p>
      <div className="flex gap-3">
        <label className="flex-1 text-sm"><span className="text-fg-token">Abre</span>
          <input aria-label="Abre" type="time" value={open} onChange={(e) => setOpen(e.target.value)}
            className="mt-1 w-full rounded-lg border border-border-token bg-surface-muted-token px-3 py-2 text-fg-token" />
        </label>
        <label className="flex-1 text-sm"><span className="text-fg-token">Fecha</span>
          <input aria-label="Fecha" type="time" value={close} onChange={(e) => setClose(e.target.value)}
            className="mt-1 w-full rounded-lg border border-border-token bg-surface-muted-token px-3 py-2 text-fg-token" />
        </label>
      </div>
      {err && <p className="text-sm text-red-500">{err}</p>}
      <button onClick={save} disabled={busy}
        className="w-full rounded-lg bg-brand px-4 py-2 font-medium text-white disabled:opacity-50">
        Salvar e continuar
      </button>
    </div>
  );
};
export default StepHours;
```

> Nota de integração: confirme que `deliveryService` é o default export de `services/delivery.ts` (método `createZone`) e `productsService` o de `services/products.ts` (`createProduct`). `updateStore(id, data)` aceita `Partial<StoreInput>`; os campos `operating_hours`/`delivery_enabled`/`pickup_enabled` podem exigir `as any` se não estiverem no tipo `StoreInput` — confirme e use o tipo certo se existir.

- [ ] **Step 4: Rodar e ver passar**

Run: `npm test -- steps`
Expected: PASS (2 testes do arquivo). `npx tsc --noEmit` → 0.

- [ ] **Step 5: Commit**

```bash
git add src/components/onboarding/wizard/steps/
git commit -m "feat(onboarding): 5 mini-forms do wizard sobre os services existentes"
```

---

## Task B6: Dash — montagem, auto-open e CTA do card

**Files:**
- Modify: `src/pages/dashboard/DashboardPage.tsx`
- Modify: `src/components/onboarding/OnboardingChecklist.tsx`
- Create: `src/components/onboarding/wizard/buildWizardSteps.tsx` (monta o array de `WizardStepDef` a partir dos steps + storeId)
- Test: `src/components/onboarding/wizard/__tests__/buildWizardSteps.test.tsx`

**Interfaces:**
- Consumes: B3 (`markWizardSeen`, `wizard_seen`), B4 (`OnboardingWizard`, `WizardStepDef`), B5 (os steps).
- Produces: `buildWizardSteps(storeId)` → `WizardStepDef[]` (welcome opcional + 5 steps). DashboardPage controla `open` + chama `markWizardSeen` no auto-open. O card ganha botão "Continuar configuração" que abre o wizard.

- [ ] **Step 1: Teste falhando**

```tsx
// src/components/onboarding/wizard/__tests__/buildWizardSteps.test.tsx
import { buildWizardSteps } from '../buildWizardSteps';

describe('buildWizardSteps', () => {
  it('monta os 5 passos na ordem com as keys do checklist', () => {
    const steps = buildWizardSteps('s1');
    expect(steps.map((s) => s.key)).toEqual(['logo', 'product', 'delivery', 'hours', 'whatsapp']);
    expect(steps.every((s) => typeof s.render === 'function' && s.title)).toBe(true);
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `npm test -- buildWizardSteps`
Expected: FAIL — módulo não existe.

- [ ] **Step 3: Implementar `buildWizardSteps`**

```tsx
// src/components/onboarding/wizard/buildWizardSteps.tsx
import type { WizardStepDef } from './useOnboardingWizard';
import StepLogo from './steps/StepLogo';
import StepProduct from './steps/StepProduct';
import StepDelivery from './steps/StepDelivery';
import StepHours from './steps/StepHours';
import StepWhatsApp from './steps/StepWhatsApp';

export function buildWizardSteps(storeId: string): WizardStepDef[] {
  return [
    { key: 'logo', title: 'Adicione a logo da sua loja', render: ({ onSaved }) => <StepLogo storeId={storeId} onSaved={onSaved} /> },
    { key: 'product', title: 'Cadastre seu 1º produto', render: ({ onSaved }) => <StepProduct storeId={storeId} onSaved={onSaved} /> },
    { key: 'delivery', title: 'Configure a entrega', render: ({ onSaved }) => <StepDelivery storeId={storeId} onSaved={onSaved} /> },
    { key: 'hours', title: 'Defina o horário', render: ({ onSaved }) => <StepHours storeId={storeId} onSaved={onSaved} /> },
    { key: 'whatsapp', title: 'Informe seu WhatsApp', render: ({ onSaved }) => <StepWhatsApp storeId={storeId} onSaved={onSaved} /> },
  ];
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `npm test -- buildWizardSteps`
Expected: PASS. `npx tsc --noEmit` → 0.

- [ ] **Step 5: Ligar no card** — em `OnboardingChecklist.tsx`, adicionar um CTA que abre o wizard. Como o wizard é controlado pelo DashboardPage, o card recebe uma prop opcional `onContinue?: () => void` e renderiza, abaixo da lista, quando passada:

```tsx
// na assinatura: const OnboardingChecklist: FC<{ onContinue?: () => void }> = ({ onContinue }) => {
// ...após a <ul>:
      {onContinue && (
        <div className="border-t border-border-token px-5 py-3">
          <button onClick={onContinue}
            className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white">
            Continuar configuração →
          </button>
        </div>
      )}
```

(Ajuste o teste de `OnboardingChecklist` se necessário — sem `onContinue` o comportamento é idêntico ao atual; com ele, aparece o botão.)

- [ ] **Step 6: Montar no DashboardPage com auto-open**

Em `src/pages/dashboard/DashboardPage.tsx`, no topo do conteúdo (onde o card já é montado), gerenciar o estado:

```tsx
// imports
import { useState, useEffect } from 'react';
import OnboardingWizard from '../../components/onboarding/wizard/OnboardingWizard';
import { buildWizardSteps } from '../../components/onboarding/wizard/buildWizardSteps';
import { getChecklist, markWizardSeen } from '../../services/onboarding';
import { useStore } from '../../hooks/useStore';

// dentro do componente:
const { storeId, storeSlug } = useStore();
const [wizardOpen, setWizardOpen] = useState(false);

useEffect(() => {
  if (!storeSlug) return;
  getChecklist(storeSlug).then((c) => {
    if (!c.all_done && !c.wizard_seen) {
      setWizardOpen(true);
      markWizardSeen(storeSlug).catch(() => {});
    }
  }).catch(() => {});
}, [storeSlug]);

// no JSX, antes do <OnboardingChecklist/>:
{storeId && (
  <OnboardingWizard open={wizardOpen} steps={buildWizardSteps(storeId)} onClose={() => setWizardOpen(false)} />
)}
<OnboardingChecklist onContinue={storeId ? () => setWizardOpen(true) : undefined} />
```

> Nota: o `OnboardingChecklist` já faz seu próprio fetch do checklist; o DashboardPage faz um fetch adicional só pra decidir o auto-open (aceitável — payload pequeno). Confirme que não há duplicação problemática; se preferir, suba o fetch pro DashboardPage e passe via prop numa iteração futura (fora do escopo desta task).

- [ ] **Step 7: Verificar tudo**

Run: `npm test -- onboarding wizard steps buildWizardSteps OnboardingChecklist` (ou `npm test`) → tudo verde, zero `act()` warning.
Run: `npx tsc --noEmit` → 0. Run: `npm run build` → OK.

- [ ] **Step 8: Commit**

```bash
git add src/components/onboarding/wizard/buildWizardSteps.tsx src/components/onboarding/wizard/__tests__/buildWizardSteps.test.tsx src/components/onboarding/OnboardingChecklist.tsx src/pages/dashboard/DashboardPage.tsx
git commit -m "feat(onboarding): auto-open do wizard no 1o login + CTA de retomada no card"
```

---

## Self-Review (preenchido)

- **Cobertura do spec (Fase B):** campo `onboarding_wizard_seen` → B1 ✓; expor no checklist → B1 ✓; endpoint de escrita `seen` → B2 ✓; service `markWizardSeen` → B3 ✓; shell full-screen (Dialog+framer-motion+progresso+nav) → B4 ✓; 5 mini-forms sobre os services → B5 ✓; auto-open 1× + `markWizardSeen` no auto-open + CTA de retomada → B6 ✓; "só o card" (sem /comecar) ✓; sem localStorage ✓.
- **Placeholders:** código completo em cada step. As notas "confirme o default export / o tipo de StoreInput" são integrações em código existente (não inventar), não placeholders.
- **Consistência de tipos:** `WizardStepDef` (B4) usado em `buildWizardSteps` (B6) e no shell; cada step tem assinatura `{storeId, onSaved}` (B5) consumida em `buildWizardSteps`; `markWizardSeen`/`wizard_seen` (B3) usados em B6; contrato `wizard_seen` do backend (B1) ↔ tipo TS (B3) ↔ uso (B6).
- **Ordem/branch:** mesma branch `feat/onboarding-wizard` (server2 backend B1-B2; dash B3-B6). Ordem: B1→B2 (backend), B3→B4→B5→B6 (dash). B5 depende de B4 (tipo) só no buildWizardSteps; os steps em si são independentes.
- **Deploy:** server2 `deploy.sh` (migration additive); dash push `main` (Vercel). Após review final whole-branch.
