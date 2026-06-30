# Fase 2 — Checklist "Primeiros Passos" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um dono novo vê no topo do painel um card "Primeiros passos" que marca sozinho (derivado de dados reais) o que falta pra loja vender, e some quando tudo está feito.

**Architecture:** Backend expõe um endpoint read-only que deriva o estado de cada passo de campos já existentes do `Store` (sem model novo). Frontend consome e renderiza um card com progresso; as rotas de cada passo (action_path) são domínio do frontend (o backend só devolve `key`/`label`/`done`).

**Tech Stack:** Django 4 + DRF (server2, harness Docker `scripts/sdd-test.sh`); React + Vite + TypeScript + jest (pastita-dash).

## Global Constraints

- **TDD obrigatório** — teste falhando antes do código. Zero regressão.
- **`is_staff` NÃO dá acesso cross-tenant** — só `store.owner` / `store.staff` / `is_superuser` (helper `_can_manage`).
- **Sem model novo / sem migration** — tudo derivado de campos existentes.
- **Commits em português**, terminando com `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Backend (server2):** rodar testes `bash scripts/sdd-test.sh <path> --reuse-db -q` (sem python local; ~60s no 1º run).
- **Dash:** runner **jest** (`npm test -- <pad>`); `npx tsc --noEmit` deve sair 0; output de teste pristine (sem `act()` warning); **`vite.config.ts` NUNCA entra em commit** (fica unstaged).
- **Tokens do tema dark-luxe** no front: `bg-surface-token`/`text-fg-token`/`text-fg-muted-token`/`bg-brand`/`border-border-token` (ver `SubscriptionManagementPage.tsx`/`TrialBanner.tsx`).
- **Contrato do checklist (fonte única):** backend → `{ steps: [{key, label, done}], completed, total, all_done }`. `key ∈ {account, logo, product, delivery, hours, whatsapp}`. `total = 6`.

---

## File Structure

**server2 (backend):**
- `apps/stores/services/onboarding_checklist.py` — CREATE: função pura `build_checklist(store)`.
- `apps/stores/tests/test_onboarding_checklist.py` — CREATE: testes da função pura.
- `apps/stores/api/views/onboarding_views.py` — CREATE: `StoreOnboardingChecklistView`.
- `apps/stores/urls.py` — MODIFY: rota `onboarding/checklist/` no nível `<slug:store_slug>/`.
- `apps/stores/tests/test_onboarding_checklist_api.py` — CREATE: teste do endpoint (200 owner / 403 não-owner).

**pastita-dash (frontend):**
- `src/services/onboarding.ts` — MODIFY: `getChecklist(storeSlug)` + tipos.
- `src/services/__tests__/onboarding.test.ts` — CREATE (ou estende): teste do service.
- `src/components/onboarding/OnboardingChecklist.tsx` — CREATE: o card.
- `src/components/onboarding/__tests__/OnboardingChecklist.test.tsx` — CREATE.
- `src/pages/dashboard/DashboardPage.tsx` — MODIFY: montar `<OnboardingChecklist />` no topo.

---

## Task 1: Função pura `build_checklist`

**Files:**
- Create: `apps/stores/services/onboarding_checklist.py`
- Test: `apps/stores/tests/test_onboarding_checklist.py`

**Interfaces:**
- Produces: `build_checklist(store) -> dict` no formato `{ "steps": [{"key": str, "label": str, "done": bool}], "completed": int, "total": int, "all_done": bool }`. Ordem fixa das keys: `account, logo, product, delivery, hours, whatsapp`.

- [ ] **Step 1: Escrever o teste falhando**

```python
# apps/stores/tests/test_onboarding_checklist.py
from django.contrib.auth import get_user_model
from django.test import TestCase
from apps.stores.models import Store
from apps.stores.models.delivery import StoreDeliveryZone
from apps.stores.services.onboarding_checklist import build_checklist

User = get_user_model()


def _store(**kw):
    owner = User.objects.create_user(
        username=f"o-{kw.get('slug','x')}", email=f"{kw.get('slug','x')}@t.local", password='x')
    return Store.objects.create(name=kw.get('slug', 'L'), slug=kw.get('slug', 'l'), owner=owner)


