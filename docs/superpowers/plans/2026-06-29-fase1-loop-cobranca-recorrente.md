# Fase 1 — Loop de Cobrança Recorrente (Plano de Implementação)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Uma loja NOVA consegue, sozinha, sair do trial e virar assinante recorrente pago em produção — e quem não paga é barrado automaticamente, sem tocar nas 3 lojas isentas.

**Architecture:** O motor MercadoPago (preapproval recorrente + webhook HMAC) já existe e funciona. Esta fase **finaliza e conecta**: (1) uma Celery task diária que aplica expiração de trial → carência → suspensão e escalonamento de dunning; (2) enforcement real do status `suspended` no storefront; (3) cobrança da taxa de adesão (toggle por plano); (4) endpoints + UI de gestão de assinatura e paywall; (5) ligar autocharge em produção com smoke test. Nada é reescrito.

**Tech Stack:** Django 4 + DRF + Celery (beat) + Redis + PostgreSQL (backend `server2`); React + Vite + TypeScript (painel `pastita-dash`); MercadoPago SDK (preapproval + preference).

## Global Constraints

- **TDD obrigatório** — teste falhando antes do código. Zero regressão.
- **`billing_exempt=True` curto-circuita TUDO** — toda checagem de trial/carência/suspensão/cobrança DEVE retornar cedo para loja isenta. As 3 lojas reais não podem ser afetadas.
- **Settings module de teste:** `DJANGO_SETTINGS_MODULE=config.settings.development`.
- **Rodar testes backend:** `make test-app APP=apps.stores` (Docker) ou `python manage.py test apps.stores`.
- **Rodar testes dash:** `npm test` em `pastita-dash`.
- **Commits em português.** Terminar mensagem com `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Catálogo de planos é fonte única:** `apps/stores/billing.py:PLAN_CATALOG`. Não duplicar valores.
- **Status canônicos** (`StoreSubscription.Status`): `trialing`, `active`, `past_due`, `suspended`, `canceled`.
- **Carência padrão = 3 dias** (`BILLING_GRACE_DAYS`); **dunning padrão = 3 dias** (`BILLING_DUNNING_DAYS`). Configuráveis por env.
- **Autocharge gated** por `settings.BILLING_AUTOCHARGE_ENABLED` (default False) — fica pronto mas desligado até o smoke test em produção.

---

## File Structure

**server2 (backend):**
- `apps/stores/billing.py` — MODIFY: adicionar `charges_setup_fee(plan_key)` e flag no catálogo.
- `config/settings/base.py` — MODIFY: `BILLING_GRACE_DAYS`, `BILLING_DUNNING_DAYS`, `BILLING_SETUP_FEE_ENABLED`.
- `apps/stores/models/subscription.py` — MODIFY: campos `grace_until`, `dunning_since`, `mp_setup_payment_id`.
- `apps/stores/services/subscription_lifecycle.py` — CREATE: lógica pura de transição de estado (trial→carência→suspenso; past_due→dunning→suspenso). Sem I/O, testável isolada.
- `apps/stores/services/subscription_service.py` — MODIFY: wiring da setup fee (preference one-off) no `create_subscription`; funções `cancel_subscription`, `change_plan`.
- `apps/stores/tasks.py` — MODIFY/CREATE: Celery task `enforce_subscription_lifecycle` que varre lojas e aplica `subscription_lifecycle`.
- `config/celery.py` — MODIFY: registrar a task no beat_schedule (diária).
- `apps/stores/api/views/subscription_views.py` — MODIFY: adicionar `StoreSubscriptionDetailView` (GET status), `StoreSubscriptionCancelView`, `StoreSubscriptionChangePlanView`.
- `apps/stores/urls.py` — MODIFY: rotas das novas views.
- `apps/public_api/` (order create) — MODIFY: recusar pedido se loja suspensa.
- `apps/stores/webhooks` / `mercadopago_handler.py` — MODIFY: tratar pagamento de setup fee (match por `mp_setup_payment_id`).

**pastita-dash (frontend):**
- `src/services/billing.ts` — MODIFY: `getSubscription`, `cancelSubscription`, `changePlan`; corrigir comentário desatualizado.
- `src/pages/plano/SubscriptionManagementPage.tsx` — CREATE: status, próxima cobrança, cancelar, up/downgrade.
- `src/components/billing/PaywallModal.tsx` — CREATE: modal "faça upgrade" disparado no 400 de limite.
- `src/pages/products/ProductFormModal.tsx` — MODIFY: capturar 400 de limite e abrir PaywallModal.
- `src/components/layout/Navbar.tsx` — MODIFY: item "Assinatura" na navegação.

**Ops (sem código):**
- Checklist de go-live do autocharge em produção (Task 13).

---

## TASK 1 — Toggle de setup fee no catálogo + settings de carência/dunning

**Files:**
- Modify: `apps/stores/billing.py`
- Modify: `config/settings/base.py:621-628`
- Test: `apps/stores/tests/test_billing_catalog.py`

**Interfaces:**
- Produces: `billing.charges_setup_fee(plan_key) -> bool`; cada plano em `PLAN_CATALOG` ganha `'charges_setup_fee': bool` (default `False` no primeiro ship — caminho mais curto). Settings: `BILLING_GRACE_DAYS:int`, `BILLING_DUNNING_DAYS:int`, `BILLING_SETUP_FEE_ENABLED:bool`.

- [ ] **Step 1: Escrever o teste falhando**

```python
# apps/stores/tests/test_billing_catalog.py
from django.test import TestCase
from apps.stores import billing


class SetupFeeToggleTest(TestCase):
    def test_charges_setup_fee_default_false(self):
        # Toggle por plano; default desligado no primeiro ship (caminho curto).
        self.assertFalse(billing.charges_setup_fee('starter'))

    def test_charges_setup_fee_respects_catalog_flag(self):
        original = billing.PLAN_CATALOG['pro'].get('charges_setup_fee')
        billing.PLAN_CATALOG['pro']['charges_setup_fee'] = True
        try:
            self.assertTrue(billing.charges_setup_fee('pro'))
        finally:
            if original is None:
                billing.PLAN_CATALOG['pro'].pop('charges_setup_fee', None)
            else:
                billing.PLAN_CATALOG['pro']['charges_setup_fee'] = original

    def test_unknown_plan_falls_back_to_default(self):
        self.assertFalse(billing.charges_setup_fee('inexistente'))
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python manage.py test apps.stores.tests.test_billing_catalog -v 2`
Expected: FAIL — `AttributeError: module 'apps.stores.billing' has no attribute 'charges_setup_fee'`

- [ ] **Step 3: Implementar no `billing.py`**

Adicionar `'charges_setup_fee': False` em cada um dos 3 planos do `PLAN_CATALOG` (logo abaixo de `'monthly_price'`). Depois adicionar o helper após `within_product_limit`:

```python
def charges_setup_fee(plan_key):
    """True se ESTE plano deve cobrar a taxa de adesão (setup_fee). Toggle por plano."""
    return bool(get_plan(plan_key).get('charges_setup_fee', False))
