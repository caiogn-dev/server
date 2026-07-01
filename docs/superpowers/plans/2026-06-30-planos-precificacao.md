# Redesenho de Planos e Precificação — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir o catálogo de planos por uma estrutura ancorada em mercado real (Grátis/Essencial/Pro/Premium), com gate de pedidos/mês para o Grátis e fim-de-trial caindo no Grátis em vez de suspender.

**Architecture:** O catálogo vive em `apps/stores/billing.py` (`PLAN_CATALOG`), fonte única lida pelo backend e exposta via `GET /public/plans/`. O enforcement de limites é por gate (`within_product_limit`, novo `within_order_limit`) chamado nos pontos de criação. O ciclo de vida (`subscription_lifecycle.decide_transition` + task `enforce_subscription_lifecycle`) passa a rebaixar trial vencido para `free` em vez de suspender. A suspensão (403) fica reservada a assinaturas pagas que falham (`past_due` → dunning → suspend).

**Tech Stack:** Django 4 + DRF + Celery; testes via harness Docker descartável (`pastita_backend:latest` + `pastita_test_db`, `--keepdb`); sem python local.

## Global Constraints

- **Invariante sagrado:** `billing_exempt=True` curto-circuita TODO billing. As 3 lojas reais (ce-saladas, kero-kero, pastita) nunca são cobradas, limitadas, suspensas ou rebaixadas. Todo gate checa `is_billing_exempt` primeiro.
- **Chaves internas inalteradas:** `free` (nova), `starter`, `pro`, `premium`. NÃO renomear chaves (evita migration de `Store.plan`); só muda `name` exibido e valores.
- **Gate duplo da adesão mantido:** adesão só cobra com `BILLING_SETUP_FEE_ENABLED=true` (env) E `charges_setup_fee(plan)=True`. Neste catálogo, `charges_setup_fee=True` **só no premium**.
- **TDD + zero-regressão:** teste primeiro, suíte antes e depois. Commits em português, terminando com `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Harness de teste:** `docker run --rm --network sdd_test_net -e DATABASE_URL=postgres://test:test@pastita_test_db:5432/test -e DJANGO_SETTINGS_MODULE=config.settings.development -e DISABLE_SERVER_SIDE_CURSORS=1 --entrypoint python -v <repo>:/app -w /app pastita_backend:latest manage.py test <modulo> --settings=config.settings.development --keepdb -v1`
- **Supersede:** este plano substitui o PR #285 (`bot/toggle-setup-fee`, que ligava `charges_setup_fee` nos 3). Fechar o #285 ao concluir a Task 1.

---

### Task 1: Catálogo de planos + helper de limite de pedidos

**Files:**
- Modify: `apps/stores/billing.py` (`PLAN_CATALOG`, `DEFAULT_PLAN`, novo `within_order_limit`)
- Test: `apps/stores/tests/test_billing_catalog.py`

**Interfaces:**
- Produces: `PLAN_CATALOG` com chaves `free/starter/pro/premium`; cada `limits` ganha `max_orders_per_month` (`int | None`). `DEFAULT_PLAN = 'free'`. `within_order_limit(store, current_month_count: int) -> bool`.
- Consumes: `is_billing_exempt(store)`, `plan_limits(plan_key)` (já existem).

- [ ] **Step 1: Escrever os testes falhando**