class BuildChecklistTest(TestCase):
    def test_loja_vazia_so_account(self):
        c = build_checklist(_store(slug='vazia'))
        self.assertEqual(c['total'], 6)
        self.assertEqual(c['completed'], 1)  # só 'account'
        self.assertFalse(c['all_done'])
        done = {s['key']: s['done'] for s in c['steps']}
        self.assertTrue(done['account'])
        self.assertFalse(done['logo'])
        self.assertFalse(done['product'])
        self.assertFalse(done['delivery'])
        self.assertFalse(done['hours'])
        self.assertFalse(done['whatsapp'])

    def test_ordem_e_labels_presentes(self):
        c = build_checklist(_store(slug='ord'))
        self.assertEqual([s['key'] for s in c['steps']],
                         ['account', 'logo', 'product', 'delivery', 'hours', 'whatsapp'])
        self.assertTrue(all(s['label'] for s in c['steps']))

    def test_logo_url_externa_conta(self):
        s = _store(slug='logo')
        s.logo_url = 'https://x/y.png'; s.save(update_fields=['logo_url'])
        done = {x['key']: x['done'] for x in build_checklist(s)['steps']}
        self.assertTrue(done['logo'])

    def test_horario_e_whatsapp(self):
        s = _store(slug='hw')
        s.operating_hours = {'monday': {'open': '09:00', 'close': '18:00'}}
        s.whatsapp_number = '5563999999999'
        s.save(update_fields=['operating_hours', 'whatsapp_number'])
        done = {x['key']: x['done'] for x in build_checklist(s)['steps']}
        self.assertTrue(done['hours'])
        self.assertTrue(done['whatsapp'])

    def test_zona_de_entrega_conta_como_delivery(self):
        s = _store(slug='deliv')
        StoreDeliveryZone.objects.create(store=s, name='Centro', fee=5)
        done = {x['key']: x['done'] for x in build_checklist(s)['steps']}
        self.assertTrue(done['delivery'])

    def test_all_done(self):
        s = _store(slug='full')
        s.logo_url = 'https://x/y.png'
        s.operating_hours = {'monday': {'open': '09:00', 'close': '18:00'}}
        s.whatsapp_number = '556399'
        s.save()
        from apps.stores.models.product import StoreProduct  # noqa
        # cria 1 produto mínimo; se faltar campo obrigatório, leia o model e adicione o mínimo
        StoreProduct.objects.create(store=s, name='X', price=10)
        StoreDeliveryZone.objects.create(store=s, name='Centro', fee=5)
        c = build_checklist(s)
        self.assertTrue(c['all_done'])
        self.assertEqual(c['completed'], 6)
```

> Nota de integração (NÃO inventar): antes de rodar, confirme os campos obrigatórios reais de `StoreDeliveryZone` (`apps/stores/models/delivery.py`) e de `StoreProduct` (`apps/stores/models/product.py`). Se `fee`/`price`/`name` tiverem outro nome ou exigirem mais campos, ajuste a criação no teste para o mínimo válido. O related_name de produtos é `products`; o de zonas é `delivery_zones`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `bash scripts/sdd-test.sh apps/stores/tests/test_onboarding_checklist.py --reuse-db -q`
Expected: FAIL — `ModuleNotFoundError: ...onboarding_checklist`.

- [ ] **Step 3: Implementar a função pura**

```python
# apps/stores/services/onboarding_checklist.py
"""
Checklist de onboarding ("Primeiros passos") — estado 100% DERIVADO de dados
reais do Store. Sem model novo, sem flag manual. Cada passo é uma função de
derivação isolada. O frontend mapeia key -> rota/label de ação; aqui devolvemos
key/label/done (label é a cópia curta do passo).
"""

# (key, label, função de derivação)
_STEPS = [
    ('account', 'Conta criada', lambda s: True),
    ('logo', 'Adicionar logo da loja', lambda s: bool(s.logo or s.logo_url)),
    ('product', 'Cadastrar 1º produto', lambda s: s.products.exists()),
    ('delivery', 'Configurar entrega', lambda s: s.delivery_zones.exists()),
    ('hours', 'Definir horário de funcionamento', lambda s: bool(s.operating_hours)),
    ('whatsapp', 'Informar WhatsApp', lambda s: bool(s.whatsapp_number)),
]