```

- [ ] **Step 4: Adicionar settings de carência/dunning/setup**

Em `config/settings/base.py`, logo após `BILLING_PANEL_URL` (linha ~623):

```python
# Dias de carência após o fim do trial antes de suspender a loja.
BILLING_GRACE_DAYS = int(os.environ.get('BILLING_GRACE_DAYS', '3'))
# Dias em past_due (cobrança falhou) antes de suspender.
BILLING_DUNNING_DAYS = int(os.environ.get('BILLING_DUNNING_DAYS', '3'))
# Kill-switch global da cobrança de adesão (além do toggle por plano).
BILLING_SETUP_FEE_ENABLED = os.environ.get('BILLING_SETUP_FEE_ENABLED', 'false').lower() == 'true'
```

- [ ] **Step 5: Rodar e ver passar**

Run: `python manage.py test apps.stores.tests.test_billing_catalog -v 2`
Expected: PASS (3 testes)

- [ ] **Step 6: Commit**

```bash
git add apps/stores/billing.py config/settings/base.py apps/stores/tests/test_billing_catalog.py
git commit -m "feat(billing): toggle de setup fee por plano + settings de carencia/dunning"
```

---

## TASK 2 — Campos de ciclo de vida na StoreSubscription

**Files:**
- Modify: `apps/stores/models/subscription.py`
- Create: migration (autogerada)
- Test: `apps/stores/tests/test_subscription_lifecycle_fields.py`

**Interfaces:**
- Produces: `StoreSubscription.grace_until: DateTimeField(null)`, `.dunning_since: DateTimeField(null)`, `.mp_setup_payment_id: CharField`.

- [ ] **Step 1: Escrever o teste falhando**

```python
# apps/stores/tests/test_subscription_lifecycle_fields.py
from django.test import TestCase
from django.utils import timezone
from apps.stores.models import Store, StoreSubscription


class SubscriptionLifecycleFieldsTest(TestCase):
    def test_new_fields_exist_and_default_null(self):
        store = Store.objects.create(name='Loja X', slug='loja-x')
        sub = StoreSubscription.objects.create(store=store)
        self.assertIsNone(sub.grace_until)
        self.assertIsNone(sub.dunning_since)
        self.assertEqual(sub.mp_setup_payment_id, '')

    def test_grace_until_persists(self):
        store = Store.objects.create(name='Loja Y', slug='loja-y')
        sub = StoreSubscription.objects.create(store=store)
        when = timezone.now()
        sub.grace_until = when
        sub.save(update_fields=['grace_until'])
        sub.refresh_from_db()
        self.assertEqual(sub.grace_until, when)
```

> Nota: se `Store.objects.create(name=, slug=)` exigir mais campos obrigatórios, leia `apps/stores/models/base.py` e adicione o mínimo necessário (ex.: `owner`). Use a factory existente se houver (`grep -rn "StoreFactory\|def create_store" apps/stores/tests`).

- [ ] **Step 2: Rodar e ver falhar**

Run: `python manage.py test apps.stores.tests.test_subscription_lifecycle_fields -v 2`
Expected: FAIL — `AttributeError: 'StoreSubscription' object has no attribute 'grace_until'`

- [ ] **Step 3: Adicionar os campos ao modelo**

Em `apps/stores/models/subscription.py`, após `canceled_at` (linha 30):

```python
    # Ciclo de vida do billing (Fase 1)
    grace_until = models.DateTimeField(null=True, blank=True)      # fim da carência pós-trial
    dunning_since = models.DateTimeField(null=True, blank=True)    # início do past_due
    mp_setup_payment_id = models.CharField(max_length=255, blank=True, default='')  # pagamento da adesão
```

- [ ] **Step 4: Gerar e aplicar a migration**

Run:
```bash
python manage.py makemigrations stores
python manage.py migrate stores
```
Expected: cria `apps/stores/migrations/00XX_subscription_lifecycle_fields.py` e aplica sem erro.

- [ ] **Step 5: Rodar e ver passar**

Run: `python manage.py test apps.stores.tests.test_subscription_lifecycle_fields -v 2`
Expected: PASS (2 testes)

- [ ] **Step 6: Commit**

```bash
git add apps/stores/models/subscription.py apps/stores/migrations/ apps/stores/tests/test_subscription_lifecycle_fields.py
git commit -m "feat(billing): campos grace_until/dunning_since/mp_setup_payment_id na assinatura"
```

---

## TASK 3 — Lógica pura de transição de ciclo de vida

Decide a próxima transição SEM tocar no banco nem no MP — função pura, fácil de testar exaustivamente. A task Celery (Task 4) aplica o que esta função decide.

**Files:**
- Create: `apps/stores/services/subscription_lifecycle.py`
- Test: `apps/stores/tests/test_subscription_lifecycle.py`

**Interfaces:**
- Produces: `decide_transition(*, status, trial_ends_at, grace_until, dunning_since, now, grace_days, dunning_days, billing_exempt) -> Transition`, onde `Transition` é um dataclass com `.action` em `{'none','start_grace','suspend','keep'}` e `.set_grace_until: datetime|None`.

- [ ] **Step 1: Escrever os testes falhando**

```python
# apps/stores/tests/test_subscription_lifecycle.py
from datetime import timedelta
from django.test import SimpleTestCase
from django.utils import timezone
from apps.stores.services.subscription_lifecycle import decide_transition, Transition

NOW = timezone.now()
GRACE = 3
DUN = 3


def call(**kw):
    base = dict(
        status='trialing', trial_ends_at=None, grace_until=None,
        dunning_since=None, now=NOW, grace_days=GRACE, dunning_days=DUN,
        billing_exempt=False,
    )
    base.update(kw)
    return decide_transition(**base)


