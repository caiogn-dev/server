# Gamificação & Fidelização — Fase 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expor o programa de fidelidade já existente no backend (progresso + resgate) no storefront web, criar a página de configuração no dash, banner de cupom destaque, e intent de saldo no bot — conforme `server2/docs/SPEC_GAMIFICACAO_FIDELIDADE_2026-07-28.md`.

**Architecture:** O motor (`LoyaltyService`, `StoreLoyaltyAccount`) e o resgate no checkout (`CheckoutService.create_order(use_loyalty_reward=True)`) já existem em produção. O trabalho é: (server2) qualificação configurável por categoria, `is_featured` no cupom, dados públicos de loyalty/cupom no app-config, endpoint de listagem para o dash, intent do bot e linha de fidelidade na mensagem de pago; (cardapidex-web) hook + cartão de progresso + resgate no checkout + banner; (pastita-dash) página Fidelidade & Cupons.

**Tech Stack:** Django 4 + DRF (server2), Next.js pages-router JSX + Vitest (cardapidex-web), React+TS + Jest (pastita-dash).

## Global Constraints

- server2: branch `development` (ÚNICA); testes via `bash /home/graco/WORK/scripts/server2-test.sh` (roda a suíte toda; **o script ignora args** — para um teste específico use o comando docker documentado na Task 1). Gate = zero falha nova vs baseline.
- cardapidex-web: branch `master` (ÚNICA); Vitest (`npm test`); **zero cor hardcoded** — só `var(--color-*)` do tema da loja; CSS global novo precisa ser importado em `pages/_app.js`.
- pastita-dash: branch `main` (ÚNICA, Vercel auto-deploy no push — só commitar local, push apenas na task de deploy); Jest (`npm test`); tokens Dark Luxe (`bg-surface`, `border-border-token`, `text-fg-token`, nunca `blue-100`/`green-100` etc.); componentes de `src/components/ui`.
- Commits em português. TDD: teste antes da implementação em toda task.
- `store.metadata` no dash: PATCH substitui o dict inteiro — **sempre** `{ ...currentMetadata, novaChave }`.
- Adiado (NÃO implementar): C3/C4/C5 proativos (carrinho abandonado, reativação, fidelidade proativa) — ficam para a fase do número mediador Cardapidex.

## File Structure

**server2** (`/home/graco/WORK/server2`):
- Modify: `apps/stores/services/loyalty_service.py` (qualificação configurável)
- Modify: `apps/stores/services/order_service.py:178-192` (usar helper novo no crédito)
- Modify: `apps/stores/services/checkout_service.py:645-666` (`_cart_salad_discount` usa helper)
- Modify: `apps/stores/models/coupon.py` + migration (`is_featured`)
- Modify: `apps/stores/api/serializers.py:1598,1661` (expor `is_featured`)
- Modify: `apps/stores/api/views/storefront_views.py` (app-config: `loyalty_program` + `featured_coupon`)
- Modify: `apps/stores/billing.py` (`coupon_banner` no PLAN_CATALOG)
- Modify: `apps/stores/api/views/loyalty_views.py` + `apps/stores/urls.py` (listagem de contas)
- Create: `apps/whatsapp/intents/handlers/loyalty.py`; Modify: `detector.py`, `handlers/__init__.py`
- Modify: `apps/stores/models/order.py:425-452` (linha de fidelidade no "pago")
- Tests: `apps/stores/tests/test_loyalty_qualifying.py`, `test_featured_coupon.py`, `test_loyalty_accounts_endpoint.py`, `apps/whatsapp/tests/test_loyalty_intent.py`

**cardapidex-web** (`/home/graco/WORK/cardapidex-web`):
- Modify: `src/services/storeApi.js` (`getLoyaltyStatus`)
- Create: `src/hooks/useLoyalty.js`, `src/utils/loyalty.js`
- Create: `src/components/LoyaltyProgressCard.jsx` + `.css`; `src/components/CouponBanner.jsx` + `.css`
- Modify: `src/components/CartSidebar.jsx`, `src/pages/Cardapio.jsx`, `src/components/checkout/OrderConfirmation.jsx`, `src/pages/CheckoutPage.jsx`, `pages/_app.js`
- Tests: `src/hooks/__tests__/useLoyalty.test.js`, `src/utils/__tests__/loyalty.test.js`, `src/components/__tests__/LoyaltyProgressCard.test.jsx`, `src/components/__tests__/CouponBanner.test.jsx`, `src/components/checkout/__tests__/OrderConfirmation.loyalty.test.jsx`

**pastita-dash** (`/home/graco/WORK/pastita-dash`):
- Create: `src/services/loyalty.ts`, `src/pages/loyalty/FidelidadePage.tsx`
- Modify: `src/services/coupons.ts` (tipo `is_featured`), `src/App.tsx`, `src/components/layout/navSections.tsx`, `src/components/layout/__tests__/navSections.test.tsx`
- Tests: `src/pages/loyalty/__tests__/FidelidadePage.test.tsx`

---

### Task 1: server2 — Qualificação configurável por categoria

**Files:**
- Modify: `apps/stores/services/loyalty_service.py`
- Modify: `apps/stores/services/order_service.py:178-192`
- Modify: `apps/stores/services/checkout_service.py:645` (`_cart_salad_discount`)
- Test: `apps/stores/tests/test_loyalty_qualifying.py`

**Interfaces:**
- Consumes: `CheckoutService._is_salad_order_item(item)` (checkout_service.py:511), `_is_salad_cart_item(item)` (:527).
- Produces: `LoyaltyService.order_item_qualifies(store, item) -> bool` e `LoyaltyService.cart_item_qualifies(store, item) -> bool`. Config nova: `store.metadata['loyalty_qualifying_categories']: list[str]` (vazia/ausente = heurística legada de "salada").

- [ ] **Step 1: Escrever os testes que falham**

```python
# apps/stores/tests/test_loyalty_qualifying.py
from types import SimpleNamespace
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store
from apps.stores.services.loyalty_service import LoyaltyService

User = get_user_model()


def _item(category_id=None, product_name=''):
    product = SimpleNamespace(category_id=category_id)
    return SimpleNamespace(
        product=product, product_name=product_name, variant_name='',
        options={}, quantity=1,
    )


class LoyaltyQualifyingTest(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='dono', password='x')
        self.store = Store.objects.create(name='Loja', slug='loja-q', owner=owner, status='active')

    def test_sem_config_usa_heuristica_salada(self):
        assert LoyaltyService.order_item_qualifies(self.store, _item(product_name='Salada Caesar')) is True
        assert LoyaltyService.order_item_qualifies(self.store, _item(product_name='Suco de Uva')) is False

    def test_com_config_categoria_listada_qualifica(self):
        self.store.metadata = {'loyalty_qualifying_categories': ['cat-1']}
        self.store.save(update_fields=['metadata'])
        assert LoyaltyService.order_item_qualifies(self.store, _item(category_id='cat-1', product_name='Suco de Uva')) is True

    def test_com_config_categoria_fora_nao_qualifica_mesmo_sendo_salada(self):
        self.store.metadata = {'loyalty_qualifying_categories': ['cat-1']}
        self.store.save(update_fields=['metadata'])
        assert LoyaltyService.order_item_qualifies(self.store, _item(category_id='cat-2', product_name='Salada Caesar')) is False
```

- [ ] **Step 2: Rodar e ver falhar**

Teste específico (o script `server2-test.sh` ignora args — use o docker direto):
```bash
docker run --rm --network sdd_test_net \
  -e DATABASE_URL=postgres://test:test@pastita_test_db:5432/test \
  -e DJANGO_SETTINGS_MODULE=config.settings.development -e DISABLE_SERVER_SIDE_CURSORS=1 \
  --entrypoint python -v /home/graco/WORK/server2:/app -w /app pastita_backend:latest \
  manage.py test apps.stores.tests.test_loyalty_qualifying --settings=config.settings.development --keepdb -v1
```
(Se a rede/DB não existirem, rode `bash /home/graco/WORK/scripts/server2-test.sh` uma vez antes para criá-los.)
Expected: FAIL — `AttributeError: ... has no attribute 'order_item_qualifies'`.