def build_checklist(store):
    steps = [{'key': k, 'label': lbl, 'done': bool(fn(store))} for k, lbl, fn in _STEPS]
    completed = sum(1 for s in steps if s['done'])
    total = len(steps)
    return {
        'steps': steps,
        'completed': completed,
        'total': total,
        'all_done': completed == total,
    }
```

- [ ] **Step 4: Rodar e ver passar**

Run: `bash scripts/sdd-test.sh apps/stores/tests/test_onboarding_checklist.py --reuse-db -q`
Expected: PASS (6 testes).

- [ ] **Step 5: Commit**

```bash
git add apps/stores/services/onboarding_checklist.py apps/stores/tests/test_onboarding_checklist.py
git commit -m "feat(onboarding): funcao pura build_checklist (estado derivado dos dados da loja)"
```

---

## Task 2: Endpoint `GET .../onboarding/checklist/`

**Files:**
- Create: `apps/stores/api/views/onboarding_views.py`
- Modify: `apps/stores/urls.py` (rota no nível `<slug:store_slug>/`, ao lado de `subscription/`)
- Test: `apps/stores/tests/test_onboarding_checklist_api.py`

**Interfaces:**
- Consumes: `build_checklist(store)` (Task 1); `_can_manage(store, user)` de `apps/stores/api/views/subscription_views.py`.
- Produces: `GET /api/v1/stores/<slug>/onboarding/checklist/` → 200 com o dict do checklist (owner/staff/superuser); 403 para usuário sem permissão; 404 se loja não existe.

- [ ] **Step 1: Escrever o teste falhando**

```python
# apps/stores/tests/test_onboarding_checklist_api.py
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from apps.stores.models import Store

User = get_user_model()


class OnboardingChecklistAPITest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono', email='dono@t.local', password='x')
        self.store = Store.objects.create(name='Loja', slug='loja', owner=self.owner)
        self.client = APIClient()

    def test_owner_recebe_checklist(self):
        self.client.force_authenticate(self.owner)
        r = self.client.get('/api/v1/stores/loja/onboarding/checklist/')
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body['total'], 6)
        self.assertEqual(len(body['steps']), 6)
        self.assertIn('all_done', body)

    def test_nao_owner_recebe_403(self):
        outro = User.objects.create_user(username='outro', email='outro@t.local', password='x')
        self.client.force_authenticate(outro)
        r = self.client.get('/api/v1/stores/loja/onboarding/checklist/')
        self.assertEqual(r.status_code, 403)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `bash scripts/sdd-test.sh apps/stores/tests/test_onboarding_checklist_api.py --reuse-db -q`
Expected: FAIL — 404 (rota não existe).

- [ ] **Step 3: Implementar a view**

```python
# apps/stores/api/views/onboarding_views.py
"""Endpoint read-only do checklist de onboarding ("Primeiros passos")."""
from django.shortcuts import get_object_or_404
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.stores.models import Store
from apps.stores.api.views.subscription_views import _can_manage
from apps.stores.services.onboarding_checklist import build_checklist


class StoreOnboardingChecklistView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, store_slug):
        store = get_object_or_404(Store, slug=store_slug)
        if not _can_manage(store, request.user):
            return Response({'detail': 'Sem permissão.'}, status=403)
        return Response(build_checklist(store))
```

- [ ] **Step 4: Registrar a rota**

Em `apps/stores/urls.py`, ao lado da rota `subscription/` (mesmo nível `<slug:store_slug>/`), adicione o import e a rota:

```python
from .api.views.onboarding_views import StoreOnboardingChecklistView
# ...
    path('onboarding/checklist/', StoreOnboardingChecklistView.as_view(), name='store-onboarding-checklist'),
```

> Confirme o prefixo lendo o `urlpatterns` em volta da rota `subscription/` — a nova rota deve ficar no MESMO nível (mesmo `<slug:store_slug>/`).