class DecideTransitionTest(SimpleTestCase):
    def test_exempt_store_never_transitions(self):
        t = call(billing_exempt=True, status='trialing',
                 trial_ends_at=NOW - timedelta(days=99))
        self.assertEqual(t.action, 'none')

    def test_active_subscription_is_kept(self):
        t = call(status='active', trial_ends_at=NOW - timedelta(days=10))
        self.assertEqual(t.action, 'keep')

    def test_trial_still_running_does_nothing(self):
        t = call(status='trialing', trial_ends_at=NOW + timedelta(days=5))
        self.assertEqual(t.action, 'none')

    def test_trial_expired_no_grace_yet_starts_grace(self):
        t = call(status='trialing', trial_ends_at=NOW - timedelta(hours=1),
                 grace_until=None)
        self.assertEqual(t.action, 'start_grace')
        self.assertEqual(t.set_grace_until, NOW + timedelta(days=GRACE))

    def test_grace_not_over_keeps_waiting(self):
        t = call(status='trialing', trial_ends_at=NOW - timedelta(days=1),
                 grace_until=NOW + timedelta(days=1))
        self.assertEqual(t.action, 'none')

    def test_grace_over_suspends(self):
        t = call(status='trialing', trial_ends_at=NOW - timedelta(days=5),
                 grace_until=NOW - timedelta(hours=1))
        self.assertEqual(t.action, 'suspend')

    def test_past_due_starts_dunning_clock(self):
        t = call(status='past_due', dunning_since=None)
        self.assertEqual(t.action, 'start_grace')  # reaproveita set de relógio
        self.assertIsNotNone(t.set_grace_until)

    def test_past_due_dunning_over_suspends(self):
        t = call(status='past_due', dunning_since=NOW - timedelta(days=DUN + 1))
        self.assertEqual(t.action, 'suspend')

    def test_already_suspended_or_canceled_is_terminal(self):
        self.assertEqual(call(status='suspended').action, 'none')
        self.assertEqual(call(status='canceled').action, 'none')
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python manage.py test apps.stores.tests.test_subscription_lifecycle -v 2`
Expected: FAIL — `ModuleNotFoundError: subscription_lifecycle`

- [ ] **Step 3: Implementar a lógica pura**

```python
# apps/stores/services/subscription_lifecycle.py
"""
Decisão pura do ciclo de vida da assinatura (sem I/O).

Regras:
- Loja isenta (grandfather) nunca transiciona.
- 'active' é mantida.
- 'trialing': se o trial venceu e não há carência marcada → inicia carência
  (grace_until = now + grace_days). Se a carência venceu → suspende.
- 'past_due' (cobrança falhou): se não há relógio de dunning → inicia
  (set_grace_until = now + dunning_days, gravado em dunning_since pela task).
  Se o dunning venceu → suspende.
- 'suspended'/'canceled' são terminais.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


@dataclass(frozen=True)
class Transition:
    action: str                      # 'none' | 'start_grace' | 'suspend' | 'keep'
    set_grace_until: Optional[datetime] = None


def decide_transition(*, status, trial_ends_at, grace_until, dunning_since,
                      now, grace_days, dunning_days, billing_exempt) -> Transition:
    if billing_exempt:
        return Transition('none')

    if status == 'active':
        return Transition('keep')

    if status in ('suspended', 'canceled'):
        return Transition('none')

    if status == 'trialing':
        if not trial_ends_at or trial_ends_at > now:
            return Transition('none')
        # trial venceu
        if grace_until is None:
            return Transition('start_grace', set_grace_until=now + timedelta(days=grace_days))
        if grace_until <= now:
            return Transition('suspend')
        return Transition('none')

    if status == 'past_due':
        if dunning_since is None:
            return Transition('start_grace', set_grace_until=now + timedelta(days=dunning_days))
        if now - dunning_since >= timedelta(days=dunning_days):
            return Transition('suspend')
        return Transition('none')

    return Transition('none')
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python manage.py test apps.stores.tests.test_subscription_lifecycle -v 2`
Expected: PASS (9 testes)

- [ ] **Step 5: Commit**

```bash
git add apps/stores/services/subscription_lifecycle.py apps/stores/tests/test_subscription_lifecycle.py
git commit -m "feat(billing): logica pura de transicao trial->carencia->suspensao e dunning"
```

---

## TASK 4 — Celery task que aplica o ciclo de vida + registro no beat

**Files:**
- Modify: `apps/stores/tasks.py`
- Modify: `config/celery.py:24+` (beat_schedule)
- Test: `apps/stores/tests/test_enforce_subscription_task.py`

**Interfaces:**
- Consumes: `subscription_lifecycle.decide_transition` (Task 3), campos da Task 2.
- Produces: `apps.stores.tasks.enforce_subscription_lifecycle()` (Celery task) — varre `StoreSubscription` não-terminais e aplica a transição: grava `grace_until`/`dunning_since` ou move status para `suspended`. Retorna dict `{'scanned', 'suspended', 'grace_started'}`.

- [ ] **Step 1: Escrever o teste falhando**

```python
# apps/stores/tests/test_enforce_subscription_task.py
from datetime import timedelta
from django.test import TestCase, override_settings
from django.utils import timezone
from apps.stores.models import Store, StoreSubscription
from apps.stores.tasks import enforce_subscription_lifecycle


def mk(slug, **store_kw):
    return Store.objects.create(name=slug, slug=slug, **store_kw)


@override_settings(BILLING_GRACE_DAYS=3, BILLING_DUNNING_DAYS=3)
class EnforceSubscriptionTaskTest(TestCase):
    def test_expired_trial_starts_grace(self):
        store = mk('s1', trial_ends_at=timezone.now() - timedelta(hours=1))
        sub = StoreSubscription.objects.create(store=store, status='trialing')
        res = enforce_subscription_lifecycle()
        sub.refresh_from_db()
        self.assertIsNotNone(sub.grace_until)
        self.assertEqual(sub.status, 'trialing')
        self.assertEqual(res['grace_started'], 1)

    def test_grace_over_suspends(self):
        store = mk('s2', trial_ends_at=timezone.now() - timedelta(days=5))
        StoreSubscription.objects.create(
            store=store, status='trialing',
            grace_until=timezone.now() - timedelta(hours=1),
        )
        res = enforce_subscription_lifecycle()
        sub = StoreSubscription.objects.get(store=store)
        self.assertEqual(sub.status, 'suspended')
        self.assertEqual(res['suspended'], 1)

    def test_exempt_store_untouched(self):
        store = mk('s3', trial_ends_at=timezone.now() - timedelta(days=99),
                   billing_exempt=True)
        StoreSubscription.objects.create(store=store, status='trialing')
        enforce_subscription_lifecycle()
        sub = StoreSubscription.objects.get(store=store)
        self.assertEqual(sub.status, 'trialing')
        self.assertIsNone(sub.grace_until)

    def test_active_untouched(self):
        store = mk('s4', trial_ends_at=timezone.now() - timedelta(days=30))
        StoreSubscription.objects.create(store=store, status='active')
        enforce_subscription_lifecycle()
        sub = StoreSubscription.objects.get(store=store)
        self.assertEqual(sub.status, 'active')
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python manage.py test apps.stores.tests.test_enforce_subscription_task -v 2`
Expected: FAIL — `ImportError: cannot import name 'enforce_subscription_lifecycle'`

- [ ] **Step 3: Implementar a task**

Adicionar em `apps/stores/tasks.py` (topo: garanta `from celery import shared_task`, `from django.conf import settings`, `from django.utils import timezone`):

```python
@shared_task(name='stores.enforce_subscription_lifecycle')
def enforce_subscription_lifecycle():
    """
    Varredura diária: aplica trial→carência→suspensão e past_due→dunning→suspensão.
    Loja isenta é ignorada (decide_transition retorna 'none').
    """
    from apps.stores.models import StoreSubscription
    from apps.stores.services.subscription_lifecycle import decide_transition

    now = timezone.now()
    grace_days = getattr(settings, 'BILLING_GRACE_DAYS', 3)
    dunning_days = getattr(settings, 'BILLING_DUNNING_DAYS', 3)
    counts = {'scanned': 0, 'suspended': 0, 'grace_started': 0}

    qs = (StoreSubscription.objects
          .exclude(status__in=['suspended', 'canceled'])
          .select_related('store'))
    for sub in qs:
        counts['scanned'] += 1
        store = sub.store
        t = decide_transition(
            status=sub.status,
            trial_ends_at=store.trial_ends_at,
            grace_until=sub.grace_until,
            dunning_since=sub.dunning_since,
            now=now, grace_days=grace_days, dunning_days=dunning_days,
            billing_exempt=bool(getattr(store, 'billing_exempt', False)),
        )
        if t.action == 'start_grace':
            if sub.status == 'past_due':
                sub.dunning_since = now
                sub.save(update_fields=['dunning_since'])
            else:
                sub.grace_until = t.set_grace_until
                sub.save(update_fields=['grace_until'])
            counts['grace_started'] += 1
        elif t.action == 'suspend':
            sub.status = StoreSubscription.Status.SUSPENDED
            sub.save(update_fields=['status'])
            counts['suspended'] += 1
    return counts
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python manage.py test apps.stores.tests.test_enforce_subscription_task -v 2`
Expected: PASS (4 testes)

- [ ] **Step 5: Registrar no beat (diário às 4h)**

Em `config/celery.py`, dentro de `app.conf.beat_schedule = { ... }`:

```python
    'enforce-subscription-lifecycle': {
        'task': 'stores.enforce_subscription_lifecycle',
        'schedule': crontab(hour=4, minute=0),  # diário 04:00
    },
```

- [ ] **Step 6: Commit**

```bash
git add apps/stores/tasks.py config/celery.py apps/stores/tests/test_enforce_subscription_task.py
git commit -m "feat(billing): celery task diaria que aplica carencia/suspensao + dunning"
```

---

## TASK 5 — Enforcement: loja suspensa não aceita pedido no storefront

**Files:**
- Modify: order-create do storefront público (achar com `grep -rn "def create" apps/public_api/ | grep -i order` ou `grep -rn "StoreOrder.objects.create\|create_order\|checkout" apps/public_api/views.py`)
- Create: helper `apps/stores/billing.py:store_accepts_orders(store)`
- Test: `apps/stores/tests/test_suspended_store_blocks_orders.py`

**Interfaces:**
- Consumes: status da `StoreSubscription`.
- Produces: `billing.store_accepts_orders(store) -> bool` (False só se assinatura `suspended` E não isenta). O endpoint público de criação de pedido retorna **HTTP 403** com `{'detail': 'Loja temporariamente indisponível.'}` quando False.

- [ ] **Step 1: Escrever o teste falhando (helper puro)**

```python
# apps/stores/tests/test_suspended_store_blocks_orders.py
from django.test import TestCase
from apps.stores.models import Store, StoreSubscription
from apps.stores import billing


class StoreAcceptsOrdersTest(TestCase):
    def test_store_without_subscription_accepts(self):
        store = Store.objects.create(name='a', slug='a')
        self.assertTrue(billing.store_accepts_orders(store))

    def test_suspended_store_rejects(self):
        store = Store.objects.create(name='b', slug='b')
        StoreSubscription.objects.create(store=store, status='suspended')
        self.assertFalse(billing.store_accepts_orders(store))

    def test_suspended_but_exempt_accepts(self):
        store = Store.objects.create(name='c', slug='c', billing_exempt=True)
        StoreSubscription.objects.create(store=store, status='suspended')
        self.assertTrue(billing.store_accepts_orders(store))

    def test_active_store_accepts(self):
        store = Store.objects.create(name='d', slug='d')
        StoreSubscription.objects.create(store=store, status='active')
        self.assertTrue(billing.store_accepts_orders(store))
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python manage.py test apps.stores.tests.test_suspended_store_blocks_orders -v 2`
Expected: FAIL — `AttributeError: module 'apps.stores.billing' has no attribute 'store_accepts_orders'`

- [ ] **Step 3: Implementar o helper**

Em `apps/stores/billing.py`, após `charges_setup_fee`:

```python
def store_accepts_orders(store):
    """False só se a assinatura está 'suspended' e a loja NÃO é isenta."""
    if is_billing_exempt(store):
        return True
    sub = getattr(store, 'subscription', None)
    return not (sub is not None and sub.status == 'suspended')
```

- [ ] **Step 4: Escrever o teste de integração (endpoint 403)**

Leia o teste de criação de pedido público existente (`grep -rn "by-token\|public.*order\|criar.*pedido" apps/public_api/tests/ apps/stores/tests/`) e siga o padrão. Esqueleto:

```python
    def test_suspended_store_order_returns_403(self):
        # Arrange: loja suspensa + payload mínimo de pedido válido (copie do teste de sucesso existente)
        # Act: POST no endpoint público de criação de pedido
        # Assert: response.status_code == 403 e 'indisponível' in response.json()['detail'].lower()
```

> Se não houver teste de criação de pedido público para copiar, peça ao revisor o caminho exato do endpoint antes de implementar o guard — não adivinhe a rota.

- [ ] **Step 5: Implementar o guard no endpoint**

No início do método de criação de pedido (após resolver a `store`, antes de criar):

```python
from apps.stores import billing
if not billing.store_accepts_orders(store):
    return Response({'detail': 'Loja temporariamente indisponível.'},
                    status=status.HTTP_403_FORBIDDEN)
```

- [ ] **Step 6: Rodar e ver passar**

Run: `python manage.py test apps.stores.tests.test_suspended_store_blocks_orders -v 2`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add apps/stores/billing.py apps/public_api/ apps/stores/tests/test_suspended_store_blocks_orders.py
git commit -m "feat(billing): loja suspensa recusa novos pedidos no storefront (403)"
```

---

## TASK 6 — Cobrança da taxa de adesão (preference one-off, toggle-gated)

Quando a loja assina e o plano cobra adesão (`BILLING_SETUP_FEE_ENABLED` E `charges_setup_fee(plan)`), cria uma `preference` MercadoPago one-off para a adesão e retorna `setup_init_point`. O pagamento marca `setup_fee_paid` via webhook (Task 7).

**Files:**
- Modify: `apps/stores/services/subscription_service.py:create_subscription`
- Test: `apps/stores/tests/test_setup_fee_charge.py`

**Interfaces:**
- Consumes: `billing.charges_setup_fee` (Task 1), `settings.BILLING_SETUP_FEE_ENABLED`.
- Produces: retorno de `create_subscription` ganha chave opcional `'setup_init_point': str` (presente só quando a adesão é cobrada); grava `sub.mp_setup_payment_id` com o id da preference.

- [ ] **Step 1: Escrever o teste falhando (com MP mockado)**

```python
# apps/stores/tests/test_setup_fee_charge.py
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from apps.stores.models import Store, StoreSubscription
from apps.stores.services import subscription_service


def _mp_mock():
    sdk = MagicMock()
    sdk.preapproval().create.return_value = {
        'status': 201,
        'response': {'id': 'PRE-1', 'init_point': 'https://mp/sub'},
    }
    sdk.preference().create.return_value = {
        'status': 201,
        'response': {'id': 'PREF-1', 'init_point': 'https://mp/setup'},
    }
    return sdk


@override_settings(BILLING_SETUP_FEE_ENABLED=True)
class SetupFeeChargeTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name='Loja', slug='loja')

    @patch('apps.stores.billing.charges_setup_fee', return_value=True)
    @patch('apps.stores.services.subscription_service._sdk')
    def test_setup_fee_returns_setup_init_point(self, sdk_p, _fee):
        sdk_p.return_value = _mp_mock()
        out = subscription_service.create_subscription(
            self.store, 'pro', 'dono@x.com', 'https://painel/plano')
        self.assertEqual(out['setup_init_point'], 'https://mp/setup')
        sub = StoreSubscription.objects.get(store=self.store)
        self.assertEqual(sub.mp_setup_payment_id, 'PREF-1')

    @patch('apps.stores.billing.charges_setup_fee', return_value=False)
    @patch('apps.stores.services.subscription_service._sdk')
    def test_no_setup_fee_when_plan_toggle_off(self, sdk_p, _fee):
        sdk_p.return_value = _mp_mock()
        out = subscription_service.create_subscription(
            self.store, 'pro', 'dono@x.com', 'https://painel/plano')
        self.assertNotIn('setup_init_point', out)

    @override_settings(BILLING_SETUP_FEE_ENABLED=False)
    @patch('apps.stores.billing.charges_setup_fee', return_value=True)
    @patch('apps.stores.services.subscription_service._sdk')
    def test_global_killswitch_disables_setup_fee(self, sdk_p, _fee):
        sdk_p.return_value = _mp_mock()
        out = subscription_service.create_subscription(
            self.store, 'pro', 'dono@x.com', 'https://painel/plano')
        self.assertNotIn('setup_init_point', out)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python manage.py test apps.stores.tests.test_setup_fee_charge -v 2`
Expected: FAIL — `KeyError: 'setup_init_point'`

- [ ] **Step 3: Implementar o charge da adesão**

Em `subscription_service.create_subscription`, logo após o bloco `sub, _ = StoreSubscription.objects.update_or_create(...)` (antes do `return`):

```python
    result = {'init_point': init_point, 'preapproval_id': preapproval_id}

    # Taxa de adesão: preference one-off, gated por killswitch global + toggle do plano.
    setup_enabled = getattr(settings, 'BILLING_SETUP_FEE_ENABLED', False)
    if setup_enabled and billing.charges_setup_fee(plan_key):
        pref = sdk.preference().create({
            'items': [{
                'title': f"Adesão Cardapidex {plan['name']} — {store.name}",
                'quantity': 1,
                'unit_price': float(plan['setup_fee']),
                'currency_id': 'BRL',
            }],
            'back_urls': {'success': back_url, 'pending': back_url, 'failure': back_url},
            'external_reference': f"setup:{store.slug}",
        })
        if pref.get('status') in (200, 201):
            body = pref['response']
            sub.mp_setup_payment_id = body.get('id', '')
            sub.save(update_fields=['mp_setup_payment_id'])
            result['setup_init_point'] = body.get('init_point') or body.get('sandbox_init_point', '')
        else:
            logger.error('MP setup-fee preference falhou p/ loja %s: %s', store.slug, pref)

    logger.info('Preapproval criado p/ loja %s plano %s: %s', store.slug, plan_key, preapproval_id)
    return result
```

E REMOVER o `return {'init_point': init_point, 'preapproval_id': preapproval_id}` antigo e o `logger.info(...)` que ficavam logo abaixo (linhas 91-92) — agora estão acima.

- [ ] **Step 4: Rodar e ver passar**

Run: `python manage.py test apps.stores.tests.test_setup_fee_charge -v 2`
Expected: PASS (3 testes). Rodar também o suite de integração existente para garantir zero regressão: `python manage.py test apps.stores.tests.test_subscription_integration -v 2` → PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/stores/services/subscription_service.py apps/stores/tests/test_setup_fee_charge.py
git commit -m "feat(billing): cobranca da taxa de adesao via preference one-off (toggle por plano)"
```

---

## TASK 7 — Webhook marca setup_fee_paid quando a adesão é paga

**Files:**
- Modify: `apps/stores/services/subscription_service.py` (nova função `mark_setup_fee_paid`)
- Modify: `apps/webhooks/handlers/mercadopago_handler.py:_handle_payment_webhook`
- Test: `apps/stores/tests/test_setup_fee_paid_webhook.py`

**Interfaces:**
- Consumes: `mp_setup_payment_id` (Task 6).
- Produces: `subscription_service.mark_setup_fee_paid(external_reference, mp_status) -> dict`; o payment webhook chama isso quando o `external_reference` começa com `setup:`.

- [ ] **Step 1: Escrever o teste falhando**

```python
# apps/stores/tests/test_setup_fee_paid_webhook.py
from django.test import TestCase
from apps.stores.models import Store, StoreSubscription
from apps.stores.services import subscription_service


class SetupFeePaidTest(TestCase):
    def test_marks_setup_fee_paid_on_approved(self):
        store = Store.objects.create(name='Loja', slug='loja-sf')
        StoreSubscription.objects.create(store=store, mp_setup_payment_id='PREF-9')
        res = subscription_service.mark_setup_fee_paid('setup:loja-sf', 'approved')
        self.assertTrue(res['processed'])
        sub = StoreSubscription.objects.get(store=store)
        self.assertTrue(sub.setup_fee_paid)

    def test_ignores_non_approved(self):
        store = Store.objects.create(name='Loja', slug='loja-sf2')
        StoreSubscription.objects.create(store=store, mp_setup_payment_id='PREF-8')
        res = subscription_service.mark_setup_fee_paid('setup:loja-sf2', 'pending')
        self.assertFalse(res['processed'])
        self.assertFalse(StoreSubscription.objects.get(store=store).setup_fee_paid)

    def test_unknown_store_is_safe(self):
        res = subscription_service.mark_setup_fee_paid('setup:nao-existe', 'approved')
        self.assertFalse(res['processed'])
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python manage.py test apps.stores.tests.test_setup_fee_paid_webhook -v 2`
Expected: FAIL — `AttributeError: module has no attribute 'mark_setup_fee_paid'`

- [ ] **Step 3: Implementar a função**

Em `subscription_service.py`, no fim do arquivo:

```python
def mark_setup_fee_paid(external_reference, mp_status):
    """Marca setup_fee_paid=True quando o pagamento da adesão é aprovado.
    external_reference no formato 'setup:<store_slug>'."""
    if mp_status != 'approved' or not (external_reference or '').startswith('setup:'):
        return {'processed': False, 'reason': 'not_approved_or_not_setup'}
    slug = external_reference.split(':', 1)[1]
    sub = StoreSubscription.objects.filter(store__slug=slug).first()
    if not sub:
        return {'processed': False, 'reason': 'subscription_not_found'}
    if not sub.setup_fee_paid:
        sub.setup_fee_paid = True
        sub.save(update_fields=['setup_fee_paid'])
    logger.info('Setup fee paga p/ loja %s', slug)
    return {'processed': True}
```

- [ ] **Step 4: Ligar no payment webhook**

Em `mercadopago_handler.py:_handle_payment_webhook`, logo no início (após obter `data_id`), antes da lógica de pedido de loja, adicionar o desvio para pagamentos da plataforma:

```python
        # Pagamento da PLATAFORMA (adesão SaaS): external_reference começa com 'setup:'.
        ext_ref = str(payload.get('external_reference')
                      or payload.get('data', {}).get('external_reference') or '')
        if ext_ref.startswith('setup:'):
            from apps.stores.services import subscription_service
            mp_status = (payload.get('status')
                         or payload.get('data', {}).get('status') or '')
            return subscription_service.mark_setup_fee_paid(ext_ref, mp_status)
```

> Nota: se o webhook de pagamento do MP não trouxer `external_reference` no payload (alguns só trazem `data.id`), o desvio acima não dispara e o fluxo segue como pagamento de pedido — sem regressão. O caminho de marcação fica robusto quando o `external_reference` chega (configurável no painel MP).

- [ ] **Step 5: Rodar e ver passar**

Run: `python manage.py test apps.stores.tests.test_setup_fee_paid_webhook -v 2`
Expected: PASS (3 testes)

- [ ] **Step 6: Commit**

```bash
git add apps/stores/services/subscription_service.py apps/webhooks/handlers/mercadopago_handler.py apps/stores/tests/test_setup_fee_paid_webhook.py
git commit -m "feat(billing): webhook marca setup_fee_paid ao aprovar pagamento da adesao"
```

---

## TASK 8 — Endpoints de gestão: status, cancelar, trocar plano

**Files:**
- Modify: `apps/stores/services/subscription_service.py` (`cancel_subscription`, `change_plan`)
- Modify: `apps/stores/api/views/subscription_views.py` (3 novas views)
- Modify: `apps/stores/urls.py:206` (3 rotas)
- Test: `apps/stores/tests/test_subscription_management.py`

**Interfaces:**
- Consumes: `_sdk()`, `apply_preapproval_event`.
- Produces:
  - `GET /api/v1/stores/{slug}/subscription/` → `{plan, status, current_period_end, setup_fee_paid, grace_until}` (200) ou `{status:'none'}` se sem assinatura.
  - `POST /api/v1/stores/{slug}/subscription/cancel/` → cancela preapproval no MP, status→`canceled`. 200.
  - `POST /api/v1/stores/{slug}/subscription/change-plan/` body `{plan}` → cria novo preapproval do novo plano, retorna `{init_point}`. 201.
  - `subscription_service.cancel_subscription(store) -> StoreSubscription`; `change_plan(store, new_plan, payer_email, back_url) -> dict`.

- [ ] **Step 1: Escrever o teste falhando**

```python
# apps/stores/tests/test_subscription_management.py
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.stores.models import Store, StoreSubscription

User = get_user_model()


class SubscriptionManagementAPITest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='dono', email='dono@x.com', password='x')
        self.store = Store.objects.create(name='Loja', slug='loja', owner=self.user)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_status_none_when_no_subscription(self):
        r = self.client.get(f'/api/v1/stores/{self.store.slug}/subscription/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], 'none')

    def test_status_returns_plan_and_status(self):
        StoreSubscription.objects.create(store=self.store, plan='pro', status='active')
        r = self.client.get(f'/api/v1/stores/{self.store.slug}/subscription/')
        self.assertEqual(r.json()['plan'], 'pro')
        self.assertEqual(r.json()['status'], 'active')

    @patch('apps.stores.services.subscription_service._sdk')
    def test_cancel_sets_canceled(self, sdk_p):
        sdk = MagicMock()
        sdk.preapproval().update.return_value = {'status': 200, 'response': {}}
        sdk_p.return_value = sdk
        StoreSubscription.objects.create(
            store=self.store, plan='pro', status='active', mp_preapproval_id='PRE-1')
        r = self.client.post(f'/api/v1/stores/{self.store.slug}/subscription/cancel/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(StoreSubscription.objects.get(store=self.store).status, 'canceled')

    @patch('apps.stores.services.subscription_service.create_subscription')
    def test_change_plan_creates_new_preapproval(self, create_p):
        create_p.return_value = {'init_point': 'https://mp/new', 'preapproval_id': 'PRE-2'}
        StoreSubscription.objects.create(store=self.store, plan='starter', status='active')
        r = self.client.post(
            f'/api/v1/stores/{self.store.slug}/subscription/change-plan/',
            {'plan': 'pro'}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()['init_point'], 'https://mp/new')
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python manage.py test apps.stores.tests.test_subscription_management -v 2`
Expected: FAIL — 404 (rotas não existem)

- [ ] **Step 3: Implementar os services**

Em `subscription_service.py`:

```python
def cancel_subscription(store):
    """Cancela o preapproval no MP e marca a assinatura como canceled."""
    sub = StoreSubscription.objects.filter(store=store).first()
    if not sub:
        raise SubscriptionError('Loja sem assinatura.')
    if sub.mp_preapproval_id:
        try:
            _sdk().preapproval().update(sub.mp_preapproval_id, {'status': 'cancelled'})
        except Exception as e:
            logger.error('Falha ao cancelar preapproval %s: %s', sub.mp_preapproval_id, e)
    sub.status = StoreSubscription.Status.CANCELED
    sub.canceled_at = timezone.now()
    sub.save(update_fields=['status', 'canceled_at'])
    if store.plan != billing.DEFAULT_PLAN:
        store.plan = billing.DEFAULT_PLAN
        store.save(update_fields=['plan'])
    return sub


def change_plan(store, new_plan, payer_email, back_url):
    """Troca de plano = cancela o preapproval atual e cria um novo do plano alvo."""
    if new_plan not in ('starter', 'pro', 'premium'):
        raise SubscriptionError('Plano inválido.')
    existing = StoreSubscription.objects.filter(store=store).first()
    if existing and existing.mp_preapproval_id:
        try:
            _sdk().preapproval().update(existing.mp_preapproval_id, {'status': 'cancelled'})
        except Exception as e:
            logger.error('Falha ao cancelar preapproval antigo: %s', e)
    return create_subscription(store, new_plan, payer_email, back_url)
```

- [ ] **Step 4: Implementar as views + rotas**

Em `subscription_views.py` adicionar (reaproveitando o check de permissão — extraia um helper `_can_manage(store, user)` a partir do bloco existente em `StoreSubscribeView.post`):

```python
from rest_framework import generics  # se necessário
from apps.stores.models import StoreSubscription


def _can_manage(store, user):
    return (store.owner_id == user.id
            or store.staff.filter(id=user.id).exists()
            or user.is_superuser)


class StoreSubscriptionDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, store_slug):
        store = get_object_or_404(Store, slug=store_slug)
        if not _can_manage(store, request.user):
            return Response({'detail': 'Sem permissão.'}, status=403)
        sub = StoreSubscription.objects.filter(store=store).first()
        if not sub:
            return Response({'status': 'none'})
        return Response({
            'plan': sub.plan, 'status': sub.status,
            'current_period_end': sub.current_period_end,
            'setup_fee_paid': sub.setup_fee_paid,
            'grace_until': sub.grace_until,
        })


class StoreSubscriptionCancelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, store_slug):
        store = get_object_or_404(Store, slug=store_slug)
        if not _can_manage(store, request.user):
            return Response({'detail': 'Sem permissão.'}, status=403)
        try:
            sub = subscription_service.cancel_subscription(store)
        except subscription_service.SubscriptionError as e:
            return Response({'detail': str(e)}, status=400)
        return Response({'status': sub.status})


class StoreSubscriptionChangePlanView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, store_slug):
        store = get_object_or_404(Store, slug=store_slug)
        if not _can_manage(store, request.user):
            return Response({'detail': 'Sem permissão.'}, status=403)
        plan = (request.data.get('plan') or '').strip()
        back_url = f"{getattr(settings, 'BILLING_PANEL_URL', 'https://painel.cardapidex.com.br')}/assinatura"
        try:
            result = subscription_service.change_plan(
                store, plan, (request.user.email or '').strip(), back_url)
        except subscription_service.SubscriptionError as e:
            return Response({'detail': str(e)}, status=400)
        return Response(result, status=201)
```

E refatorar `StoreSubscribeView.post` para usar `_can_manage`.

Em `apps/stores/urls.py`, ao lado da rota `subscribe/` (linha 206), adicionar o import e as rotas:

```python
from .api.views.subscription_views import (
    StoreSubscribeView, StoreSubscriptionDetailView,
    StoreSubscriptionCancelView, StoreSubscriptionChangePlanView,
)
# ...
    path('subscription/', StoreSubscriptionDetailView.as_view(), name='store-subscription-detail'),
    path('subscription/cancel/', StoreSubscriptionCancelView.as_view(), name='store-subscription-cancel'),
    path('subscription/change-plan/', StoreSubscriptionChangePlanView.as_view(), name='store-subscription-change-plan'),
```

> Confirme o prefixo real das rotas de loja lendo o `urlpatterns` em volta da linha 206 (pode haver `<slug:store_slug>/` no include). As rotas novas devem ficar no MESMO nível do `subscribe/`.

- [ ] **Step 5: Rodar e ver passar**

Run: `python manage.py test apps.stores.tests.test_subscription_management -v 2`
Expected: PASS (4 testes)

- [ ] **Step 6: Commit**

```bash
git add apps/stores/services/subscription_service.py apps/stores/api/views/subscription_views.py apps/stores/urls.py apps/stores/tests/test_subscription_management.py
git commit -m "feat(billing): endpoints de status, cancelamento e troca de plano da assinatura"
```

---

## TASK 9 — Service do dash: getSubscription, cancel, changePlan

**Files:**
- Modify: `pastita-dash/src/services/billing.ts`
- Test: `pastita-dash/src/services/__tests__/billing.test.ts` (criar se não existir; veja `grep -rn "vi.mock\|jest.mock" src/services/__tests__` para o padrão de mock do `api`)

**Interfaces:**
- Consumes: endpoints da Task 8.
- Produces: `getSubscription(slug)`, `cancelSubscription(slug)`, `changePlan(slug, plan)` em `billing.ts`; tipo `SubscriptionStatus`.

- [ ] **Step 1: Escrever o teste falhando**

```ts
// src/services/__tests__/billing.test.ts
import { describe, it, expect, vi } from 'vitest';
import api from '../api';
import { getSubscription, cancelSubscription, changePlan } from '../billing';

vi.mock('../api');

describe('billing subscription service', () => {
  it('getSubscription chama o endpoint certo', async () => {
    (api.get as any).mockResolvedValue({ data: { status: 'active', plan: 'pro' } });
    const res = await getSubscription('loja');
    expect(api.get).toHaveBeenCalledWith('/stores/loja/subscription/');
    expect(res.status).toBe('active');
  });

  it('cancelSubscription faz POST no cancel', async () => {
    (api.post as any).mockResolvedValue({ data: { status: 'canceled' } });
    const res = await cancelSubscription('loja');
    expect(api.post).toHaveBeenCalledWith('/stores/loja/subscription/cancel/');
    expect(res.status).toBe('canceled');
  });

  it('changePlan faz POST com o plano', async () => {
    (api.post as any).mockResolvedValue({ data: { init_point: 'https://mp/x' } });
    const res = await changePlan('loja', 'premium');
    expect(api.post).toHaveBeenCalledWith('/stores/loja/subscription/change-plan/', { plan: 'premium' });
    expect(res.init_point).toBe('https://mp/x');
  });
});
```

> Ajuste o import de teste (`vitest` vs `jest`) ao runner do projeto — veja o topo de qualquer arquivo em `src/**/__tests__`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `npm test -- billing` (em `pastita-dash`)
Expected: FAIL — `getSubscription is not exported`

- [ ] **Step 3: Implementar no `billing.ts`**

Corrigir o comentário do cabeçalho (linhas 3-4) — pagamento JÁ existe — e adicionar ao fim do arquivo:

```ts
/** Estado da assinatura retornado pelo backend (Task 8). */
export interface SubscriptionStatus {
  status: 'none' | 'trialing' | 'active' | 'past_due' | 'suspended' | 'canceled';
  plan?: PlanKey;
  current_period_end?: string | null;
  setup_fee_paid?: boolean;
  grace_until?: string | null;
}

export async function getSubscription(storeSlug: string): Promise<SubscriptionStatus> {
  const { data } = await api.get(`/stores/${storeSlug}/subscription/`);
  return data;
}

export async function cancelSubscription(storeSlug: string): Promise<{ status: string }> {
  const { data } = await api.post(`/stores/${storeSlug}/subscription/cancel/`);
  return data;
}

export async function changePlan(
  storeSlug: string,
  plan: PlanKey,
): Promise<{ init_point: string; preapproval_id?: string }> {
  const { data } = await api.post(`/stores/${storeSlug}/subscription/change-plan/`, { plan });
  return data;
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `npm test -- billing`
Expected: PASS (3 testes)

- [ ] **Step 5: Commit**

```bash
git add src/services/billing.ts src/services/__tests__/billing.test.ts
git commit -m "feat(dash): service de gestao de assinatura (status/cancelar/trocar plano)"
```

---

## TASK 10 — Página de gestão de assinatura no painel

**Files:**
- Create: `pastita-dash/src/pages/plano/SubscriptionManagementPage.tsx`
- Modify: roteador (achar com `grep -rn "PlanoPage\|/plano" src/App.tsx src/routes* src/**/routes*`)
- Modify: `src/components/layout/Navbar.tsx` (array `sections` — item "Assinatura" → `/assinatura`)

**Interfaces:**
- Consumes: `getSubscription`, `cancelSubscription`, `changePlan`, `getPlans` (Task 9).

> Esta é uma task de UI sem teste unitário obrigatório (componente de página integra serviços já testados). Deliverable: página funcional renderizando status real e ações.

- [ ] **Step 1: Ler o padrão da página existente**

Leia `src/pages/plano/PlanoPage.tsx` inteiro para copiar layout, uso de `useStore()`, loading/empty/error states e estilo dos cards.

- [ ] **Step 2: Criar a página**

```tsx
// src/pages/plano/SubscriptionManagementPage.tsx
import { useEffect, useState } from 'react';
import { useStore } from '../../hooks/useStore'; // ajuste o path real (ver PlanoPage)
import {
  getSubscription, cancelSubscription, changePlan, getPlans,
  type SubscriptionStatus, type Plan,
} from '../../services/billing';

const STATUS_LABEL: Record<string, string> = {
  none: 'Sem assinatura', trialing: 'Em trial', active: 'Ativa',
  past_due: 'Pagamento atrasado', suspended: 'Suspensa', canceled: 'Cancelada',
};

export default function SubscriptionManagementPage() {
  const { store } = useStore();
  const slug = store?.slug;
  const [sub, setSub] = useState<SubscriptionStatus | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    setLoading(true);
    Promise.all([getSubscription(slug), getPlans()])
      .then(([s, p]) => { setSub(s); setPlans(p); })
      .catch(() => setError('Não foi possível carregar a assinatura.'))
      .finally(() => setLoading(false));
  }, [slug]);

  async function handleCancel() {
    if (!slug || !confirm('Cancelar a assinatura? A loja será rebaixada ao fim do período.')) return;
    setBusy(true);
    try { const r = await cancelSubscription(slug); setSub({ ...(sub as SubscriptionStatus), status: r.status as any }); }
    catch { setError('Falha ao cancelar.'); }
    finally { setBusy(false); }
  }

  async function handleChange(plan: Plan) {
    if (!slug) return;
    setBusy(true);
    try { const r = await changePlan(slug, plan.key); window.location.href = r.init_point; }
    catch { setError('Falha ao trocar de plano.'); setBusy(false); }
  }

  if (loading) return <div className="p-6">Carregando assinatura…</div>;
  if (error) return <div className="p-6 text-red-600">{error}</div>;

  return (
    <div className="p-6 space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Assinatura</h1>
        <p className="text-sm opacity-70">
          Status: <strong>{STATUS_LABEL[sub?.status ?? 'none']}</strong>
          {sub?.plan && <> — plano <strong>{sub.plan}</strong></>}
          {sub?.current_period_end && <> — próxima cobrança {new Date(sub.current_period_end).toLocaleDateString('pt-BR')}</>}
        </p>
      </header>

      {sub?.status === 'suspended' && (
        <div className="rounded border border-red-300 bg-red-50 p-4 text-red-700">
          Sua loja está suspensa por falta de pagamento. Reative assinando um plano abaixo.
        </div>
      )}

      <section className="grid gap-4 md:grid-cols-3">
        {plans.map((p) => (
          <div key={p.key} className="rounded-lg border p-4">
            <h2 className="font-medium">{p.name}</h2>
            <p className="text-lg">R$ {p.monthly_price.toFixed(2)}/mês</p>
            <button disabled={busy || sub?.plan === p.key}
              onClick={() => handleChange(p)}
              className="mt-3 w-full rounded bg-amber-600 px-3 py-2 text-white disabled:opacity-50">
              {sub?.plan === p.key ? 'Plano atual' : 'Mudar para este'}
            </button>
          </div>
        ))}
      </section>

      {sub && sub.status !== 'none' && sub.status !== 'canceled' && (
        <button disabled={busy} onClick={handleCancel}
          className="text-sm text-red-600 underline disabled:opacity-50">
          Cancelar assinatura
        </button>
      )}
    </div>
  );
}
```

> Ajuste imports (`useStore`, classes Tailwind) ao que `PlanoPage.tsx` usa de fato. Não invente hook novo.

- [ ] **Step 3: Registrar a rota `/assinatura` e o item de navbar**

No roteador, adicionar `<Route path="/assinatura" element={<SubscriptionManagementPage />} />` (lazy import seguindo o padrão das outras rotas). Na `Navbar.tsx`, adicionar no array `sections` (seção de Config/Conta) um item `{ label: 'Assinatura', to: '/assinatura' }` — siga a forma exata dos itens existentes.

- [ ] **Step 4: Verificar build + lint**

Run: `npm run build && npm run lint`
Expected: build OK, sem novos erros de lint/TS.

- [ ] **Step 5: Commit**

```bash
git add src/pages/plano/SubscriptionManagementPage.tsx src/components/layout/Navbar.tsx src/App.tsx
git commit -m "feat(dash): pagina de gestao de assinatura (status, trocar plano, cancelar)"
```

---

## TASK 11 — Paywall: modal de upgrade ao bater no limite de produtos

**Files:**
- Create: `pastita-dash/src/components/billing/PaywallModal.tsx`
- Modify: `pastita-dash/src/pages/products/ProductFormModal.tsx`
- Test: `pastita-dash/src/components/billing/__tests__/PaywallModal.test.tsx`

**Interfaces:**
- Produces: `<PaywallModal open message onClose />` — CTA "Ver planos" navega para `/assinatura`.
- O backend já retorna 400 com `detail` contendo "Limite do plano" (visto em `product_views.py`). O handler captura isso.

- [ ] **Step 1: Escrever o teste falhando**

```tsx
// src/components/billing/__tests__/PaywallModal.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PaywallModal } from '../PaywallModal';

describe('PaywallModal', () => {
  it('não renderiza quando open=false', () => {
    render(<PaywallModal open={false} message="x" onClose={() => {}} />);
    expect(screen.queryByText(/faça upgrade/i)).toBeNull();
  });

  it('mostra a mensagem e o CTA quando open=true', () => {
    render(<PaywallModal open message="Limite do plano atingido (50 produtos)." onClose={() => {}} />);
    expect(screen.getByText(/limite do plano atingido/i)).toBeTruthy();
    expect(screen.getByText(/ver planos/i)).toBeTruthy();
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `npm test -- PaywallModal`
Expected: FAIL — módulo não existe

- [ ] **Step 3: Implementar o modal**

```tsx
// src/components/billing/PaywallModal.tsx
interface PaywallModalProps {
  open: boolean;
  message: string;
  onClose: () => void;
}

export function PaywallModal({ open, message, onClose }: PaywallModalProps) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-semibold">Faça upgrade do seu plano</h2>
        <p className="mt-2 text-sm opacity-80">{message}</p>
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} className="rounded px-3 py-2 text-sm">Agora não</button>
          <a href="/assinatura" className="rounded bg-amber-600 px-3 py-2 text-sm text-white">Ver planos</a>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `npm test -- PaywallModal`
Expected: PASS (2 testes)

- [ ] **Step 5: Integrar no ProductFormModal**

Ler `src/pages/products/ProductFormModal.tsx`, achar o `catch` do submit de criação. Adicionar estado `const [paywall, setPaywall] = useState<string | null>(null);` e, no catch:

```tsx
      const detail = err?.response?.data?.detail ?? '';
      if (err?.response?.status === 400 && /limite do plano/i.test(detail)) {
        setPaywall(detail);
        return;
      }
      // ...tratamento de erro existente segue aqui
```

E renderizar no fim do JSX: `<PaywallModal open={!!paywall} message={paywall ?? ''} onClose={() => setPaywall(null)} />` (importar o componente).

- [ ] **Step 6: Verificar build**

Run: `npm run build`
Expected: OK.

- [ ] **Step 7: Commit**

```bash
git add src/components/billing/PaywallModal.tsx src/pages/products/ProductFormModal.tsx src/components/billing/__tests__/PaywallModal.test.tsx
git commit -m "feat(dash): paywall modal de upgrade ao bater no limite de produtos"
```

---

## TASK 12 — Banner de loja suspensa/atrasada no painel

**Files:**
- Modify: `pastita-dash/src/components/layout/TrialBanner.tsx` (estender para status suspended/past_due)
- Test: extensão do teste existente do banner se houver (`grep -rn "TrialBanner" src/**/__tests__`)

**Interfaces:**
- Consumes: `getSubscription` (Task 9) OU o status já presente no `store` se exposto. Mostra faixa vermelha "Loja suspensa — reative" linkando `/assinatura`.

- [ ] **Step 1: Ler o banner atual**

Ler `src/components/layout/TrialBanner.tsx` inteiro.

- [ ] **Step 2: Escrever/estender teste**

Se houver teste do TrialBanner, adicionar caso: status `suspended` → renderiza texto "suspensa" e link `/assinatura`. Senão, criar `src/components/layout/__tests__/TrialBanner.test.tsx` com esse caso (mock de `getSubscription` retornando `{status:'suspended'}`).

- [ ] **Step 3: Implementar**

Adicionar no componente: buscar subscription status (ou receber via prop/contexto existente) e, se `suspended`/`past_due`, renderizar faixa vermelha com link para `/assinatura`, ANTES do bloco de trial. Manter o comportamento de trial intacto.

- [ ] **Step 4: Rodar testes + build**

Run: `npm test -- TrialBanner && npm run build`
Expected: PASS + build OK.

- [ ] **Step 5: Commit**

```bash
git add src/components/layout/TrialBanner.tsx src/components/layout/__tests__/
git commit -m "feat(dash): aviso de loja suspensa/atrasada com CTA de reativacao"
```

---

## TASK 13 — Go-live do autocharge em produção (ops, sem código)

Esta task NÃO tem TDD — é um checklist operacional executado com loja de teste real. Não ligar `BILLING_AUTOCHARGE_ENABLED=true` antes de todos os itens acima estarem mergeados e deployados.

- [ ] **Step 1: Provisionar credenciais MP de produção**
  - Confirmar `MERCADO_PAGO_ACCESS_TOKEN` (prod), `MERCADO_PAGO_WEBHOOK_SECRET`, `BACKEND_URL` público e `BILLING_PANEL_URL` corretos no `.env` de produção.
  - Garantir que `MERCADO_PAGO_SANDBOX_TOKEN` está VAZIO em produção (senão `_sdk()` usa sandbox).

- [ ] **Step 2: Configurar a URL de webhook no painel MercadoPago**
  - Apontar para `https://<BACKEND_URL>/webhooks/payments/mercadopago/`.
  - Habilitar eventos: `preapproval`, `subscription_authorized_payment`, `payment`.
  - Garantir que o painel envia `external_reference` nos pagamentos (necessário p/ setup fee — Task 7).

- [ ] **Step 3: Deploy do server2 com as migrations**
  - Seguir a skill `cardapidex-deployment-safe`. Atenção ao disco no build (histórico de crash de Postgres).
  - `python manage.py migrate stores` aplicado em produção.

- [ ] **Step 4: Smoke test ponta a ponta com loja de teste**
  - Criar loja nova via `/cadastro` (NÃO isenta).
  - Assinar plano `starter` no painel → autorizar cartão de teste real no MP → confirmar webhook `authorized` → `StoreSubscription.status == 'active'` e `store.plan == 'starter'`.
  - Forçar trial vencido (ajustar `trial_ends_at` no admin) → rodar `enforce_subscription_lifecycle` manualmente (`python manage.py shell -c "from apps.stores.tasks import enforce_subscription_lifecycle as t; print(t())"`) → confirmar `grace_until` setado.
  - Avançar a carência → rodar de novo → confirmar `status == 'suspended'` e storefront recusando pedido (403).
  - Cancelar no painel → confirmar preapproval cancelado no MP e `status == 'canceled'`.

- [ ] **Step 5: Ligar o autocharge**
  - Só após o smoke test verde: setar `BILLING_AUTOCHARGE_ENABLED=true` no `.env` de produção e reiniciar worker/beat.
  - Verificar nos logs a execução da `enforce-subscription-lifecycle` no dia seguinte.

- [ ] **Step 6: Confirmar isenção das 3 lojas reais**
  - `python manage.py shell -c "from apps.stores.models import Store; print([(s.slug, s.billing_exempt) for s in Store.objects.filter(billing_exempt=True)])"`
  - Confirmar que Cê Saladas e as outras 2 estão `billing_exempt=True` ANTES de ligar o autocharge.

---

## Self-Review (preenchido)

**1. Cobertura do spec:**
- Bloco 1.1 (task de expiração) → Tasks 3+4. ✓
- Bloco 1.2 (enforcement suspensão) → Task 5 (storefront) + Task 12 (aviso painel). ✓
- Bloco 1.3 (dunning) → lógica em Task 3 (`past_due`→dunning→suspend) + aplicação Task 4. ✓
- Bloco 1.4 (gestão de assinatura) → Tasks 8+9+10. ✓
- Bloco 1.5 (paywall) → Task 11. ✓
- Bloco 1.6 (setup fee + toggle + autocharge prod) → Tasks 1+6+7 (setup fee/toggle) + Task 13 (autocharge go-live). ✓

**2. Placeholders:** Nenhum "TODO/TBD" no código dos passos. As notas "leia o arquivo X / confirme a rota" são instruções de integração em código existente que eu não devo adivinhar (endpoint público de pedido, roteador do dash), não placeholders de implementação.

**3. Consistência de tipos:** `decide_transition`/`Transition` (Task 3) consumidos com a mesma assinatura na Task 4. Campos `grace_until`/`dunning_since`/`mp_setup_payment_id` (Task 2) usados consistentes em 4/5/6/7/8. `SubscriptionStatus` (Task 9) consumido em 10/12. `charges_setup_fee` (Task 1) usado em 6. `store_accepts_orders` (Task 5) usado no guard.

**Dependência entre tasks:** 1→2→3→4 (backend core); 5 depende de 1; 6→7 depende de 1+2; 8 depende de 2; 9 depende de 8; 10/12 dependem de 9; 11 independente; 13 por último. Ordem de execução = ordem numérica.