- [ ] **Step 3: Implementar em `loyalty_service.py`**

Adicionar à classe `LoyaltyService`:

```python
    @staticmethod
    def _qualifying_categories(store):
        cats = (store.metadata or {}).get('loyalty_qualifying_categories') or []
        return {str(c) for c in cats}

    @staticmethod
    def _item_category_id(item):
        cat = getattr(item, 'category_id', None)
        if cat:
            return cat
        product = getattr(item, 'product', None)
        return getattr(product, 'category_id', None)

    @staticmethod
    def order_item_qualifies(store, item) -> bool:
        from apps.stores.services.checkout_service import CheckoutService
        cats = LoyaltyService._qualifying_categories(store)
        if cats:
            return str(LoyaltyService._item_category_id(item)) in cats
        return CheckoutService._is_salad_order_item(item)

    @staticmethod
    def cart_item_qualifies(store, item) -> bool:
        from apps.stores.services.checkout_service import CheckoutService
        cats = LoyaltyService._qualifying_categories(store)
        if cats:
            return str(LoyaltyService._item_category_id(item)) in cats
        return CheckoutService._is_salad_cart_item(item)
```

- [ ] **Step 4: Trocar os call sites**

Em `order_service.py:178-192`, trocar `CheckoutService._is_salad_order_item(item)` por `LoyaltyService.order_item_qualifies(order.store, item)` (manter o resto igual; import de `CheckoutService` pode sair se ficar sem uso).

Em `checkout_service.py`, dentro de `_cart_salad_discount` (linha 645), trocar o uso de `_is_salad_cart_item(item)` por `LoyaltyService.cart_item_qualifies(cart.store, item)` — o cart tem FK `store`; se o atributo no método for outro (ex. `store` vem por parâmetro), passar o mesmo objeto usado no restante do método. Import local dentro do método para evitar ciclo:
```python
from apps.stores.services.loyalty_service import LoyaltyService
```

- [ ] **Step 5: Rodar o teste específico (PASS) e a suíte completa**

```bash
bash /home/graco/WORK/scripts/server2-test.sh
```
Expected: testes novos PASS, zero falha nova vs baseline.

- [ ] **Step 6: Commit**

```bash
cd /home/graco/WORK/server2 && git add -A && git commit -m "feat(fidelidade): qualificação configurável por categoria via store.metadata"
```

---

### Task 2: server2 — `is_featured` no cupom + plano `coupon_banner`

**Files:**
- Modify: `apps/stores/models/coupon.py` (+ migration nova)
- Modify: `apps/stores/api/serializers.py:1598` (`StoreCouponSerializer.Meta.fields`) e `:1661` (`StoreCouponCreateSerializer.Meta.fields`)
- Modify: `apps/stores/billing.py` (`PLAN_CATALOG`)
- Test: `apps/stores/tests/test_featured_coupon.py`

**Interfaces:**
- Produces: `StoreCoupon.is_featured: BooleanField(default=False)`; `billing.plan_allows(store, 'coupon_banner') -> bool` (False em free/starter, True em pro/premium). Task 3 consome ambos.

- [ ] **Step 1: Teste que falha**

```python
# apps/stores/tests/test_featured_coupon.py
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores import billing
from apps.stores.models import Store, StoreCoupon

User = get_user_model()


class FeaturedCouponModelTest(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='dono2', password='x')
        self.store = Store.objects.create(name='Loja', slug='loja-fc', owner=owner, status='active')

    def test_is_featured_default_false(self):
        c = StoreCoupon.objects.create(
            store=self.store, code='BEMVINDO10',
            discount_type='percentage', discount_value=10,
        )
        assert c.is_featured is False
        c.is_featured = True
        c.save(update_fields=['is_featured'])
        assert StoreCoupon.objects.get(id=c.id).is_featured is True

    def test_plan_gate_coupon_banner(self):
        assert billing.plan_allows('free', 'coupon_banner') is False
        assert billing.plan_allows('starter', 'coupon_banner') is False
        assert billing.plan_allows('pro', 'coupon_banner') is True
        assert billing.plan_allows('premium', 'coupon_banner') is True
```

- [ ] **Step 2: Rodar e ver falhar** (mesmo comando docker da Task 1, módulo `apps.stores.tests.test_featured_coupon`). Expected: FAIL (`is_featured` inexistente / `plan_allows` False≠True).

- [ ] **Step 3: Implementar**

Em `apps/stores/models/coupon.py`, junto dos booleans existentes:
```python
    is_featured = models.BooleanField(default=False, help_text='Exibir como banner no cardápio')
```
Em `apps/stores/billing.py`, adicionar em cada `limits` do `PLAN_CATALOG`: `'coupon_banner': False` (free e starter) / `'coupon_banner': True` (pro e premium).
Nos dois serializers de cupom (`serializers.py:1598` e `:1661`), adicionar `'is_featured'` à lista `fields`.

Gerar migration (container, sem python local):
```bash
docker run --rm --network sdd_test_net \
  -e DATABASE_URL=postgres://test:test@pastita_test_db:5432/test \
  -e DJANGO_SETTINGS_MODULE=config.settings.development \
  --entrypoint python -v /home/graco/WORK/server2:/app -w /app pastita_backend:latest \
  manage.py makemigrations stores
```

- [ ] **Step 4: Rodar teste (PASS) + suíte completa** (`bash /home/graco/WORK/scripts/server2-test.sh`).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(cupom): campo is_featured + gate de plano coupon_banner"
```

---

### Task 3: server2 — `loyalty_program` e `featured_coupon` no app-config do storefront

**Files:**
- Modify: `apps/stores/api/views/storefront_views.py` (view do `app-config/` — localizar com `grep -n "app-config" apps/stores/urls.py` e abrir a view apontada)
- Modify: `apps/public_api/serializers.py:14-38` (`PublicStoreSerializer`, mesmos dois campos, para consistência)
- Test: `apps/stores/tests/test_storefront_loyalty_config.py`

**Interfaces:**
- Consumes: Task 2 (`is_featured`, `coupon_banner`), config de metadata (`loyalty_enabled`, `loyalty_salads_required`).
- Produces: payload do `GET /api/v1/stores/{slug}/app-config/` ganha:
  `loyalty_program: {enabled: bool, threshold: int}` e `featured_coupon: {code, description, discount_type, discount_value, first_order_only} | null`. O front (Tasks 6/8) consome via `useStore()`.

- [ ] **Step 1: Teste que falha**

```python
# apps/stores/tests/test_storefront_loyalty_config.py
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreCoupon

User = get_user_model()


class AppConfigLoyaltyTest(APITestCase):
    def setUp(self):
        owner = User.objects.create_user(username='dono3', password='x')
        self.store = Store.objects.create(
            name='Loja', slug='loja-ac', owner=owner, status='active',
            plan='pro', metadata={'loyalty_enabled': True, 'loyalty_salads_required': 8},
        )
        StoreCoupon.objects.create(
            store=self.store, code='BEMVINDO10', discount_type='percentage',
            discount_value=10, is_active=True, is_featured=True, first_order_only=True,
        )

    def _get(self):
        resp = self.client.get(f'/api/v1/stores/{self.store.slug}/app-config/')
        assert resp.status_code == 200, resp.content
        return resp.json()

    def test_loyalty_program_no_app_config(self):
        data = self._get()
        assert data['loyalty_program'] == {'enabled': True, 'threshold': 8}

    def test_featured_coupon_no_app_config_plano_pro(self):
        data = self._get()
        assert data['featured_coupon']['code'] == 'BEMVINDO10'
        assert data['featured_coupon']['discount_type'] == 'percentage'

    def test_featured_coupon_oculto_em_plano_free(self):
        self.store.plan = 'free'
        self.store.save(update_fields=['plan'])
        assert self._get()['featured_coupon'] is None
