# Onboarding Fase A — Guide Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar o card "Primeiros passos" (hoje uma lista de emoji feia) num card premium dark-luxe: anel de progresso + ícones lucide por passo + linhas polidas, removendo o dismiss-por-localStorage.

**Architecture:** Só frontend (pastita-dash). Reusa o `getChecklist` e o contrato existentes (Fase 2). Adiciona um componente presentational `ProgressRing` e redesenha `OnboardingChecklist`. Sem backend, sem dependência nova (lucide-react + tokens já existem). O wizard (Fase B) liga depois no CTA; nesta fase os passos pendentes continuam linkando pras rotas reais.

**Tech Stack:** React + Vite + TypeScript + jest; `lucide-react` (ícones); tokens dark-luxe (CSS vars); SVG puro pro anel.

## Global Constraints

- **TDD**; runner **jest** (`npm test -- <pad>`); `npx tsc --noEmit` sai 0; output pristine (zero `act()` warning).
- **Sem dependência nova** — usar `lucide-react` (já instalado) e os tokens dark-luxe (`bg-surface-token`/`text-fg-token`/`text-fg-muted-token`/`bg-brand`/`border-border-token`/`brand`). NÃO inventar token.
- **Sem framer-motion nesta fase** — micro-animação só via CSS transition (evita flakiness de act() no jest). framer-motion fica pra Fase B (wizard).
- **`vite.config.ts` NUNCA entra em commit** — `git add` só os arquivos da task.
- **Remover localStorage** do card (decisão do spec): o card aparece enquanto `!all_done` e some sozinho em `all_done`; sem botão "dispensar".
- Mantém `buildRouteByKey(storeId)` (rotas reais) — passos pendentes continuam sendo `Link` pra rota do passo.
- Commits em português + `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Contrato consumido (inalterado): `getChecklist(slug) -> { steps:[{key,label,done}], completed, total, all_done }`, `ChecklistKey ∈ {account,logo,product,delivery,hours,whatsapp}`.

---

## File Structure

- `src/components/onboarding/ProgressRing.tsx` — CREATE: anel SVG de progresso, presentational puro.
- `src/components/onboarding/__tests__/ProgressRing.test.tsx` — CREATE.
- `src/components/onboarding/OnboardingChecklist.tsx` — MODIFY: redesenha usando ProgressRing + ícones lucide; remove localStorage/dismiss.
- `src/components/onboarding/__tests__/OnboardingChecklist.test.tsx` — MODIFY: remove o teste de dismiss-localStorage; ajusta asserts ao novo markup.

---

## Task 1: Componente `ProgressRing`

**Files:**
- Create: `src/components/onboarding/ProgressRing.tsx`
- Test: `src/components/onboarding/__tests__/ProgressRing.test.tsx`

**Interfaces:**
- Produces: `ProgressRing` (default export), props `{ completed: number; total: number; size?: number }`. Renderiza um SVG com trilho + arco de progresso (via `stroke-dasharray`/`stroke-dashoffset`), com o texto `N/total` no centro. `size` default 56. Acessível: `role="img"` + `aria-label="N de TOTAL passos concluídos"`.

- [ ] **Step 1: Escrever o teste falhando**

```tsx
// src/components/onboarding/__tests__/ProgressRing.test.tsx
import { render, screen } from '@testing-library/react';
import ProgressRing from '../ProgressRing';