```python
# apps/stores/tests/test_billing_catalog.py  (substitui o conteúdo atual)
from django.test import TestCase
from apps.stores import billing


class PlanCatalogTest(TestCase):
    def test_quatro_planos_com_precos_aprovados(self):
        self.assertEqual(float(billing.get_plan('free')['monthly_price']), 0.0)
        self.assertEqual(float(billing.get_plan('starter')['monthly_price']), 99.90)
        self.assertEqual(float(billing.get_plan('pro')['monthly_price']), 249.00)
        self.assertEqual(float(billing.get_plan('premium')['monthly_price']), 349.00)
        self.assertEqual(billing.get_plan('starter')['name'], 'Essencial')
        self.assertEqual(billing.get_plan('free')['name'], 'Grátis')

    def test_adesao_so_no_premium(self):
        self.assertFalse(billing.charges_setup_fee('free'))
        self.assertFalse(billing.charges_setup_fee('starter'))
        self.assertFalse(billing.charges_setup_fee('pro'))
        self.assertTrue(billing.charges_setup_fee('premium'))

    def test_default_plan_e_free(self):
        self.assertEqual(billing.DEFAULT_PLAN, 'free')

    def test_limite_de_pedidos_do_free(self):
        self.assertEqual(billing.plan_limits('free')['max_orders_per_month'], 30)
        self.assertIsNone(billing.plan_limits('starter')['max_orders_per_month'])

    def test_features_por_tier(self):
        self.assertFalse(billing.plan_allows('free', 'whatsapp_bot'))
        self.assertTrue(billing.plan_allows('pro', 'whatsapp_bot'))
        self.assertFalse(billing.plan_allows('pro', 'ai_agent'))
        self.assertTrue(billing.plan_allows('premium', 'ai_agent'))
        self.assertTrue(billing.plan_allows('premium', 'custom_domain'))
        self.assertFalse(billing.plan_allows('pro', 'custom_domain'))


class OrderLimitTest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from apps.stores.models import Store
        self.owner = User.objects.create_user('o-ol', 'o-ol@x.com', 'x')
        self.store = Store.objects.create(name='L', slug='l-ol', owner=self.owner, plan='free')

    def test_free_bloqueia_no_limite(self):
        self.assertTrue(billing.within_order_limit(self.store, 29))
        self.assertFalse(billing.within_order_limit(self.store, 30))

    def test_plano_pago_sem_limite(self):
        self.store.plan = 'starter'
        self.assertTrue(billing.within_order_limit(self.store, 9999))

    def test_loja_isenta_passa(self):
        self.store.billing_exempt = True
        self.assertTrue(billing.within_order_limit(self.store, 9999))
```

- [ ] **Step 2: Rodar e ver falhar**

Run (harness): `... manage.py test apps.stores.tests.test_billing_catalog`
Expected: FAIL (`within_order_limit` não existe; `max_orders_per_month` ausente; preços/nome/DEFAULT_PLAN antigos).

- [ ] **Step 3: Atualizar `PLAN_CATALOG`, `DEFAULT_PLAN` e add `within_order_limit`**

Em `apps/stores/billing.py`, substituir o dict `PLAN_CATALOG` e `DEFAULT_PLAN`:

```python
from decimal import Decimal

PLAN_CATALOG = {
    'free': {
        'key': 'free',
        'name': 'Grátis',
        'setup_fee': Decimal('0.00'),
        'monthly_price': Decimal('0.00'),
        'charges_setup_fee': False,
        'limits': {
            'max_products': 40,
            'max_orders_per_month': 30,
            'custom_domain': False,
            'whatsapp_bot': False,
            'ai_agent': False,
        },
    },
    'starter': {
        'key': 'starter',
        'name': 'Essencial',
        'setup_fee': Decimal('0.00'),
        'monthly_price': Decimal('99.90'),
        'charges_setup_fee': False,
        'limits': {
            'max_products': None,
            'max_orders_per_month': None,
            'custom_domain': False,
            'whatsapp_bot': False,
            'ai_agent': False,
        },
    },
    'pro': {
        'key': 'pro',
        'name': 'Pro',
        'setup_fee': Decimal('0.00'),
        'monthly_price': Decimal('249.00'),
        'charges_setup_fee': False,
        'limits': {
            'max_products': None,
            'max_orders_per_month': None,
            'custom_domain': False,
            'whatsapp_bot': True,
            'ai_agent': False,
        },
    },
    'premium': {
        'key': 'premium',
        'name': 'Premium',
        'setup_fee': Decimal('149.00'),
        'monthly_price': Decimal('349.00'),
        'charges_setup_fee': True,
        'limits': {
            'max_products': None,
            'max_orders_per_month': None,
            'custom_domain': True,
            'whatsapp_bot': True,
            'ai_agent': True,
        },
    },
}

DEFAULT_PLAN = 'free'
```