```

Nota: se o payload real do app-config for aninhado (ex. `data['store']['...']`), ajustar as asserções para o envelope real na primeira rodada — o requisito é: os dois campos presentes na resposta do app-config.

- [ ] **Step 2: Rodar e ver falhar** (módulo `apps.stores.tests.test_storefront_loyalty_config`). Expected: FAIL com `KeyError: 'loyalty_program'`.

- [ ] **Step 3: Implementar**

Em `storefront_views.py`, módulo-level:

```python
def _loyalty_program_payload(store):
    meta = store.metadata or {}
    return {
        'enabled': bool(meta.get('loyalty_enabled', True)),
        'threshold': max(1, int(meta.get('loyalty_salads_required', 10) or 10)),
    }


def _featured_coupon_payload(store):
    from apps.stores import billing
    from apps.stores.models import StoreCoupon
    if not billing.plan_allows(store, 'coupon_banner'):
        return None
    coupon = (StoreCoupon.objects
              .filter(store=store, is_active=True, is_featured=True)
              .order_by('-created_at').first())
    if not coupon:
        return None
    ok, _reason = coupon.is_valid()
    if not ok:
        return None
    return {
        'code': coupon.code,
        'description': coupon.description,
        'discount_type': coupon.discount_type,
        'discount_value': str(coupon.discount_value),
        'first_order_only': coupon.first_order_only,
    }
```

Na view do app-config, antes do `Response`, injetar no dict de resposta:
```python
payload['loyalty_program'] = _loyalty_program_payload(store)
payload['featured_coupon'] = _featured_coupon_payload(store)
```
Em `PublicStoreSerializer` (public_api/serializers.py), adicionar os dois como `SerializerMethodField` delegando aos mesmos helpers (import de `apps.stores.api.views.storefront_views`) e incluir na lista `fields`.

- [ ] **Step 4: Rodar teste (PASS) + suíte completa.**

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(storefront): loyalty_program e featured_coupon no app-config e API pública"`

---

### Task 4: server2 — Endpoint de contas de fidelidade para o dash

**Files:**
- Modify: `apps/stores/api/views/loyalty_views.py`
- Modify: `apps/stores/urls.py` (após linha 261)
- Test: `apps/stores/tests/test_loyalty_accounts_endpoint.py`

**Interfaces:**
- Produces: `GET /api/v1/stores/{slug}/loyalty/accounts/?page=1` (Token auth; dono da loja ou superuser; 403 caso contrário) →
  `{count, results: [{user_id, display_name, email, qualified_count, redeemed_count, progress, available_rewards, updated_at}]}`. Consumido pela Task 10 (dash).

- [ ] **Step 1: Teste que falha**

```python
# apps/stores/tests/test_loyalty_accounts_endpoint.py
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreLoyaltyAccount

User = get_user_model()


class LoyaltyAccountsEndpointTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono4', password='x')
        self.other = User.objects.create_user(username='intruso', password='x')
        self.customer = User.objects.create_user(
            username='cli1', password='x', email='cli1@x.com', first_name='Ana')
        self.store = Store.objects.create(
            name='Loja', slug='loja-la', owner=self.owner, status='active',
            metadata={'loyalty_salads_required': 10},
        )
        StoreLoyaltyAccount.objects.create(
            store=self.store, user=self.customer, qualified_count=13, redeemed_count=1)
        self.url = f'/api/v1/stores/{self.store.slug}/loyalty/accounts/'

    def test_dono_lista_contas_com_progresso(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.get(self.url)
        assert resp.status_code == 200, resp.content
        data = resp.json()
        assert data['count'] == 1
        row = data['results'][0]
        assert row['qualified_count'] == 13
        assert row['progress'] == 3           # 13 % 10
        assert row['available_rewards'] == 0  # 13//10 - 1
        assert row['display_name'] == 'Ana'

    def test_nao_dono_recebe_403(self):
        self.client.force_authenticate(user=self.other)
        assert self.client.get(self.url).status_code == 403

    def test_anonimo_recebe_401(self):
        assert self.client.get(self.url).status_code == 401
```

- [ ] **Step 2: Rodar e ver falhar** (módulo `apps.stores.tests.test_loyalty_accounts_endpoint`). Expected: FAIL 404 (rota inexistente).

- [ ] **Step 3: Implementar**

Em `loyalty_views.py` (novos imports: `StoreLoyaltyAccount` de `...models`, `LoyaltyService` de `...services.loyalty_service`):

```python
class LoyaltyAccountsView(APIView):
    """Listagem de contas de fidelidade da loja (dash). Dono ou superuser."""
    permission_classes = [IsAuthenticated]

    PAGE_SIZE = 50

    def get(self, request, store_slug):
        store = get_active_store(store_slug)
        if not (request.user.is_superuser or store.owner_id == request.user.id):
            return Response({'error': 'Sem permissão para esta loja.'}, status=403)
        threshold, _enabled = LoyaltyService._config(store)
        qs = (StoreLoyaltyAccount.objects.filter(store=store)
              .select_related('user').order_by('-updated_at'))
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (TypeError, ValueError):
            page = 1
        start = (page - 1) * self.PAGE_SIZE
        results = []
        for acc in qs[start:start + self.PAGE_SIZE]:
            earned = acc.qualified_count // threshold
            results.append({
                'user_id': str(acc.user_id),
                'display_name': acc.user.get_full_name() or acc.user.username,
                'email': acc.user.email,
                'qualified_count': acc.qualified_count,
                'redeemed_count': acc.redeemed_count,
                'progress': acc.qualified_count % threshold,
                'available_rewards': max(0, earned - acc.redeemed_count),
                'updated_at': acc.updated_at.isoformat(),
            })
        return Response({'count': qs.count(), 'results': results})
```

Em `apps/stores/urls.py`, importar `LoyaltyAccountsView` na linha 164 e adicionar após a linha 261:
```python
    path('loyalty/accounts/', LoyaltyAccountsView.as_view(), name='store-loyalty-accounts'),
```

- [ ] **Step 4: Rodar teste (PASS) + suíte completa.**

- [ ] **Step 5: Commit** — `git commit -am "feat(fidelidade): endpoint de listagem de contas para o dash"`

---

### Task 5: server2 — Intent "fidelidade" no bot + linha de fidelidade na mensagem de pago

**Files:**
- Modify: `apps/whatsapp/intents/detector.py` (enum linha 21, `PATTERNS` linha 73, `priority_order` linhas 214-234)
- Create: `apps/whatsapp/intents/handlers/loyalty.py`
- Modify: `apps/whatsapp/intents/handlers/__init__.py:27-54` (`HANDLER_MAP`)
- Modify: `apps/stores/models/order.py:425-452` (`_trigger_status_whatsapp_notification`)
- Test: `apps/whatsapp/tests/test_loyalty_intent.py`, `apps/stores/tests/test_paid_message_loyalty_line.py`

**Interfaces:**
- Consumes: `IntentHandler` base (`handlers/base.py:200` — `__init__(self, account, conversation, company_profile=None)`, atributos `self.store`, `self.conversation`), `LoyaltyService.get_status(store, user)`.
- Produces: `IntentType.LOYALTY_STATUS = "loyalty_status"`; `LoyaltyStatusHandler` que responde o saldo; mensagem de "Pagamento Confirmado" com linha `🥗 …`.

- [ ] **Step 1: Testes que falham**

```python
# apps/whatsapp/tests/test_loyalty_intent.py
from django.test import TestCase

from apps.whatsapp.intents.detector import IntentDetector, IntentType


class LoyaltyIntentDetectionTest(TestCase):
    def test_frases_de_fidelidade_detectadas(self):
        det = IntentDetector()
        for frase in ('quantos pontos eu tenho?', 'meu cartão fidelidade',
                      'quando ganho salada grátis', 'fidelidade'):
            intent = det.detect_regex(frase)
            assert intent == IntentType.LOYALTY_STATUS, f'{frase!r} -> {intent}'
```
Nota: conferir a assinatura real de `detect_regex` (detector.py:214) na primeira rodada — se receber `(self, text, ...)` com mais params obrigatórios, replicar a chamada usada nos testes existentes de intents do app.