- [ ] **Step 5: Rodar e ver passar**

Run: `bash scripts/sdd-test.sh apps/stores/tests/test_onboarding_checklist_api.py --reuse-db -q`
Expected: PASS (2 testes).

- [ ] **Step 6: Commit**

```bash
git add apps/stores/api/views/onboarding_views.py apps/stores/urls.py apps/stores/tests/test_onboarding_checklist_api.py
git commit -m "feat(onboarding): endpoint GET onboarding/checklist gated por _can_manage"
```

---

## Task 3: Service do dash `getChecklist`

**Files:**
- Modify: `src/services/onboarding.ts`
- Test: `src/services/__tests__/onboarding.test.ts`

**Interfaces:**
- Consumes: endpoint da Task 2.
- Produces: `getChecklist(storeSlug: string): Promise<OnboardingChecklist>`; tipos `ChecklistStepDTO = { key: ChecklistKey; label: string; done: boolean }`, `OnboardingChecklist = { steps: ChecklistStepDTO[]; completed: number; total: number; all_done: boolean }`, `ChecklistKey = 'account'|'logo'|'product'|'delivery'|'hours'|'whatsapp'`.

- [ ] **Step 1: Escrever o teste falhando**

```ts
// src/services/__tests__/onboarding.test.ts
import api from '../api';
import { getChecklist } from '../onboarding';

jest.mock('../api');

describe('getChecklist', () => {
  it('chama o endpoint certo e retorna o checklist', async () => {
    (api.get as jest.Mock).mockResolvedValue({
      data: { steps: [{ key: 'account', label: 'Conta criada', done: true }],
              completed: 1, total: 6, all_done: false },
    });
    const res = await getChecklist('loja');
    expect(api.get).toHaveBeenCalledWith('/stores/loja/onboarding/checklist/');
    expect(res.total).toBe(6);
    expect(res.steps[0].key).toBe('account');
  });
});
```

> Confirme o padrão de mock olhando `src/services/__tests__/billing.test.ts` (mesmo runner jest, mesmo `jest.mock('../api')`). Ajuste se o projeto usar outro estilo.

- [ ] **Step 2: Rodar e ver falhar**

Run (em `pastita-dash`): `npm test -- onboarding`
Expected: FAIL — `getChecklist is not exported`.

- [ ] **Step 3: Implementar no `onboarding.ts`**

Adicionar ao fim de `src/services/onboarding.ts`:

```ts
export type ChecklistKey =
  | 'account' | 'logo' | 'product' | 'delivery' | 'hours' | 'whatsapp';

export interface ChecklistStepDTO {
  key: ChecklistKey;
  label: string;
  done: boolean;
}

export interface OnboardingChecklist {
  steps: ChecklistStepDTO[];
  completed: number;
  total: number;
  all_done: boolean;
}

export async function getChecklist(storeSlug: string): Promise<OnboardingChecklist> {
  const { data } = await api.get(`/stores/${storeSlug}/onboarding/checklist/`);
  return data;
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `npm test -- onboarding`
Expected: PASS (1 teste). Depois: `npx tsc --noEmit` → sai 0.

- [ ] **Step 5: Commit**

```bash
git add src/services/onboarding.ts src/services/__tests__/onboarding.test.ts
git commit -m "feat(dash): service getChecklist do onboarding"
```

---

## Task 4: Componente `OnboardingChecklist` + montagem no dashboard

**Files:**
- Create: `src/components/onboarding/OnboardingChecklist.tsx`
- Create: `src/components/onboarding/__tests__/OnboardingChecklist.test.tsx`
- Modify: `src/pages/dashboard/DashboardPage.tsx` (montar no topo)

**Interfaces:**
- Consumes: `getChecklist`, tipos `OnboardingChecklist`/`ChecklistKey` (Task 3); `useStore()` p/ o slug.
- Produces: `<OnboardingChecklist />` (sem props) — renderiza o card; some quando `all_done` ou quando dispensado.

O componente é dono do mapa `key -> { route, fallbackLabel }` (rotas são domínio do front). Use a `label` vinda do backend como texto; a rota vem deste mapa.

- [ ] **Step 1: Ler as rotas reais**

Leia `src/App.tsx` e anote as rotas reais para: produtos, configuração de entrega, horário, logo/marca, whatsapp/contato. O home é a rota `index` (`DashboardPage`). Monte o mapa `ROUTE_BY_KEY` com as rotas que existirem; para um passo cujo destino não exista como rota dedicada, aponte para `/settings` (rota confirmada). NÃO invente rota inexistente.

- [ ] **Step 2: Escrever o teste falhando**

```tsx
// src/components/onboarding/__tests__/OnboardingChecklist.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { act } from 'react';
import OnboardingChecklist from '../OnboardingChecklist';
import * as onboarding from '../../../services/onboarding';