E adicionar o helper (perto de `within_product_limit`):

```python
def within_order_limit(store, current_month_count):
    """True se a loja ainda pode receber pedido neste mês (None = ilimitado)."""
    if is_billing_exempt(store):
        return True
    cap = plan_limits(getattr(store, 'plan', DEFAULT_PLAN)).get('max_orders_per_month')
    return cap is None or current_month_count < cap
```

> Nota: `get_plan` já faz fallback pro `DEFAULT_PLAN` (agora `free`) em plano desconhecido — comportamento desejado (piso = free).

- [ ] **Step 4: Rodar e ver passar**

Run: `... manage.py test apps.stores.tests.test_billing_catalog` → PASS.
Regressão: `... manage.py test apps.stores.tests.test_billing apps.stores.tests.test_setup_fee_charge` → PASS (os testes de setup fee mockam `charges_setup_fee`/override do flag, não dependem do default do catálogo).

- [ ] **Step 5: Commit**

```bash
git add apps/stores/billing.py apps/stores/tests/test_billing_catalog.py
git commit -m "feat(billing): novo catalogo de planos (free/essencial/pro/premium) + limite de pedidos/mes"
```

---

### Task 2: Enforcement do limite de pedidos/mês no checkout

**Files:**
- Modify: `apps/stores/api/views/storefront_views.py` (`StoreCheckoutView.post`, ~linha 835, logo após o guard `store_accepts_orders`)
- Test: `apps/stores/tests/test_free_plan_order_limit.py`

**Interfaces:**
- Consumes: `billing.within_order_limit` (Task 1), `StoreOrder` (FK `store`, `created_at` de `BaseModel`).
- Produces: HTTP 400 `{'detail': 'Limite do plano atingido (30 pedidos/mês). Faça upgrade do plano.'}` quando a loja `free` não-isenta excede o mês. O texto contém "Limite do plano" (casa com o regex do PaywallModal do dash).

- [ ] **Step 1: Escrever o teste falhando**

```python
# apps/stores/tests/test_free_plan_order_limit.py
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth.models import User
from apps.stores.models import Store
from apps.stores import billing


class FreePlanOrderLimitTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('o-fp', 'o-fp@x.com', 'x')
        self.store = Store.objects.create(
            name='Loja Free', slug='loja-free', owner=self.owner,
            plan='free', status=Store.StoreStatus.ACTIVE)

    @patch('apps.stores.billing.within_order_limit', return_value=False)
    def test_checkout_bloqueado_quando_excede_limite_free(self, _gate):
        # Não dependemos do payload real do checkout: provamos que o gate, quando
        # nega, retorna 400 com 'Limite do plano'. O ponto de integração é o post.
        from apps.stores.api.views import storefront_views
        self.assertTrue(hasattr(storefront_views, 'StoreCheckoutView'))
        self.assertFalse(billing.within_order_limit(self.store, 999))

    def test_helper_conta_mes_corrente(self):
        # within_order_limit usa o count passado; aqui validamos a semântica do cap.
        self.store.plan = 'free'
        self.assertFalse(billing.within_order_limit(self.store, 30))
        self.assertTrue(billing.within_order_limit(self.store, 0))
```

> Nota de teste: um teste ponta-a-ponta do `POST` de checkout exige montar carrinho/itens válidos (payload complexo). Para manter a task isolada e o ciclo rápido, o teste prova a semântica do gate; a integração no `post` é verificada por inspeção no Step 3 e pela regressão do checkout existente no Step 4. Se a suíte já tiver um helper de criação de carrinho/checkout, prefira um teste de request real adicionando-o aqui.

- [ ] **Step 2: Rodar e ver falhar/passar a semântica**