```python
# apps/stores/tests/test_paid_message_loyalty_line.py
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store
from apps.stores.services.loyalty_service import LoyaltyService

User = get_user_model()


class PaidMessageLoyaltyLineTest(TestCase):
    def test_linha_de_fidelidade_para_cliente_com_saldo(self):
        owner = User.objects.create_user(username='dono5', password='x')
        cli = User.objects.create_user(username='cli5', password='x')
        store = Store.objects.create(name='L', slug='loja-pm', owner=owner, status='active')
        acc, _ = __import__('apps.stores.models', fromlist=['StoreLoyaltyAccount']).StoreLoyaltyAccount.objects.get_or_create(store=store, user=cli)
        acc.qualified_count = 7
        acc.save(update_fields=['qualified_count'])
        from apps.stores.models.order import build_loyalty_status_line
        line = build_loyalty_status_line(store, cli)
        assert '7/10' in line and 'faltam 3' in line

    def test_linha_com_premio_disponivel(self):
        owner = User.objects.create_user(username='dono6', password='x')
        cli = User.objects.create_user(username='cli6', password='x')
        store = Store.objects.create(name='L', slug='loja-pm2', owner=owner, status='active')
        from apps.stores.models import StoreLoyaltyAccount
        StoreLoyaltyAccount.objects.create(store=store, user=cli, qualified_count=10, redeemed_count=0)
        from apps.stores.models.order import build_loyalty_status_line
        assert 'grátis' in build_loyalty_status_line(store, cli)
```
(Trocar o import feio do primeiro teste por `from apps.stores.models import StoreLoyaltyAccount` — está aqui só ilustrando; escrever o teste já com o import limpo no topo.)

- [ ] **Step 2: Rodar e ver falhar.** Expected: FAIL (`LOYALTY_STATUS` inexistente; `build_loyalty_status_line` inexistente).

- [ ] **Step 3: Implementar detector + handler**

`detector.py`: adicionar ao enum `LOYALTY_STATUS = "loyalty_status"`; em `PATTERNS`, junto das entradas regex existentes (mesmo formato delas):
```python
    IntentType.LOYALTY_STATUS: [
        r'\b(fidelidade|meus?\s+pontos?|cart[aã]o\s+fidelidade|salada\s+gr[aá]tis|meu\s+saldo)\b',
    ],
```
E inserir `IntentType.LOYALTY_STATUS` no `priority_order` (linhas 214-234) **antes** das intents genéricas de info/fallback.

`handlers/loyalty.py`:
```python
from apps.stores.models import StoreOrder
from apps.stores.services.loyalty_service import LoyaltyService

from .base import IntentHandler


class LoyaltyStatusHandler(IntentHandler):
    """Responde saldo do cartão fidelidade dentro da janela (custo zero)."""

    def _resolve_user(self):
        phone = getattr(self.conversation, 'contact_phone', None) or \
            getattr(self.conversation, 'phone_number', None)
        if not phone:
            return None
        order = (StoreOrder.objects
                 .filter(store=self.store, customer_phone=phone, customer__isnull=False)
                 .order_by('-created_at').first())
        return order.customer if order else None

    def handle(self, message_text: str) -> dict:
        user = self._resolve_user()
        status = LoyaltyService.get_status(self.store, user) if user else None
        if not status or not status.get('enabled'):
            text = ('Nosso cartão fidelidade conta seus pedidos pagos no site! '
                    'Peça pelo cardápio para começar a juntar. 🥗')
        elif status['available_rewards'] > 0:
            text = (f"🎉 Você tem {status['available_rewards']} salada(s) grátis para resgatar! "
                    f"É só marcar o resgate no checkout do site.")
        else:
            text = (f"🥗 Cartão fidelidade: {status['progress']}/{status['threshold']} — "
                    f"faltam {status['remaining']} para a próxima grátis!")
        return self.reply_text(text)
```
Nota de adaptação (verificar em `handlers/base.py` e num handler existente, ex. `info.py`): o nome do atributo de telefone da conversa e o método de resposta (`reply_text` vs retorno de dict) devem seguir o padrão dos handlers vizinhos — copiar a forma de retorno de `info.py`.

`handlers/__init__.py`: importar e registrar `IntentType.LOYALTY_STATUS: LoyaltyStatusHandler` no `HANDLER_MAP`.

- [ ] **Step 4: Implementar linha na mensagem de pago**

Em `apps/stores/models/order.py`, módulo-level (perto de `_trigger_status_whatsapp_notification`):

```python
def build_loyalty_status_line(store, user):
    """Linha de fidelidade anexada à mensagem de pagamento confirmado ('' se n/a)."""
    if not user:
        return ''
    from apps.stores.services.loyalty_service import LoyaltyService
    status = LoyaltyService.get_status(store, user)
    if not status.get('enabled'):
        return ''
    if status['available_rewards'] > 0:
        return f"\n\n🥗 Você tem {status['available_rewards']} salada(s) grátis para resgatar!"
    if status['qualified_salads'] > 0:
        return (f"\n\n🥗 Cartão fidelidade: {status['progress']}/{status['threshold']} — "
                f"faltam {status['remaining']} para a próxima grátis!")
    return ''
```

Em `_trigger_status_whatsapp_notification` (linhas 425-452), após resolver o texto do `default_message_map`/override, para `status == 'paid'`:
```python
        if new_status == 'paid':
            message += build_loyalty_status_line(self.store, self.customer if self.customer_id else None)
```
(usar os nomes de variáveis reais do método — o texto final que segue para envio.)

- [ ] **Step 5: Rodar testes novos (PASS) + suíte completa.**

- [ ] **Step 6: Commit** — `git commit -am "feat(bot): intent de saldo fidelidade + linha de progresso na confirmação de pagamento"`

---

### Task 6: cardapidex-web — service + hook + util de fidelidade

**Files:**
- Modify: `src/services/storeApi.js` (perto de `validateCoupon`, ~linha 582)
- Create: `src/hooks/useLoyalty.js`, `src/utils/loyalty.js`
- Test: `src/utils/__tests__/loyalty.test.js`, `src/hooks/__tests__/useLoyalty.test.js`

**Interfaces:**
- Consumes: `storeApi` (axios instance com slug na baseURL + Token), `useAuth()` (`isAuthenticated`).
- Produces: `getLoyaltyStatus(): Promise<LoyaltyStatus>`; `useLoyalty() -> {loyalty, loading, refresh}` (loyalty=null se deslogado/erro); `estimateLoyaltyDiscount(cartItems) -> number` (menor preço unitário entre itens com 'salada'/'salad' no nome; 0 se nenhum). Consumidos pelas Tasks 7-9.

- [ ] **Step 1: Testes que falham**

```js
// src/utils/__tests__/loyalty.test.js
import { describe, expect, it } from 'vitest';
import { estimateLoyaltyDiscount } from '../loyalty';

describe('estimateLoyaltyDiscount', () => {
  it('retorna o menor preço unitário entre saladas', () => {
    const items = [
      { name: 'Salada Caesar', price: 32.9, quantity: 1 },
      { product_name: 'Salada Tropical', price: 27.5, quantity: 2 },
      { name: 'Suco de Uva', price: 12, quantity: 1 },
    ];
    expect(estimateLoyaltyDiscount(items)).toBe(27.5);
  });

  it('retorna 0 sem itens qualificados', () => {
    expect(estimateLoyaltyDiscount([{ name: 'Suco', price: 12 }])).toBe(0);
    expect(estimateLoyaltyDiscount([])).toBe(0);
  });
});
```

```js
// src/hooks/__tests__/useLoyalty.test.js
import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../services/storeApi', () => ({
  getLoyaltyStatus: vi.fn().mockResolvedValue({
    enabled: true, threshold: 10, progress: 7, remaining: 3,
    available_rewards: 0, can_redeem: false, qualified_salads: 7,
  }),
}));
vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({ isAuthenticated: true }),
}));

import useLoyalty from '../useLoyalty';

describe('useLoyalty', () => {
  it('carrega status quando autenticado', async () => {
    const { result } = renderHook(() => useLoyalty());
    await waitFor(() => expect(result.current.loyalty).not.toBeNull());
    expect(result.current.loyalty.progress).toBe(7);
  });
});
```

- [ ] **Step 2: Rodar `npm test` e ver os 2 arquivos falharem** (módulos inexistentes).