describe('ProgressRing', () => {
  it('mostra N/total no centro e tem aria-label', () => {
    render(<ProgressRing completed={2} total={6} />);
    expect(screen.getByText('2/6')).toBeTruthy();
    expect(screen.getByRole('img', { name: /2 de 6 passos conclu/i })).toBeTruthy();
  });

  it('arco zera quando completed=0 e completa quando completed=total', () => {
    const { rerender, container } = render(<ProgressRing completed={0} total={6} />);
    const arc = () => container.querySelectorAll('circle')[1] as SVGCircleElement;
    const off0 = arc().getAttribute('stroke-dashoffset');
    rerender(<ProgressRing completed={6} total={6} />);
    const offFull = arc().getAttribute('stroke-dashoffset');
    expect(off0).not.toEqual(offFull);
    expect(Number(offFull)).toBeCloseTo(0, 1); // 100% => offset 0
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run (em `pastita-dash`): `npm test -- ProgressRing`
Expected: FAIL — módulo não existe.

- [ ] **Step 3: Implementar**

```tsx
// src/components/onboarding/ProgressRing.tsx
import { type FC } from 'react';

interface ProgressRingProps {
  completed: number;
  total: number;
  size?: number;
}

const ProgressRing: FC<ProgressRingProps> = ({ completed, total, size = 56 }) => {
  const stroke = 5;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = total > 0 ? Math.min(1, Math.max(0, completed / total)) : 0;
  const offset = circumference * (1 - pct);
  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label={`${completed} de ${total} passos concluídos`}
      className="shrink-0"
    >
      <circle
        cx={size / 2} cy={size / 2} r={radius}
        fill="none" stroke="var(--border)" strokeWidth={stroke}
      />
      <circle
        cx={size / 2} cy={size / 2} r={radius}
        fill="none" stroke="var(--brand)" strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: 'stroke-dashoffset 600ms ease' }}
      />
      <text
        x="50%" y="50%" dominantBaseline="central" textAnchor="middle"
        className="fill-fg-token text-xs font-semibold"
      >
        {completed}/{total}
      </text>
    </svg>
  );
};

export default ProgressRing;
```

- [ ] **Step 4: Rodar e ver passar**

Run: `npm test -- ProgressRing`
Expected: PASS (2 testes). Depois `npx tsc --noEmit` → sai 0.

- [ ] **Step 5: Commit**

```bash
git add src/components/onboarding/ProgressRing.tsx src/components/onboarding/__tests__/ProgressRing.test.tsx
git commit -m "feat(onboarding): componente ProgressRing (anel SVG de progresso)"
```

---

## Task 2: Redesenhar `OnboardingChecklist`

**Files:**
- Modify: `src/components/onboarding/OnboardingChecklist.tsx`
- Modify: `src/components/onboarding/__tests__/OnboardingChecklist.test.tsx`

**Interfaces:**
- Consumes: `ProgressRing` (Task 1); `getChecklist`/tipos (Fase 2); `useStore()` (`{store, storeId}`).
- Produces: `OnboardingChecklist` (default export, sem props) — card premium. Some quando `!data || all_done`. SEM localStorage/dismiss.

- [ ] **Step 1: Ajustar o teste (remover dismiss, validar novo markup)**

Substituir o conteúdo de `src/components/onboarding/__tests__/OnboardingChecklist.test.tsx` por:

```tsx
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { act } from 'react';
import OnboardingChecklist from '../OnboardingChecklist';
import * as onboarding from '../../../services/onboarding';

jest.mock('../../../services/onboarding', () => ({ getChecklist: jest.fn() }));
jest.mock('../../../hooks/useStore', () => ({ useStore: () => ({ store: { slug: 'loja' }, storeId: 'loja' }) }));

const mockGet = onboarding.getChecklist as jest.Mock;

function renderCard() {
  return render(<MemoryRouter><OnboardingChecklist /></MemoryRouter>);
}

describe('OnboardingChecklist (redesign)', () => {
  it('mostra o anel de progresso e um passo pendente com link', async () => {
    mockGet.mockResolvedValue({
      steps: [
        { key: 'account', label: 'Conta criada', done: true },
        { key: 'product', label: 'Cadastrar 1º produto', done: false },
      ],
      completed: 1, total: 6, all_done: false,
    });
    await act(async () => { renderCard(); });
    expect(await screen.findByText('1/6')).toBeTruthy();
    const link = screen.getByRole('link', { name: /cadastrar 1º produto/i });
    expect(link.getAttribute('href')).toBe('/stores/loja/products');
  });

  it('não renderiza quando all_done', async () => {
    mockGet.mockResolvedValue({ steps: [], completed: 6, total: 6, all_done: true });
    let c: { container: HTMLElement };
    await act(async () => { c = renderCard(); });
    expect(c!.container.textContent).not.toMatch(/primeiros passos/i);
  });

  it('não renderiza quando o fetch falha', async () => {
    mockGet.mockRejectedValue(new Error('net'));
    let c: { container: HTMLElement };
    await act(async () => { c = renderCard(); });
    expect(c!.container.textContent).not.toMatch(/primeiros passos/i);
  });
});
```

> Nota: este teste agora asserta o `href` real do Link do passo pendente (fecha a lacuna de cobertura da Fase 2). O mock de `useStore` retorna `storeId: 'loja'`, então `product` resolve para `/stores/loja/products`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `npm test -- OnboardingChecklist`
Expected: FAIL — o markup atual não tem o anel (`1/6` aparece, mas o href-assert e a ausência de "Dispensar" podem divergir); confirme que falha antes de implementar.

- [ ] **Step 3: Implementar o redesign**

Substituir o conteúdo de `src/components/onboarding/OnboardingChecklist.tsx` por:

```tsx
/**
 * OnboardingChecklist — card premium "Primeiros passos" no topo do dashboard.
 * Progresso 100% derivado (getChecklist, Fase 2). Some quando all_done.
 * Sem localStorage: o card é o ponto de retomada até a loja ficar pronta.
 * Rotas são domínio do front (buildRouteByKey, derivado de App.tsx).
 */
import { useEffect, useState, type FC, type ComponentType } from 'react';
import { Link } from 'react-router-dom';
import {
  CheckCircle2, Image, ShoppingBag, Truck, Clock, MessageCircle, Store, ArrowRight,
} from 'lucide-react';
import { useStore } from '../../hooks/useStore';
import { getChecklist, type OnboardingChecklist as Checklist, type ChecklistKey } from '../../services/onboarding';
import ProgressRing from './ProgressRing';

const ICON_BY_KEY: Record<ChecklistKey, ComponentType<{ className?: string }>> = {
  account: Store,
  logo: Image,
  product: ShoppingBag,
  delivery: Truck,
  hours: Clock,
  whatsapp: MessageCircle,
};

function buildRouteByKey(storeId: string | null | undefined): Record<ChecklistKey, string> {
  return {
    account: '/',
    product: storeId ? `/stores/${storeId}/products` : '/settings',
    delivery: storeId ? `/stores/${storeId}/delivery` : '/settings',
    hours: storeId ? `/stores/${storeId}/settings` : '/settings',
    logo: storeId ? `/stores/${storeId}/storefront` : '/settings',
    whatsapp: '/connections',
  };
}

const OnboardingChecklist: FC = () => {
  const { store, storeId } = useStore();
  const slug = store?.slug;
  const [data, setData] = useState<Checklist | null>(null);

  useEffect(() => {
    if (!slug) return;
    getChecklist(slug).then(setData).catch(() => { /* silencioso: não quebra o home */ });
  }, [slug]);

  if (!data || data.all_done) return null;

  const routeByKey = buildRouteByKey(storeId);

  return (
    <section
      role="region"
      aria-label="Primeiros passos"
      className="mb-6 overflow-hidden rounded-xl border border-border-token bg-surface-token shadow-sm"
    >
      <header className="flex items-center gap-4 border-b border-border-token px-5 py-4">
        <ProgressRing completed={data.completed} total={data.total} />
        <div>
          <h2 className="text-base font-semibold text-fg-token">Primeiros passos</h2>
          <p className="text-sm text-fg-muted-token">
            Falta pouco pra sua loja vender — complete os passos abaixo.
          </p>
        </div>
      </header>
      <ul className="divide-y divide-border-token">
        {data.steps.map((step) => {
          const Icon = step.done ? CheckCircle2 : ICON_BY_KEY[step.key];
          const rowBase = 'flex items-center gap-3 px-5 py-3 text-sm';
          if (step.done) {
            return (
              <li key={step.key} className={rowBase}>
                <CheckCircle2 className="h-5 w-5 text-brand" />
                <span className="text-fg-muted-token line-through">{step.label}</span>
              </li>
            );
          }
          return (
            <li key={step.key}>
              <Link
                to={routeByKey[step.key]}
                className={`${rowBase} group transition-colors hover:bg-surface-muted-token`}
              >
                <Icon className="h-5 w-5 text-fg-muted-token group-hover:text-brand" />
                <span className="flex-1 text-fg-token">{step.label}</span>
                <ArrowRight className="h-4 w-4 text-fg-muted-token group-hover:text-brand" />
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
};

export default OnboardingChecklist;
```

> Notas: removido `dismiss`/localStorage e o emoji. `surface-muted-token` é token confirmado (`var(--surface-2)`); se o lint reclamar de import não-usado (`Icon`/`ComponentType`), ajuste — todos os imports acima são usados. Mantém `buildRouteByKey` idêntico à Fase 2 (rotas reais já verificadas).

- [ ] **Step 4: Rodar e ver passar**

Run: `npm test -- OnboardingChecklist`
Expected: PASS (3 testes), ZERO `act()` warning. Depois `npx tsc --noEmit` → 0.

- [ ] **Step 5: Build de sanidade**

Run: `npm run build`
Expected: OK (Vercel-safe).

- [ ] **Step 6: Commit**

```bash
git add src/components/onboarding/OnboardingChecklist.tsx src/components/onboarding/__tests__/OnboardingChecklist.test.tsx
git commit -m "feat(onboarding): redesign premium do card Primeiros Passos (anel + icones, sem localStorage)"
```

---

## Self-Review (preenchido)

- **Cobertura do spec (parte Fase A):** redesign do card (anel + ícones lucide + linhas polidas) → Task 1 + 2 ✓; remover localStorage → Task 2 ✓; CTA "Continuar configuração" do wizard → **fora da Fase A** (depende do wizard; chega na Fase B — nesta fase os passos linkam pras rotas, comportamento já existente). Sem dependência nova ✓ (lucide já instalado).
- **Placeholders:** nenhum; código completo nos 2 componentes e nos testes. A nota "se o lint reclamar" é higiene, não placeholder.
- **Consistência de tipos:** `ProgressRing` props `{completed,total,size?}` (Task 1) consumidas igual na Task 2 (`completed={data.completed} total={data.total}`). `ChecklistKey` usado em `ICON_BY_KEY` e `buildRouteByKey` idêntico ao service (Fase 2). Contrato do `getChecklist` inalterado.
- **Nota de execução:** branch dash nova `feat/onboarding-wizard` a partir de `main` (a Fase B continua na mesma branch). server2 não muda nesta fase.