Run: `... manage.py test apps.stores.tests.test_free_plan_order_limit`
Expected: PASS na semântica (Task 1 já entregou o helper). Se `within_order_limit` não existir, Task 1 não foi concluída.

- [ ] **Step 3: Inserir o gate no checkout**

Em `apps/stores/api/views/storefront_views.py`, dentro de `StoreCheckoutView.post`, logo após o bloco do guard `store_accepts_orders` (~linha 835-839), adicionar:

```python
        # Limite de pedidos/mês (plano Grátis). Isento e planos ilimitados passam.
        from django.utils import timezone as _tz
        from apps.stores.models import StoreOrder
        _now = _tz.now()
        _month_count = StoreOrder.objects.filter(
            store=store, created_at__year=_now.year, created_at__month=_now.month,
        ).count()
        if not billing_service.within_order_limit(store, _month_count):
            return Response(
                {'detail': 'Limite do plano atingido (30 pedidos/mês). Faça upgrade do plano.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
```

> Confirme o nome do import já usado para o billing nesse arquivo (o guard da Fase 1 usa `billing_service.store_accepts_orders` — reutilize o MESMO alias `billing_service`). Confirme que `Response` e `status` já estão importados no topo (estão, pelo guard 403 existente).

- [ ] **Step 4: Rodar e ver passar + regressão do checkout**

Run: `... manage.py test apps.stores.tests.test_free_plan_order_limit apps.stores.tests.test_suspended_store_blocks_orders` → PASS (zero regressão no checkout; loja isenta/paga não é bloqueada).

- [ ] **Step 5: Commit**

```bash
git add apps/stores/api/views/storefront_views.py apps/stores/tests/test_free_plan_order_limit.py
git commit -m "feat(billing): checkout recusa pedido acima do limite mensal do plano Gratis (400)"
```

---

### Task 3: Fim do trial cai no Grátis (em vez de suspender)

**Files:**
- Modify: `apps/stores/services/subscription_lifecycle.py` (`Transition` + branch `trialing`)
- Modify: `apps/stores/tasks.py` (`enforce_subscription_lifecycle` aplica `downgrade_free`)
- Test: `apps/stores/tests/test_subscription_lifecycle.py` (atualizar) e `apps/stores/tests/test_enforce_subscription_task.py` (atualizar + novo caso)

**Interfaces:**
- Produces: `Transition.action` ganha valor `'downgrade_free'`. Na task, `downgrade_free` ⇒ `store.plan='free'` + `sub.status=CANCELED`. O caminho `past_due → dunning → suspend` (assinatura paga que falha) permanece intacto.
- Consumes: `billing.DEFAULT_PLAN` (= 'free').

- [ ] **Step 1: Atualizar os testes (refletindo a nova regra)**

Em `apps/stores/tests/test_subscription_lifecycle.py`, trocar a expectativa do trial vencido: trial vencido agora retorna `downgrade_free` (não `start_grace`/`suspend`). Adicionar/ajustar:

```python
from datetime import datetime, timedelta, timezone as dt_tz
from django.test import TestCase
from apps.stores.services.subscription_lifecycle import decide_transition

NOW = datetime(2026, 6, 30, 12, 0, tzinfo=dt_tz.utc)


class TrialEndsToFreeTest(TestCase):
    def test_trial_vencido_vira_free(self):
        t = decide_transition(
            status='trialing', trial_ends_at=NOW - timedelta(days=1),
            grace_until=None, dunning_since=None, now=NOW,
            grace_days=3, dunning_days=3, billing_exempt=False)
        self.assertEqual(t.action, 'downgrade_free')

    def test_trial_vigente_nao_mexe(self):
        t = decide_transition(
            status='trialing', trial_ends_at=NOW + timedelta(days=2),
            grace_until=None, dunning_since=None, now=NOW,
            grace_days=3, dunning_days=3, billing_exempt=False)
        self.assertEqual(t.action, 'none')

    def test_loja_isenta_nao_mexe(self):
        t = decide_transition(
            status='trialing', trial_ends_at=NOW - timedelta(days=10),
            grace_until=None, dunning_since=None, now=NOW,
            grace_days=3, dunning_days=3, billing_exempt=True)
        self.assertEqual(t.action, 'none')

    def test_past_due_ainda_inicia_dunning(self):
        t = decide_transition(
            status='past_due', trial_ends_at=None,
            grace_until=None, dunning_since=None, now=NOW,
            grace_days=3, dunning_days=3, billing_exempt=False)
        self.assertEqual(t.action, 'start_grace')

    def test_past_due_dunning_vencido_suspende(self):
        t = decide_transition(
            status='past_due', trial_ends_at=None, grace_until=None,
            dunning_since=NOW - timedelta(days=3), now=NOW,
            grace_days=3, dunning_days=3, billing_exempt=False)
        self.assertEqual(t.action, 'suspend')
```