- [ ] **Step 3: Implementar**

`src/services/storeApi.js` (junto de `validateCoupon`):
```js
export const getLoyaltyStatus = async () => (await storeApi.get('/loyalty/')).data;
```

`src/utils/loyalty.js`:
```js
const isSaladName = (name) => /salad/i.test(name || '') || /salada/i.test(name || '');

export const estimateLoyaltyDiscount = (cartItems = []) => {
  const prices = cartItems
    .filter((item) => isSaladName(item.name || item.product_name))
    .map((item) => Number(item.price) || 0)
    .filter((p) => p > 0);
  return prices.length ? Math.min(...prices) : 0;
};
```

`src/hooks/useLoyalty.js`:
```js
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { getLoyaltyStatus } from '../services/storeApi';

export default function useLoyalty() {
  const { isAuthenticated } = useAuth();
  const [loyalty, setLoyalty] = useState(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!isAuthenticated) { setLoyalty(null); return; }
    setLoading(true);
    try { setLoyalty(await getLoyaltyStatus()); }
    catch { setLoyalty(null); }
    finally { setLoading(false); }
  }, [isAuthenticated]);

  useEffect(() => { refresh(); }, [refresh]);
  return { loyalty, loading, refresh };
}
```

- [ ] **Step 4: `npm test` — os novos PASS, suíte inteira verde.**

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(fidelidade): service getLoyaltyStatus, hook useLoyalty e estimativa de desconto"`

---

### Task 7: cardapidex-web — Cartão de progresso (cardápio + sacola)

**Files:**
- Create: `src/components/LoyaltyProgressCard.jsx`, `src/components/LoyaltyProgressCard.css`
- Modify: `src/components/CartSidebar.jsx` (acima do bloco de totais), `src/pages/Cardapio.jsx` (abaixo do header, perto do `.reorder-banner` l.578-588), `pages/_app.js` (import do CSS)
- Test: `src/components/__tests__/LoyaltyProgressCard.test.jsx`

**Interfaces:**
- Consumes: `useLoyalty()`, `useAuth()`, `useStore()` (`store.loyalty_program` da Task 3).
- Produces: `<LoyaltyProgressCard compact? />` — logado: barra "X/N — faltam Y"; prêmio: "salada grátis disponível"; deslogado com programa ativo: teaser "Entre e junte saladas"; programa off/sem dados: `null`.

- [ ] **Step 1: Teste que falha**

```jsx
// src/components/__tests__/LoyaltyProgressCard.test.jsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const mockLoyalty = vi.fn();
const mockAuth = vi.fn();
const mockStore = vi.fn();
vi.mock('../../hooks/useLoyalty', () => ({ default: () => mockLoyalty() }));
vi.mock('../../context/AuthContext', () => ({ useAuth: () => mockAuth() }));
vi.mock('../../context/StoreContext', () => ({ useStore: () => mockStore() }));

import LoyaltyProgressCard from '../LoyaltyProgressCard';

const program = { enabled: true, threshold: 10 };

describe('LoyaltyProgressCard', () => {
  it('mostra progresso para cliente logado', () => {
    mockAuth.mockReturnValue({ isAuthenticated: true });
    mockStore.mockReturnValue({ store: { loyalty_program: program } });
    mockLoyalty.mockReturnValue({ loyalty: { enabled: true, threshold: 10, progress: 7, remaining: 3, available_rewards: 0 }, loading: false });
    render(<LoyaltyProgressCard />);
    expect(screen.getByText(/7\/10/)).toBeInTheDocument();
    expect(screen.getByText(/faltam 3/i)).toBeInTheDocument();
  });

  it('mostra prêmio disponível', () => {
    mockAuth.mockReturnValue({ isAuthenticated: true });
    mockStore.mockReturnValue({ store: { loyalty_program: program } });
    mockLoyalty.mockReturnValue({ loyalty: { enabled: true, threshold: 10, progress: 0, remaining: 10, available_rewards: 1 }, loading: false });
    render(<LoyaltyProgressCard />);
    expect(screen.getByText(/grátis/i)).toBeInTheDocument();
  });

  it('teaser para deslogado com programa ativo', () => {
    mockAuth.mockReturnValue({ isAuthenticated: false });
    mockStore.mockReturnValue({ store: { loyalty_program: program } });
    mockLoyalty.mockReturnValue({ loyalty: null, loading: false });
    render(<LoyaltyProgressCard />);
    expect(screen.getByText(/entre/i)).toBeInTheDocument();
  });

  it('não renderiza com programa desativado', () => {
    mockAuth.mockReturnValue({ isAuthenticated: false });
    mockStore.mockReturnValue({ store: { loyalty_program: { enabled: false, threshold: 10 } } });
    mockLoyalty.mockReturnValue({ loyalty: null, loading: false });
    const { container } = render(<LoyaltyProgressCard />);
    expect(container.firstChild).toBeNull();
  });
});
```

- [ ] **Step 2: `npm test` — FAIL (componente inexistente).**

- [ ] **Step 3: Implementar componente**

```jsx
// src/components/LoyaltyProgressCard.jsx
import { useAuth } from '../context/AuthContext';
import { useStore } from '../context/StoreContext';
import useLoyalty from '../hooks/useLoyalty';

export default function LoyaltyProgressCard({ compact = false }) {
  const { isAuthenticated } = useAuth();
  const { store } = useStore();
  const { loyalty } = useLoyalty();

  const program = store?.loyalty_program;
  if (!program?.enabled) return null;

  if (!isAuthenticated) {
    return (
      <div className={`loyalty-card ${compact ? 'loyalty-card--compact' : ''}`}>
        <span className="loyalty-card__emoji" aria-hidden>🥗</span>
        <p className="loyalty-card__text">
          Entre na sua conta e junte saladas — a {program.threshold}ª é <strong>grátis</strong>!
        </p>
      </div>
    );
  }
  if (!loyalty?.enabled) return null;

  const { progress, threshold, remaining, available_rewards: rewards } = loyalty;
  const pct = Math.min(100, Math.round((progress / (threshold || 1)) * 100));

  return (
    <div className={`loyalty-card ${compact ? 'loyalty-card--compact' : ''}`}>
      <span className="loyalty-card__emoji" aria-hidden>🥗</span>
      <div className="loyalty-card__body">
        {rewards > 0 ? (
          <p className="loyalty-card__text">
            <strong>Você tem {rewards} salada{rewards > 1 ? 's' : ''} grátis!</strong> Resgate no checkout 🎉
          </p>
        ) : (
          <>
            <p className="loyalty-card__text">
              Cartão fidelidade: <strong>{progress}/{threshold}</strong> — faltam {remaining}!
            </p>
            <div className="loyalty-card__track" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={threshold}>
              <div className="loyalty-card__fill" style={{ width: `${pct}%` }} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
```

```css
/* src/components/LoyaltyProgressCard.css — só tokens do tema */
.loyalty-card {
  display: flex; align-items: center; gap: 0.75rem;
  padding: 0.75rem 1rem; margin: 0.75rem 0;
  border-radius: var(--radius-md, 12px);
  background: rgba(var(--color-primary-rgb), 0.08);
  border: 1px solid rgba(var(--color-primary-rgb), 0.25);
  color: var(--color-text);
}
.loyalty-card--compact { padding: 0.5rem 0.75rem; margin: 0.5rem 0; }
.loyalty-card__emoji { font-size: 1.5rem; }
.loyalty-card__body { flex: 1; min-width: 0; }
.loyalty-card__text { margin: 0 0 0.35rem; font-size: 0.875rem; }
.loyalty-card__text strong { color: var(--color-primary); }
.loyalty-card__track {
  height: 8px; border-radius: 999px; overflow: hidden;
  background: rgba(var(--color-primary-rgb), 0.15);
}
.loyalty-card__fill {
  height: 100%; border-radius: 999px;
  background: var(--color-primary); transition: width 0.4s ease;
}
```

- [ ] **Step 4: Montar nas superfícies**