jest.mock('../../../services/onboarding');
jest.mock('../../../hooks/useStore', () => ({ useStore: () => ({ store: { slug: 'loja' } }) }));

const mockGet = onboarding.getChecklist as jest.Mock;

function renderCard() {
  return render(<MemoryRouter><OnboardingChecklist /></MemoryRouter>);
}

describe('OnboardingChecklist', () => {
  beforeEach(() => { localStorage.clear(); });

  it('mostra progresso e um passo pendente com link', async () => {
    mockGet.mockResolvedValue({
      steps: [
        { key: 'account', label: 'Conta criada', done: true },
        { key: 'product', label: 'Cadastrar 1º produto', done: false },
      ],
      completed: 1, total: 6, all_done: false,
    });
    await act(async () => { renderCard(); });
    expect(await screen.findByText(/cadastrar 1º produto/i)).toBeTruthy();
    expect(screen.getByText(/1\/6|1 de 6/i)).toBeTruthy();
  });

  it('não renderiza quando all_done', async () => {
    mockGet.mockResolvedValue({ steps: [], completed: 6, total: 6, all_done: true });
    let c: { container: HTMLElement };
    await act(async () => { c = renderCard(); });
    expect(c!.container.textContent).not.toMatch(/primeiros passos/i);
  });

  it('não renderiza quando dispensado no localStorage', async () => {
    localStorage.setItem('onboarding_dismissed_loja', '1');
    mockGet.mockResolvedValue({ steps: [{ key: 'logo', label: 'Adicionar logo', done: false }],
                                completed: 1, total: 6, all_done: false });
    let c: { container: HTMLElement };
    await act(async () => { c = renderCard(); });
    expect(c!.container.textContent).not.toMatch(/primeiros passos/i);
  });
});
```

> Confirme o caminho real do hook `useStore` (o `jest.mock` acima usa `../../../hooks/useStore`) lendo como `SubscriptionManagementPage.tsx` importa `useStore`. Ajuste o path do mock se diferente. Garanta ZERO `act()` warning na saída (padrão do `TrialBanner.test.tsx`).

- [ ] **Step 3: Rodar e ver falhar**

Run: `npm test -- OnboardingChecklist`
Expected: FAIL — módulo não existe.

- [ ] **Step 4: Implementar o componente**

```tsx
// src/components/onboarding/OnboardingChecklist.tsx
import { useEffect, useState, type FC } from 'react';
import { Link } from 'react-router-dom';
import { useStore } from '../../hooks/useStore'; // confirme o path real (ver SubscriptionManagementPage)
import { getChecklist, type OnboardingChecklist as Checklist, type ChecklistKey } from '../../services/onboarding';

// Rotas são domínio do front. Ajuste os destinos às rotas reais do App.tsx (Step 1).
const ROUTE_BY_KEY: Record<ChecklistKey, string> = {
  account: '/',
  logo: '/settings',
  product: '/settings',     // troque pela rota real de produtos se existir
  delivery: '/settings',
  hours: '/settings',
  whatsapp: '/settings',
};