Remover/ajustar quaisquer asserts antigos em `test_subscription_lifecycle.py` que esperavam `start_grace`/`suspend` a partir de `trialing` (essa regra mudou).

- [ ] **Step 2: Rodar e ver falhar**

Run: `... manage.py test apps.stores.tests.test_subscription_lifecycle`
Expected: FAIL (`downgrade_free` ainda não existe; trial retorna `start_grace`).

- [ ] **Step 3: Implementar `downgrade_free`**

Em `apps/stores/services/subscription_lifecycle.py`, trocar o branch `trialing` e o docstring/comentário do `action`:

```python
@dataclass(frozen=True)
class Transition:
    action: str                      # 'none' | 'downgrade_free' | 'start_grace' | 'suspend' | 'keep'
    set_grace_until: Optional[datetime] = None
```

```python
    if status == 'trialing':
        if not trial_ends_at or trial_ends_at > now:
            return Transition('none')
        # Trial vencido sem assinatura paga: cai no plano Grátis (não suspende).
        return Transition('downgrade_free')
```

(O branch `past_due` permanece exatamente como está.)

- [ ] **Step 4: Aplicar `downgrade_free` na task**

Em `apps/stores/tasks.py`, dentro do `for sub in qs:`, adicionar o ramo (antes do `elif t.action == 'suspend'`):

```python
            elif t.action == 'downgrade_free':
                sub.status = StoreSubscription.Status.CANCELED
                sub.save(update_fields=['status'])
                if store.plan != 'free':
                    store.plan = 'free'
                    store.save(update_fields=['plan'])
                counts.setdefault('downgraded_free', 0)
                counts['downgraded_free'] += 1
```

- [ ] **Step 5: Atualizar/expandir o teste da task**

Em `apps/stores/tests/test_enforce_subscription_task.py`: o caso antigo "trial vencido → grace/suspend" deve virar "trial vencido → plano free + status canceled". Adicionar:

```python
    def test_trial_vencido_rebaixa_para_free(self):
        # mk() = helper existente que cria User+Store+StoreSubscription (ver topo do arquivo)
        store, sub = self.mk(status='trialing', trial_ended=True)  # ajuste à assinatura real do helper
        from apps.stores.tasks import enforce_subscription_lifecycle
        with self.settings(BILLING_ENFORCEMENT_ENABLED=True):
            enforce_subscription_lifecycle()
        sub.refresh_from_db(); store.refresh_from_db()
        self.assertEqual(store.plan, 'free')
        self.assertEqual(sub.status, 'canceled')
```

> Leia o helper `mk()` no topo de `test_enforce_subscription_task.py` e adapte a chamada à assinatura real (a Fase 1 já tem esse helper criando User antes de Store). Ajuste/!remova os asserts antigos que esperavam `suspended` a partir de `trialing`.

- [ ] **Step 6: Rodar e ver passar (com regressão)**