`pages/_app.js`: `import '../src/components/LoyaltyProgressCard.css';` (junto dos demais imports de CSS de componente).
`src/components/CartSidebar.jsx`: `<LoyaltyProgressCard compact />` imediatamente acima do bloco de cupom/totais (linhas ~285).
`src/pages/Cardapio.jsx`: `<LoyaltyProgressCard />` logo após o bloco do `.reorder-banner` (l.588).

- [ ] **Step 5: `npm test` verde; commit** — `git commit -am "feat(fidelidade): cartão de progresso no cardápio e na sacola"`

---

### Task 8: cardapidex-web — Resgate no checkout

**Files:**
- Modify: `src/components/checkout/OrderConfirmation.jsx` (bloco novo abaixo do `<CouponInput />`), `src/pages/CheckoutPage.jsx` (estado + payload + stepper), `src/styles/CheckoutModal.module.css` (classe `.loyaltyRow`)
- Test: `src/components/checkout/__tests__/OrderConfirmation.loyalty.test.jsx`

**Interfaces:**
- Consumes: `useLoyalty()` (can_redeem), `estimateLoyaltyDiscount` (Task 6); backend já aceita `use_loyalty_reward: true` no POST do checkout (`storefront_views.py:902-913`) e aplica o desconto da salada mais barata server-side.
- Produces: props novas de `OrderConfirmation`: `loyalty` (objeto status ou null), `useLoyaltyReward` (bool), `onToggleLoyaltyReward` (fn), `loyaltyDiscount` (number estimado). Payload do pedido ganha `use_loyalty_reward`.

- [ ] **Step 1: Teste que falha**

```jsx
// src/components/checkout/__tests__/OrderConfirmation.loyalty.test.jsx
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import OrderConfirmation from '../OrderConfirmation';

// Reusar o setup de props do teste existente OrderConfirmation.discount.test.jsx
// (copiar o bloco de mocks/props base de lá) e acrescentar:
const loyaltyProps = {
  loyalty: { enabled: true, can_redeem: true, available_rewards: 1, threshold: 10 },
  useLoyaltyReward: false,
  onToggleLoyaltyReward: vi.fn(),
  loyaltyDiscount: 27.5,
};

describe('OrderConfirmation — resgate de fidelidade', () => {
  it('mostra oferta de resgate quando can_redeem', () => {
    render(<OrderConfirmation {...baseProps} {...loyaltyProps} />);
    expect(screen.getByText(/salada grátis/i)).toBeInTheDocument();
  });

  it('chama onToggleLoyaltyReward ao marcar', () => {
    render(<OrderConfirmation {...baseProps} {...loyaltyProps} />);
    fireEvent.click(screen.getByRole('checkbox', { name: /usar minha salada grátis/i }));
    expect(loyaltyProps.onToggleLoyaltyReward).toHaveBeenCalled();
  });

  it('mostra linha de desconto quando marcado', () => {
    render(<OrderConfirmation {...baseProps} {...loyaltyProps} useLoyaltyReward />);
    expect(screen.getByText(/fidelidade/i)).toBeInTheDocument();
    expect(screen.getByText(/27,50|27\.50/)).toBeInTheDocument();
  });

  it('não mostra nada sem can_redeem', () => {
    render(<OrderConfirmation {...baseProps} {...loyaltyProps} loyalty={{ enabled: true, can_redeem: false }} />);
    expect(screen.queryByText(/salada grátis/i)).not.toBeInTheDocument();
  });
});
```
(`baseProps` = o mesmo conjunto mínimo de props que `OrderConfirmation.discount.test.jsx` usa — copiar de lá, é a fonte canônica.)

- [ ] **Step 2: `npm test` — FAIL.**

- [ ] **Step 3: Implementar em `OrderConfirmation.jsx`**

Novas props com defaults (`loyalty = null, useLoyaltyReward = false, onToggleLoyaltyReward = () => {}, loyaltyDiscount = 0`). Abaixo do `<CouponInput />`:

```jsx
{loyalty?.can_redeem && (
  <label className={styles.loyaltyRow}>
    <input
      type="checkbox"
      checked={useLoyaltyReward}
      onChange={onToggleLoyaltyReward}
      aria-label="Usar minha salada grátis"
    />
    <span>
      🥗 <strong>Você tem {loyalty.available_rewards} salada{loyalty.available_rewards > 1 ? 's' : ''} grátis!</strong>{' '}
      Usar minha salada grátis neste pedido
    </span>
  </label>
)}
```

Na área de totais (junto do `discountRow` l.238-241), quando `useLoyaltyReward && loyaltyDiscount > 0`, adicionar linha "Fidelidade (salada grátis)" com `-R$ {loyaltyDiscount}` no mesmo formato monetário das outras linhas, e incluir `loyaltyDiscount` na conta do `total` exibido: `Math.max(0, numericCartTotal + shippingCost - numericDiscount - (useLoyaltyReward ? loyaltyDiscount : 0))`.

`CheckoutModal.module.css`:
```css
.loyaltyRow {
  display: flex; gap: 0.5rem; align-items: flex-start;
  padding: 0.75rem; margin: 0.75rem 0;
  border-radius: 8px;
  background: rgba(var(--color-primary-rgb), 0.08);
  border: 1px dashed var(--color-primary);
  cursor: pointer; font-size: 0.875rem;
}
```

- [ ] **Step 4: Ligar no `CheckoutPage.jsx`**

- `const { loyalty, refresh: refreshLoyalty } = useLoyalty();` e `const [useLoyaltyReward, setUseLoyaltyReward] = useState(false);`
- `const loyaltyDiscount = useLoyaltyReward ? estimateLoyaltyDiscount(cartItems) : 0;` (usar a mesma variável de itens do carrinho que a página já usa para o Meta Pixel/total).
- Passar as 4 props novas para `<OrderConfirmation ... />`.
- No payload do pedido (junto de `coupon_code`, l.612): `use_loyalty_reward: useLoyaltyReward,`
- Ativar o passo "Fidelidade" do stepper que hoje é decorativo: `const stepIndex = currentStep === 'order' ? (loyalty?.can_redeem ? 1 : 0) : 2;` — manter `checkoutSteps` como está.
- Após pedido criado com sucesso, chamar `refreshLoyalty()`.

- [ ] **Step 5: `npm test` verde; commit** — `git commit -am "feat(fidelidade): resgate de salada grátis no checkout (use_loyalty_reward)"`

---

### Task 9: cardapidex-web — Banner de cupom destaque

**Files:**
- Create: `src/components/CouponBanner.jsx`, `src/components/CouponBanner.css`
- Modify: `src/pages/Cardapio.jsx` (topo, acima do conteúdo, padrão `StoreClosedBanner`), `pages/_app.js` (CSS)
- Test: `src/components/__tests__/CouponBanner.test.jsx`

**Interfaces:**
- Consumes: `useStore()` → `store.featured_coupon` (Task 3): `{code, description, discount_type, discount_value, first_order_only}`.
- Produces: banner dismissível por sessão (`sessionStorage['cardapidex_coupon_banner_dismissed:{code}']`), com botão "copiar código" (`navigator.clipboard.writeText`).

- [ ] **Step 1: Teste que falha**

```jsx
// src/components/__tests__/CouponBanner.test.jsx
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockStore = vi.fn();
vi.mock('../../context/StoreContext', () => ({ useStore: () => mockStore() }));

import CouponBanner from '../CouponBanner';

const coupon = { code: 'BEMVINDO10', description: '', discount_type: 'percentage', discount_value: '10.00', first_order_only: true };

describe('CouponBanner', () => {
  beforeEach(() => sessionStorage.clear());

  it('mostra código e desconto', () => {
    mockStore.mockReturnValue({ store: { featured_coupon: coupon } });
    render(<CouponBanner />);
    expect(screen.getByText(/BEMVINDO10/)).toBeInTheDocument();
    expect(screen.getByText(/10%/)).toBeInTheDocument();
    expect(screen.getByText(/primeiro pedido/i)).toBeInTheDocument();
  });

  it('não renderiza sem featured_coupon', () => {
    mockStore.mockReturnValue({ store: { featured_coupon: null } });
    const { container } = render(<CouponBanner />);
    expect(container.firstChild).toBeNull();
  });

  it('fechar persiste na sessão', () => {
    mockStore.mockReturnValue({ store: { featured_coupon: coupon } });
    const { unmount } = render(<CouponBanner />);
    fireEvent.click(screen.getByRole('button', { name: /fechar/i }));
    unmount();
    const { container } = render(<CouponBanner />);
    expect(container.firstChild).toBeNull();
  });
});
```