const OnboardingChecklist: FC = () => {
  const { store } = useStore();
  const slug = store?.slug;
  const [data, setData] = useState<Checklist | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (!slug) return;
    setDismissed(localStorage.getItem(`onboarding_dismissed_${slug}`) === '1');
    getChecklist(slug).then(setData).catch(() => { /* silencioso: não quebra o home */ });
  }, [slug]);

  if (!data || data.all_done || dismissed) return null;

  function dismiss() {
    if (slug) localStorage.setItem(`onboarding_dismissed_${slug}`, '1');
    setDismissed(true);
  }

  return (
    <section
      role="region"
      aria-label="Primeiros passos"
      className="mb-6 rounded-lg border border-border-token bg-surface-token p-4"
    >
      <header className="flex items-center justify-between">
        <h2 className="font-semibold text-fg-token">Primeiros passos</h2>
        <span className="text-sm text-fg-muted-token">{data.completed}/{data.total}</span>
      </header>
      <ul className="mt-3 space-y-2">
        {data.steps.map((s) => (
          <li key={s.key} className="flex items-center gap-2 text-sm">
            <span aria-hidden>{s.done ? '✅' : '⬜'}</span>
            {s.done ? (
              <span className="text-fg-muted-token line-through">{s.label}</span>
            ) : (
              <Link to={ROUTE_BY_KEY[s.key]} className="text-fg-token hover:text-brand">
                {s.label} →
              </Link>
            )}
          </li>
        ))}
      </ul>
      <button onClick={dismiss} className="mt-3 text-xs text-fg-muted-token underline">
        Dispensar
      </button>
    </section>
  );
};

export default OnboardingChecklist;
```

> Ajuste: o import de `useStore` e os nomes das classes de token ao que o codebase realmente usa (ver `SubscriptionManagementPage.tsx`/`TrialBanner.tsx`). Não inventar token novo.

- [ ] **Step 5: Rodar e ver passar**

Run: `npm test -- OnboardingChecklist`
Expected: PASS (3 testes), ZERO `act()` warning.

- [ ] **Step 6: Montar no dashboard**

Em `src/pages/dashboard/DashboardPage.tsx`, importar e renderizar `<OnboardingChecklist />` no TOPO do conteúdo da página (antes dos cards/estatísticas existentes). Não alterar o resto do dashboard.

- [ ] **Step 7: Verificar build**

Run: `npx tsc --noEmit` → sai 0. Opcional: `npm run build`.

- [ ] **Step 8: Commit**

```bash
git add src/components/onboarding/OnboardingChecklist.tsx src/components/onboarding/__tests__/OnboardingChecklist.test.tsx src/pages/dashboard/DashboardPage.tsx
git commit -m "feat(dash): card Primeiros Passos no dashboard (some em 100%/dispensar)"
```

---

## Notas de execução

- **Branches:** server2 já em `feat/fase2-onboarding-checklist` (spec commitado). Dash: criar `feat/fase2-onboarding-checklist` a partir de `main` antes da Task 3.
- **Ordem:** Task 1 → 2 (backend), Task 3 → 4 (dash). 3/4 dependem só do CONTRATO (Task 1/2), podem ser feitas em paralelo ao backend se necessário, mas o contrato `{steps:[{key,label,done}],completed,total,all_done}` é fixo.
- **Deploy:** server2 via `deploy.sh` (endpoint read-only, sem migration); dash via push na `main` (Vercel). Recomendado deployar depois do review final whole-branch.

## Self-Review (preenchido)

- **Cobertura do spec:** derivação dos 6 passos → Task 1 ✓; endpoint+permissão → Task 2 ✓; service → Task 3 ✓; componente+montagem+dismissal localStorage → Task 4 ✓. Refinamento vs spec: `action_path` saiu do backend e virou domínio do front (mapa `ROUTE_BY_KEY`) — backend devolve só `key/label/done` (separação mais limpa; comportamento idêntico).
- **Placeholders:** as notas "confirme o path/rota real" são instruções de integração em código existente (não inventar rota/import), não placeholders de implementação. Código completo em cada passo.
- **Consistência de tipos:** `build_checklist` retorna `{steps:[{key,label,done}],completed,total,all_done}` (Task 1) consumido igual no endpoint (Task 2), no tipo TS `OnboardingChecklist` (Task 3) e no componente (Task 4). `ChecklistKey` idêntico entre service e `ROUTE_BY_KEY`.