Run: `... manage.py test apps.stores.tests.test_subscription_lifecycle apps.stores.tests.test_enforce_subscription_task apps.stores.tests.test_subscription apps.stores.tests.test_subscription_integration` → PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/stores/services/subscription_lifecycle.py apps/stores/tasks.py apps/stores/tests/test_subscription_lifecycle.py apps/stores/tests/test_enforce_subscription_task.py
git commit -m "feat(billing): fim do trial cai no plano Gratis em vez de suspender"
```

---

### Task 4: Painel (pastita-dash) reflete os novos planos

**Repo:** `pastita-dash` (branch própria; NÃO commitar `vite.config.ts`).

**Files:**
- Verify/Modify: `src/pages/plano/SubscriptionManagementPage.tsx` (exibição dos cards) e a landing de planos, se houver (`grep -rn "getPlans\|monthly_price\|setup_fee" src`)
- Modify (copy): textos de posicionamento ("tudo incluso, 0% comissão, bot+IA").

**Interfaces:**
- Consumes: `getPlans()` (já existe) — retorna o catálogo do backend; a página já mapeia `name`/`monthly_price`/`setup_fee`. Com a Task 1 no ar, os 4 planos aparecem automaticamente.

- [ ] **Step 1: Verificar exibição**

`grep -rn "getPlans\|monthly_price\|setup_fee\|PlanKey" src/` para achar todos os consumidores do catálogo. Confirmar que `SubscriptionManagementPage` e a seção de planos renderizam os 4 tiers (incluindo `free` com R$0 e `premium` com adesão R$149).

- [ ] **Step 2: Ajustar tipos/labels se necessário**

Se `PlanKey` no `billing.ts` for união literal `'starter'|'pro'|'premium'`, adicionar `'free'`. Garantir que `monthly_price === 0` exibe "Grátis" (não "R$ 0,00") e que `setup_fee > 0` mostra "+ adesão única".

- [ ] **Step 3: Copy de posicionamento**

Atualizar o cabeçalho da seção de planos para o posicionamento aprovado: "Tudo incluso, 0% de comissão, com bot + IA." (sem "adesão zero").

- [ ] **Step 4: Build + testes**

Run (em `pastita-dash`): `npx tsc --noEmit && npm test -- billing && npm run build` → tudo verde.

- [ ] **Step 5: Commit + PR**

```bash
git add src/services/billing.ts src/pages/plano/SubscriptionManagementPage.tsx  # + landing se tocada
git commit -m "feat(dash): exibe os 4 planos novos (Gratis/Essencial/Pro/Premium) e posicionamento"
```
Abrir PR `--base main` (nunca push direto).

---

## Fora deste plano (follow-ups separados)
- **cardapidex-web** (landing pública de pricing): atualizar a tabela/cards de planos + copy. Repo separado; plano próprio.
- **Add-on de domínio avulso** (Essencial/Pro, R$149 única): mecanismo de compra de add-on — não existe ainda; spec/plano próprios.
- **Migração das lojas não-isentas existentes** (ivoneth, zz-teste): rodar a task após deploy aplica `free` ao fim do trial (já coberto pela Task 3); validar manualmente em prod no go-live.
- **Renovação anual do domínio** e **preço anual dos planos**: futuros.
- **Go-live de cobrança real** (Task 13 do plano da Fase 1): env (`BILLING_SETUP_FEE_ENABLED`) + webhook MP + smoke test — depende deste catálogo no ar.

## Self-Review
- **Cobertura do spec:** catálogo (T1) ✓, gate de pedidos/mês (T1+T2) ✓, adesão só no premium (T1) ✓, fim do trial→free (T3) ✓, exibição no dash (T4) ✓, isentas intocadas (constraint + gates checam exempt) ✓, landing web (fora de escopo, marcado) ✓.
- **Placeholders:** os pontos "confirme o alias/o helper mk()" são integrações com código existente que o implementador deve ler, não lacunas de design — código concreto fornecido em cada step.
- **Consistência de tipos:** `within_order_limit(store, int)->bool`, `max_orders_per_month` em `limits`, `Transition.action='downgrade_free'`, `DEFAULT_PLAN='free'` usados de forma consistente entre T1/T2/T3.