- [ ] **Step 2: `npm test` — FAIL.**

- [ ] **Step 3: Implementar**

```jsx
// src/components/CouponBanner.jsx
import { useState } from 'react';
import { useStore } from '../context/StoreContext';

const dismissKey = (code) => `cardapidex_coupon_banner_dismissed:${code}`;

export default function CouponBanner() {
  const { store } = useStore();
  const coupon = store?.featured_coupon;
  const [dismissed, setDismissed] = useState(() =>
    coupon ? sessionStorage.getItem(dismissKey(coupon.code)) === '1' : false);
  const [copied, setCopied] = useState(false);

  if (!coupon || dismissed) return null;

  const valueLabel = coupon.discount_type === 'percentage'
    ? `${parseFloat(coupon.discount_value)}%`
    : `R$ ${parseFloat(coupon.discount_value).toFixed(2).replace('.', ',')}`;

  const copy = async () => {
    try { await navigator.clipboard.writeText(coupon.code); setCopied(true); } catch { /* noop */ }
  };
  const close = () => {
    sessionStorage.setItem(dismissKey(coupon.code), '1');
    setDismissed(true);
  };

  return (
    <div className="coupon-banner" role="status">
      <span aria-hidden>🏷️</span>
      <p className="coupon-banner__text">
        {coupon.first_order_only ? 'Primeiro pedido? ' : ''}
        Use <button type="button" className="coupon-banner__code" onClick={copy}>{coupon.code}</button>{' '}
        e ganhe <strong>{valueLabel} off</strong>{copied ? ' — copiado!' : ''}
      </p>
      <button type="button" className="coupon-banner__close" aria-label="Fechar" onClick={close}>×</button>
    </div>
  );
}
```

```css
/* src/components/CouponBanner.css */
.coupon-banner {
  display: flex; align-items: center; gap: 0.5rem;
  padding: 0.6rem 1rem;
  background: var(--color-primary); color: var(--color-primary-text, #fff);
  font-size: 0.875rem;
}
.coupon-banner__text { margin: 0; flex: 1; }
.coupon-banner__code {
  font-weight: 700; letter-spacing: 0.05em; cursor: pointer;
  background: rgba(255, 255, 255, 0.2); color: inherit;
  border: 1px dashed currentColor; border-radius: 4px; padding: 0 0.4rem;
}
.coupon-banner__close {
  background: none; border: none; color: inherit;
  font-size: 1.25rem; line-height: 1; cursor: pointer; padding: 0 0.25rem;
}
```

Montar em `Cardapio.jsx` no topo do JSX da página (acima do header/conteúdo, mesmo nível do `StoreClosedBanner` se presente) e importar o CSS em `_app.js`.

- [ ] **Step 4: `npm test` verde; commit** — `git commit -am "feat(cupom): banner de cupom destaque no cardápio"`

---

### Task 10: pastita-dash — service de fidelidade + tipo do cupom

**Files:**
- Create: `src/services/loyalty.ts`
- Modify: `src/services/coupons.ts` (interface `Coupon` e `CreateCoupon`: `is_featured?: boolean`), `src/services/index.ts` (export)
- Test: `src/services/__tests__/loyalty.test.ts`

**Interfaces:**
- Consumes: `api` (axios base com Token), endpoint da Task 4.
- Produces:
```ts
export interface LoyaltyAccountRow {
  user_id: string; display_name: string; email: string;
  qualified_count: number; redeemed_count: number;
  progress: number; available_rewards: number; updated_at: string;
}
export interface LoyaltyAccountsResponse { count: number; results: LoyaltyAccountRow[]; }
loyaltyService.getAccounts(storeSlug: string, page?: number): Promise<LoyaltyAccountsResponse>
```

- [ ] **Step 1: Teste que falha**

```ts
// src/services/__tests__/loyalty.test.ts
jest.mock('../api', () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));
import api from '../api';
import { loyaltyService } from '../loyalty';

describe('loyaltyService', () => {
  it('busca contas com slug e página', async () => {
    (api.get as jest.Mock).mockResolvedValue({ data: { count: 0, results: [] } });
    const data = await loyaltyService.getAccounts('ce-saladas', 2);
    expect(api.get).toHaveBeenCalledWith('/stores/ce-saladas/loyalty/accounts/', { params: { page: 2 } });
    expect(data.count).toBe(0);
  });
});
```

- [ ] **Step 2: `npm test -- loyalty` — FAIL.**

- [ ] **Step 3: Implementar**

```ts
// src/services/loyalty.ts
import api from './api';

export interface LoyaltyAccountRow {
  user_id: string;
  display_name: string;
  email: string;
  qualified_count: number;
  redeemed_count: number;
  progress: number;
  available_rewards: number;
  updated_at: string;
}

export interface LoyaltyAccountsResponse {
  count: number;
  results: LoyaltyAccountRow[];
}

class LoyaltyService {
  async getAccounts(storeSlug: string, page = 1): Promise<LoyaltyAccountsResponse> {
    const { data } = await api.get(`/stores/${storeSlug}/loyalty/accounts/`, { params: { page } });
    return data;
  }
}

export const loyaltyService = new LoyaltyService();
export default loyaltyService;
```
Em `coupons.ts`, adicionar `is_featured?: boolean` às interfaces `Coupon` e `CreateCoupon`/`UpdateCoupon`. Exportar `loyaltyService` no barril `src/services/index.ts`.

- [ ] **Step 4: `npm test` verde; commit** — `git commit -am "feat(fidelidade): loyaltyService + is_featured no tipo de cupom"`

---

### Task 11: pastita-dash — Página "Fidelidade & Cupons" + rota + navbar

**Files:**
- Create: `src/pages/loyalty/FidelidadePage.tsx`
- Modify: `src/App.tsx` (lazy + rota `stores/:storeId/fidelidade`), `src/components/layout/navSections.tsx` (grupo Cardápio), `src/components/layout/__tests__/navSections.test.tsx`
- Test: `src/pages/loyalty/__tests__/FidelidadePage.test.tsx`

**Interfaces:**
- Consumes: `loyaltyService.getAccounts` (Task 10), `updateStore(id, {metadata})` + `getStores` de `storesApi` (merge obrigatório `{...currentMetadata}`), `couponsService.createCoupon` (Task 10 tipos), componentes `Card, Button, Input, SearchInput, Badge` de `../../components/ui`.
- Produces: página com 3 seções — Configuração do programa, Cupom de boas-vindas 1-clique, Clientes no programa.

- [ ] **Step 1: Teste que falha**

```tsx
// src/pages/loyalty/__tests__/FidelidadePage.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

jest.mock('../../../services/storesApi', () => ({
  getStores: jest.fn(),
  updateStore: jest.fn(),
}));
jest.mock('../../../services/loyalty', () => ({
  loyaltyService: { getAccounts: jest.fn() },
}));
jest.mock('../../../services/coupons', () => ({
  couponsService: { createCoupon: jest.fn() },
}));

import { couponsService } from '../../../services/coupons';
import { loyaltyService } from '../../../services/loyalty';
import { getStores, updateStore } from '../../../services/storesApi';
import FidelidadePage from '../FidelidadePage';

const store = {
  id: 'uuid-1', slug: 'ce-saladas', name: 'Cê Saladas',
  metadata: { loyalty_enabled: true, loyalty_salads_required: 10 },
};
const page = (results: unknown[]) => ({ count: results.length, next: null, previous: null, results });

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={['/stores/ce-saladas/fidelidade']}>
      <Routes>
        <Route path="/stores/:storeId/fidelidade" element={<FidelidadePage />} />
      </Routes>
    </MemoryRouter>
  );

beforeEach(() => {
  jest.clearAllMocks();
  localStorage.clear();
  (getStores as jest.Mock).mockResolvedValue(page([store]));
  (loyaltyService.getAccounts as jest.Mock).mockResolvedValue({
    count: 1,
    results: [{ user_id: 'u1', display_name: 'Ana', email: 'a@x.com', qualified_count: 7, redeemed_count: 0, progress: 7, available_rewards: 0, updated_at: '2026-07-28T00:00:00Z' }],
  });
});

describe('FidelidadePage', () => {
  it('carrega config e lista clientes', async () => {
    renderPage();
    expect(await screen.findByDisplayValue('10')).toBeInTheDocument();
    expect(await screen.findByText('Ana')).toBeInTheDocument();
    expect(screen.getByText(/7\/10/)).toBeInTheDocument();
  });

  it('salva threshold com merge de metadata', async () => {
    (updateStore as jest.Mock).mockResolvedValue(store);
    renderPage();
    const input = await screen.findByLabelText(/itens para ganhar/i);
    await userEvent.clear(input);
    await userEvent.type(input, '8');
    await userEvent.click(screen.getByRole('button', { name: /salvar/i }));
    await waitFor(() => expect(updateStore).toHaveBeenCalledWith('uuid-1', {
      metadata: expect.objectContaining({ loyalty_enabled: true, loyalty_salads_required: 8 }),
    }));
  });

  it('cria cupom de boas-vindas em 1 clique', async () => {
    (couponsService.createCoupon as jest.Mock).mockResolvedValue({ id: 'c1', code: 'BEMVINDO10' });
    renderPage();
    await screen.findByText('Ana');
    await userEvent.click(screen.getByRole('button', { name: /criar cupom de boas-vindas/i }));
    await waitFor(() => expect(couponsService.createCoupon).toHaveBeenCalledWith(
      expect.objectContaining({ code: 'BEMVINDO10', first_order_only: true, is_featured: true, discount_type: 'percentage' })
    ));
  });
});
```

- [ ] **Step 2: `npm test -- FidelidadePage` — FAIL.**

- [ ] **Step 3: Implementar a página**

`src/pages/loyalty/FidelidadePage.tsx` — `export default`; estrutura:

```tsx
import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Badge, Button, Card, Input } from '../../components/ui';
import { couponsService } from '../../services/coupons';
import { loyaltyService, LoyaltyAccountRow } from '../../services/loyalty';
import { getStores, updateStore } from '../../services/storesApi';
```

- Resolver a loja como a `CouponsPage` faz: `getStores()` → `stores.find(s => s.id === routeStoreId || s.slug === routeStoreId)`.
- **Seção "Programa de fidelidade"** (`Card title="Programa de fidelidade"`): toggle "Programa ativo" (checkbox), `Input` numérico com `<label>Itens para ganhar 1 grátis</label>` (id/htmlFor — o teste usa `findByLabelText`), botão "Salvar". Submit:
```tsx
const currentMetadata = (store?.metadata as Record<string, unknown>) || {};
await updateStore(store.id, {
  metadata: { ...currentMetadata, loyalty_enabled: enabled, loyalty_salads_required: Number(threshold) },
});
```
  Campo extra: "Categorias que pontuam (IDs, separados por vírgula — vazio = todas as saladas)" → `loyalty_qualifying_categories` como array de strings no mesmo merge (input texto simples nesta fase; multi-select fica para melhoria).
- **Seção "Cupom de boas-vindas"**: input % (default 10) + botão "Criar cupom de boas-vindas" →
```tsx
await couponsService.createCoupon({
  store: store.id, code: `BEMVINDO${pct}`, description: 'Cupom de boas-vindas',
  discount_type: 'percentage', discount_value: pct,
  first_order_only: true, is_active: true, is_featured: true,
} as never);
```
  (conferir os campos obrigatórios reais de `CreateCoupon` em `coupons.ts` e preencher os que faltarem com defaults vazios). Mostrar `Badge` de sucesso com o código criado e aviso "Banner no cardápio disponível nos planos Pro e Premium".
- **Seção "Clientes no programa"**: tabela `results` de `loyaltyService.getAccounts(slugOuId)` — colunas Nome, E-mail, Progresso (`{progress}/{threshold}`), Resgates, Grátis disponíveis (Badge quando > 0). Paginação simples com botão "Carregar mais" se `count > results.length`.
- Estados de loading (`Skeleton`/`Loading` de `components/common`) e erro (mensagem com `text-fg-muted-token`). Zero cores hardcoded.

- [ ] **Step 4: Rota + navbar**

`App.tsx`: `const FidelidadePage = lazy(() => import('./pages/loyalty/FidelidadePage'));` + rota junto das outras store-scoped:
```tsx
<Route path="stores/:storeId/fidelidade" element={<PageBoundary><FidelidadePage /></PageBoundary>} />
```
`navSections.tsx`, grupo **Cardápio**, após o item Cupons:
```tsx
{ name: 'Fidelidade', href: storeHref('fidelidade'), icon: GiftIcon },
```
(import `GiftIcon` de `@heroicons/react/24/outline`, mesmo pacote dos vizinhos). Atualizar `navSections.test.tsx` se o snapshot/`toEqual` de itens quebrar (o teste de labels compara seções top-level — item novo dentro de Cardápio pode ou não afetar; ajustar conforme a falha real).

- [ ] **Step 5: `npm test` completo verde; commit** — `git commit -am "feat(fidelidade): página Fidelidade & Cupons no dash (config, boas-vindas, clientes)"`

---

### Task 12: Deploy + verificação ao vivo

**Files:** nenhum novo — só deploy e smoke test.

- [ ] **Step 1: server2** — suíte completa verde (`bash /home/graco/WORK/scripts/server2-test.sh`), depois deploy padrão (imagem baked): `cd /home/graco/WORK/server2 && bash deploy.sh` (atenção ao risco de disco: prune build cache antes se necessário). Migration `is_featured` roda no deploy. Pós-deploy: `docker commit` se houver `docker cp` manual (regra da casa).
- [ ] **Step 2: Smoke server2** —
```bash
curl -s https://<api>/api/v1/stores/ce-saladas/app-config/ | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('loyalty_program'), d.get('featured_coupon'))"
```
Expected: `{'enabled': True, 'threshold': 10}` + cupom ou None.
- [ ] **Step 3: cardapidex-web** — `npm test` verde, commit na `master`, `npm run deploy:local` (build staged + swap + healthcheck com rollback automático). Verificar no ce-saladas ao vivo: banner (se cupom destaque criado), cartão de progresso logado, checkbox de resgate com saldo.
- [ ] **Step 4: pastita-dash** — `npm test` verde, push na `main` (Vercel auto-deploy; lembrar: erro TS bloqueia build). Verificar painel.cardapidex.com.br → Cardápio → Fidelidade.
- [ ] **Step 5: Fim a fim no ce-saladas** — no dash, conferir threshold/toggle; criar cupom de boas-vindas de teste; no storefront logado, conferir progresso real de um cliente com histórico (backfill legado roda na primeira leitura). Registrar resultado (prints/observações) e atualizar memória do projeto.

---

## Self-review (executado na escrita)

- **Cobertura da spec:** A1 (Task 7), A2 (Task 8 — backend já existia), A3 (Tasks 2+3+9), B1 (Tasks 10+11, com listagem da Task 4 e qualificação da Task 1), C1+C2 (Task 5), D (Task 2 `coupon_banner` + Task 3 gate; fidelidade visível sem gate = conforme spec). C3/C4/C5 explicitamente adiados (Global Constraints).
- **Tipos consistentes:** `LoyaltyAccountRow` (Tasks 4→10→11), payload `loyalty_program/featured_coupon` (Tasks 3→7→9), props de `OrderConfirmation` (Task 8), `use_loyalty_reward` (nome exato lido do backend em storefront_views.py:906).
- **Pontos de adaptação sinalizados** (não placeholders — instrução concreta de conferir o padrão vizinho): envelope do app-config (Task 3), assinatura de `detect_regex` e forma de retorno dos handlers (Task 5), `baseProps` do teste de OrderConfirmation (Task 8), campos obrigatórios de `CreateCoupon` (Task 11).
