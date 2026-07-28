# Link na Bio — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Página pública tipo Linktree por loja em `bio.cardapidex.com.br/<slug>`, auto-gerada + links customizados editáveis no dash, com contagem de cliques no backend e gates de plano Pro+.

**Architecture:** server2 (Django/DRF) ganha 2 models (`StoreBioLink`, `BioClickStat`), endpoint público de payload + redirect contador em `apps/public_api`, CRUD autenticado em `apps/stores`; cardapidex-web (Next 16, pages router) ganha página standalone SSR `/bio/[slug]` + branch de host no `proxy.js`; pastita-dash ganha página "Link na Bio" (padrão FidelidadePage) com PaywallModal nos 403.

**Tech Stack:** Django 4 + DRF (testes `django.test.TestCase` + `APIClient`), Next.js 16 pages router + Vitest + RTL, React 18 + TS + Jest (dash), Cloudflare Tunnel como edge.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-28-link-na-bio-design.md`. Divergências corrigidas pelo recon (valem estas): rotas públicas são `/api/v1/public/<slug>/bio/` (app `apps/public_api`, não `/api/public/stores/...`); edge é **Cloudflare Tunnel** (não nginx); no Next 16 o middleware chama-se **`proxy.js`** (raiz do repo); web usa **Vitest** (`npm test` = `vitest run`), não jest.
- server2: branch `development` é a ÚNICA; commits em pt-BR; testes SEM python local — rodar dentro de container Docker descartável (imagem `pastita_backend:latest`) com Postgres efêmero (SQLite falha). Comando de referência no fim do plano. Baseline: 1277 pass / 45 falhas conhecidas — zero falha NOVA.
- cardapidex-web: branch `master` única; `npm test` (vitest) baseline 142 pass; build `npm run build`.
- pastita-dash: branch `main` única; `npx jest` baseline 524 pass; `npx tsc --noEmit` limpo.
- Feature keys de plano: `bio_custom_links` e `bio_analytics` — `free`/`starter` = False, `pro`/`premium` = True.
- Link keys estáveis: `auto:menu`, `auto:whatsapp`, `auto:maps`, `auto:instagram`, `custom:<uuid>`, `page:view`.
- Mensagem de upgrade (exata, usada no 403): `'Links personalizados são exclusivos dos planos Pro e Premium. Faça upgrade do plano.'` e `'Estatísticas do Link na Bio são exclusivas dos planos Pro e Premium. Faça upgrade do plano.'`
- URLs base (settings novos, com env override): `STOREFRONT_BASE_URL` default `https://cardapidex.com.br`, `BIO_BASE_URL` default `https://bio.cardapidex.com.br`.
- NUNCA aceitar URL de destino vinda do cliente no redirect (anti open-redirect): key resolve server-side.

---

### Task 1: server2 — Models `StoreBioLink` + `BioClickStat` + migration 0056

**Files:**
- Create: `apps/stores/models/bio.py`
- Modify: `apps/stores/models/__init__.py` (exportar os 2 models)
- Create: `apps/stores/migrations/0056_storebiolink_bioclickstat.py` (via makemigrations)
- Test: `apps/stores/tests/test_bio_models.py`

**Interfaces:**
- Consumes: `Store` (`apps.stores.models.base.Store`).
- Produces: `StoreBioLink(store, title, url, icon, sort_order, is_active, created_at, updated_at)` com pk UUID; `BioClickStat(store, date, link_key, clicks)` unique `(store, date, link_key)`; helper de classe `BioClickStat.bump(store, link_key)` que incrementa atomicamente (get_or_create + `F('clicks') + 1`) e é o ÚNICO caminho de escrita usado pelas views.

- [ ] **Step 1: Write the failing test**

```python
# apps/stores/tests/test_bio_models.py
from django.test import TestCase
from django.utils import timezone

from apps.core.models import User
from apps.stores.models import BioClickStat, Store, StoreBioLink


class BioModelsTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='bio-owner', email='bio-owner@example.com', password='test-pass'
        )
        self.store = Store.objects.create(name='Bio Store', slug='bio-store', owner=self.owner)

    def test_create_bio_link_defaults(self):
        link = StoreBioLink.objects.create(
            store=self.store, title='Pesquisa de satisfação', url='https://forms.gle/abc'
        )
        self.assertTrue(link.is_active)
        self.assertEqual(link.sort_order, 0)
        self.assertEqual(link.icon, '')
        self.assertEqual(str(link), 'Pesquisa de satisfação (bio-store)')

    def test_bio_links_ordered_by_sort_order(self):
        b = StoreBioLink.objects.create(store=self.store, title='B', url='https://b.com', sort_order=2)
        a = StoreBioLink.objects.create(store=self.store, title='A', url='https://a.com', sort_order=1)
        self.assertEqual(list(self.store.bio_links.all()), [a, b])

    def test_bump_creates_and_increments(self):
        BioClickStat.bump(self.store, 'page:view')
        BioClickStat.bump(self.store, 'page:view')
        BioClickStat.bump(self.store, 'auto:menu')
        today = timezone.localdate()
        view_stat = BioClickStat.objects.get(store=self.store, date=today, link_key='page:view')
        menu_stat = BioClickStat.objects.get(store=self.store, date=today, link_key='auto:menu')
        self.assertEqual(view_stat.clicks, 2)
        self.assertEqual(menu_stat.clicks, 1)

    def test_click_stat_unique_per_store_date_key(self):
        today = timezone.localdate()
        BioClickStat.objects.create(store=self.store, date=today, link_key='auto:menu', clicks=1)
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            BioClickStat.objects.create(store=self.store, date=today, link_key='auto:menu', clicks=1)
```

- [ ] **Step 2: Run test to verify it fails**

Expected: ImportError (`StoreBioLink` não existe em `apps.stores.models`).

- [ ] **Step 3: Write minimal implementation**

```python
# apps/stores/models/bio.py
import uuid

from django.db import models
from django.db.models import F
from django.utils import timezone


class StoreBioLink(models.Model):
    """Link customizado da página Link na Bio de uma loja."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='bio_links')
    title = models.CharField(max_length=80)
    url = models.URLField(max_length=500)
    icon = models.CharField(max_length=8, blank=True, default='')
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'created_at']
        indexes = [models.Index(fields=['store', 'is_active'], name='biolink_store_active_idx')]

    def __str__(self):
        return f'{self.title} ({self.store.slug})'


class BioClickStat(models.Model):
    """Agregado diário de views/cliques da página bio. link_key: page:view, auto:*, custom:<uuid>."""

    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='bio_click_stats')
    date = models.DateField()
    link_key = models.CharField(max_length=64)
    clicks = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['store', 'date', 'link_key'], name='bioclick_store_date_key_uniq')
        ]
        indexes = [models.Index(fields=['store', 'date'], name='bioclick_store_date_idx')]

    @classmethod
    def bump(cls, store, link_key):
        obj, _created = cls.objects.get_or_create(
            store=store, date=timezone.localdate(), link_key=link_key, defaults={'clicks': 0}
        )
        cls.objects.filter(pk=obj.pk).update(clicks=F('clicks') + 1)

    def __str__(self):
        return f'{self.store.slug} {self.date} {self.link_key}={self.clicks}'
```

Em `apps/stores/models/__init__.py`, adicionar ao bloco de imports/`__all__` existente (seguir o formato do arquivo):

```python
from .bio import BioClickStat, StoreBioLink
```

IMPORTANTE: antes de escrever `bio.py`, olhe `apps/stores/models/coupon.py` — se `StoreCoupon` usar outro padrão de pk/base class, siga o padrão do repo (o teste não fixa o tipo do pk, só o comportamento).

- [ ] **Step 4: Generate migration**

`python manage.py makemigrations stores` (dentro do container de teste) → deve gerar `0056_...` dependendo de `0055_store_clarity_enabled_store_clarity_id`. Renomear para `0056_storebiolink_bioclickstat.py` se vier com nome automático diferente. Inspecionar: só cria as 2 tabelas, nada de alterar tabelas existentes.

- [ ] **Step 5: Run tests to verify they pass** (`apps.stores.tests.test_bio_models`)

- [ ] **Step 6: Commit** — `feat(bio): models StoreBioLink e BioClickStat + migration 0056`

---

### Task 2: server2 — Gates `bio_custom_links` e `bio_analytics` no PLAN_CATALOG

**Files:**
- Modify: `apps/stores/billing.py` (PLAN_CATALOG, dict `limits` dos 4 planos)
- Test: `apps/stores/tests/test_bio_billing.py`
- Check: `apps/stores/tests/test_billing_catalog.py` (se ele assertar o conjunto exato de chaves de `limits`, atualizar)

**Interfaces:**
- Consumes: `apps.stores.billing.plan_allows(store_or_plan_key, feature)` (já existe, aceita Store ou string; `billing_exempt` → True).
- Produces: `plan_allows(x, 'bio_custom_links')` e `plan_allows(x, 'bio_analytics')` → False p/ `free`/`starter`, True p/ `pro`/`premium`.

- [ ] **Step 1: Write the failing test**

```python
# apps/stores/tests/test_bio_billing.py
from django.test import TestCase

from apps.stores import billing


class BioBillingGatesTest(TestCase):
    def test_bio_gates_per_plan(self):
        for feature in ('bio_custom_links', 'bio_analytics'):
            self.assertFalse(billing.plan_allows('free', feature))
            self.assertFalse(billing.plan_allows('starter', feature))
            self.assertTrue(billing.plan_allows('pro', feature))
            self.assertTrue(billing.plan_allows('premium', feature))
```

- [ ] **Step 2: Run to verify it fails** (feature ausente → plan_allows False nos 4 → falha no caso `pro`)

- [ ] **Step 3: Implement** — em cada plano do `PLAN_CATALOG`, dentro de `limits`, ao lado de `coupon_banner`: `free`/`starter`: `'bio_custom_links': False, 'bio_analytics': False`; `pro`/`premium`: `'bio_custom_links': True, 'bio_analytics': True`.

- [ ] **Step 4: Run** `test_bio_billing` + `test_billing_catalog` (ajustar este se quebrar por chave nova) — PASS.

- [ ] **Step 5: Commit** — `feat(bio): gates bio_custom_links e bio_analytics no catálogo de planos`

---

### Task 3: server2 — Payload público `GET /api/v1/public/<slug>/bio/`

**Files:**
- Create: `apps/public_api/bio.py` (builder do payload, reutilizado pelo redirect na Task 4)
- Modify: `apps/public_api/views.py` (view `public_store_bio`)
- Modify: `apps/public_api/urls.py` (rota `<slug:slug>/bio/`)
- Modify: `config/settings/base.py` (adicionar `STOREFRONT_BASE_URL` e `BIO_BASE_URL` com env override, perto de `BILLING_PANEL_URL`)
- Test: `apps/public_api/tests/test_bio_public.py` (criar `apps/public_api/tests/__init__.py` se não existir; se os testes do app viverem em `apps/public_api/tests.py`, seguir o layout existente)

**Interfaces:**
- Consumes: `Store`, `StoreBioLink`, `BioClickStat.bump`, `billing.plan_allows`, `_get_active_store(slug)` de `apps/public_api/views.py` (get_object_or_404 status='active').
- Produces:
  - `apps.public_api.bio.bio_settings(store) -> dict` (defaults aplicados)
  - `apps.public_api.bio.resolve_link_url(store, key) -> str | None` (usado pelo redirect)
  - `apps.public_api.bio.bio_payload(store) -> dict` no formato:
    ```json
    {
      "store": {"name","slug","logo_url","primary_color","secondary_color",
                 "clarity_id","clarity_enabled","meta_pixel_id","meta_pixel_enabled"},
      "headline": "",
      "links": [{"key","title","icon","url"}],
      "show_branding": true
    }
    ```
    `links.url` é a URL FINAL de destino; o frontend monta o href de clique como `{API}/public/{slug}/bio/r/{key}/` (Task 4).

- [ ] **Step 1: Write the failing test**

```python
# apps/public_api/tests/test_bio_public.py
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import User
from apps.stores.models import BioClickStat, Store, StoreBioLink


def make_store(**kw):
    owner = kw.pop('owner')
    defaults = dict(
        status='active',
        whatsapp_number='63999990000',
        address='Rua X, 1', city='Palmas', state='TO',
        plan='free',
    )
    defaults.update(kw)
    return Store.objects.create(owner=owner, **defaults)


class PublicBioApiTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='pub-bio', email='pub-bio@example.com', password='test-pass'
        )
        self.store = make_store(owner=self.owner, name='Bio Pub', slug='bio-pub')
        self.client = APIClient()
        self.url = '/api/v1/public/bio-pub/bio/'

    def test_payload_has_auto_links_and_branding(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        keys = [l['key'] for l in data['links']]
        self.assertIn('auto:menu', keys)
        self.assertIn('auto:whatsapp', keys)
        self.assertIn('auto:maps', keys)
        self.assertNotIn('auto:instagram', keys)  # sem instagram_url configurada
        self.assertTrue(data['show_branding'])  # plano free
        self.assertEqual(data['store']['slug'], 'bio-pub')
        menu = next(l for l in data['links'] if l['key'] == 'auto:menu')
        self.assertIn('/bio-pub', menu['url'])
        wa = next(l for l in data['links'] if l['key'] == 'auto:whatsapp')
        self.assertIn('wa.me/5563999990000', wa['url'])

    def test_settings_toggle_hides_auto_link_and_headline(self):
        self.store.metadata = {
            'bio_settings': {
                'headline': 'Salada boa!',
                'links': {'whatsapp': False},
                'instagram_url': 'https://instagram.com/bio.pub',
            }
        }
        self.store.save(update_fields=['metadata'])
        data = self.client.get(self.url).json()
        keys = [l['key'] for l in data['links']]
        self.assertNotIn('auto:whatsapp', keys)
        self.assertIn('auto:instagram', keys)
        self.assertEqual(data['headline'], 'Salada boa!')

    def test_custom_links_only_on_pro_and_hidden_on_free(self):
        StoreBioLink.objects.create(store=self.store, title='Pesquisa', url='https://forms.gle/x', sort_order=1)
        StoreBioLink.objects.create(store=self.store, title='Inativo', url='https://x.com', is_active=False)
        data = self.client.get(self.url).json()
        self.assertNotIn('custom', ' '.join(l['key'] for l in data['links']))  # free esconde
        self.store.plan = 'pro'
        self.store.save(update_fields=['plan'])
        data = self.client.get(self.url).json()
        custom = [l for l in data['links'] if l['key'].startswith('custom:')]
        self.assertEqual(len(custom), 1)
        self.assertEqual(custom[0]['title'], 'Pesquisa')
        self.assertFalse(data['show_branding'])  # pro remove branding

    def test_get_increments_page_view(self):
        self.client.get(self.url)
        self.client.get(self.url)
        stat = BioClickStat.objects.get(store=self.store, date=timezone.localdate(), link_key='page:view')
        self.assertEqual(stat.clicks, 2)

    def test_unknown_or_inactive_store_404(self):
        self.assertEqual(self.client.get('/api/v1/public/nope/bio/').status_code, 404)
        self.store.status = 'inactive'
        self.store.save(update_fields=['status'])
        self.assertEqual(self.client.get(self.url).status_code, 404)
```

NOTA: confira como o campo de plano se chama no Store (`plan`) e os choices de `status` em `apps/stores/models/base.py`; ajuste fixture se necessário (o recon indica `status='active'` como filtro público).

- [ ] **Step 2: Run to verify it fails** (404 na rota inexistente)

- [ ] **Step 3: Implement**

`config/settings/base.py` (junto de `BILLING_PANEL_URL`):

```python
STOREFRONT_BASE_URL = os.environ.get('STOREFRONT_BASE_URL', 'https://cardapidex.com.br')
BIO_BASE_URL = os.environ.get('BIO_BASE_URL', 'https://bio.cardapidex.com.br')
```

```python
# apps/public_api/bio.py
"""Payload e resolução de links da página pública Link na Bio."""
import re
from urllib.parse import quote

from django.conf import settings

from apps.stores import billing
from apps.stores.models import StoreBioLink

AUTO_KEYS = ('menu', 'whatsapp', 'maps', 'instagram')
DEFAULT_SETTINGS = {'headline': '', 'links': {}, 'instagram_url': ''}


def bio_settings(store):
    raw = (store.metadata or {}).get('bio_settings') or {}
    merged = dict(DEFAULT_SETTINGS)
    merged.update({k: v for k, v in raw.items() if k in DEFAULT_SETTINGS})
    return merged


def _auto_link_urls(store):
    cfg = bio_settings(store)
    urls = {}
    base = settings.STOREFRONT_BASE_URL.rstrip('/')
    metadata = store.metadata or {}
    menu_url = metadata.get('menu_url') or metadata.get('frontend_url')
    urls['menu'] = menu_url or f'{base}/{store.slug}'
    digits = re.sub(r'\D', '', store.whatsapp_number or '')
    if digits:
        if len(digits) <= 11:
            digits = f'55{digits}'
        urls['whatsapp'] = f'https://wa.me/{digits}'
    if store.latitude is not None and store.longitude is not None:
        urls['maps'] = f'https://www.google.com/maps/search/?api=1&query={store.latitude},{store.longitude}'
    elif store.address:
        q = quote(f'{store.address} {store.city or ""} {store.state or ""}'.strip())
        urls['maps'] = f'https://www.google.com/maps/search/?api=1&query={q}'
    insta = (cfg.get('instagram_url') or '').strip()
    if insta:
        urls['instagram'] = insta
    return urls


AUTO_TITLES = {'menu': 'Cardápio', 'whatsapp': 'Pedir no WhatsApp', 'maps': 'Como chegar', 'instagram': 'Instagram'}
AUTO_ICONS = {'menu': '🍽️', 'whatsapp': '💬', 'maps': '📍', 'instagram': '📸'}


def bio_links(store):
    """Lista ordenada de links visíveis: automáticos habilitados + customizados ativos (se o plano permite)."""
    cfg = bio_settings(store)
    toggles = cfg.get('links') or {}
    urls = _auto_link_urls(store)
    links = []
    for key in AUTO_KEYS:
        if key in urls and toggles.get(key, True) is not False:
            links.append({'key': f'auto:{key}', 'title': AUTO_TITLES[key], 'icon': AUTO_ICONS[key], 'url': urls[key]})
    if billing.plan_allows(store, 'bio_custom_links'):
        for link in store.bio_links.filter(is_active=True):
            links.append({'key': f'custom:{link.id}', 'title': link.title, 'icon': link.icon, 'url': link.url})
    return links


def resolve_link_url(store, key):
    """Resolve uma link_key pra URL de destino, ou None. Nunca lê URL do request (anti open-redirect)."""
    if key.startswith('auto:'):
        short = key.split(':', 1)[1]
        cfg = bio_settings(store)
        if (cfg.get('links') or {}).get(short, True) is False:
            return None
        return _auto_link_urls(store).get(short)
    if key.startswith('custom:'):
        if not billing.plan_allows(store, 'bio_custom_links'):
            return None
        link = store.bio_links.filter(id=key.split(':', 1)[1], is_active=True).first()
        return link.url if link else None
    return None


def bio_page_url(store):
    return f"{settings.BIO_BASE_URL.rstrip('/')}/{store.slug}"


def bio_payload(store):
    cfg = bio_settings(store)
    logo_url = store.logo_url if getattr(store, 'logo_url', None) else None
    return {
        'store': {
            'name': store.name,
            'slug': store.slug,
            'logo_url': logo_url,
            'primary_color': store.primary_color,
            'secondary_color': store.secondary_color,
            'clarity_id': store.clarity_id,
            'clarity_enabled': store.clarity_enabled,
            'meta_pixel_id': store.meta_pixel_id,
            'meta_pixel_enabled': store.meta_pixel_enabled,
        },
        'headline': cfg.get('headline') or '',
        'links': bio_links(store),
        'show_branding': not billing.plan_allows(store, 'bio_custom_links'),
    }
```

NOTA sobre `logo_url`: o `PublicStoreSerializer` usa `get_logo_url` com `build_absolute_uri`/`obj.logo_url` — replique a MESMA lógica dele aqui (leia `apps/public_api/serializers.py:33-40` e copie; se precisar do request para URL absoluta, passe `request` como kwarg opcional em `bio_payload(store, request=None)`).

View em `apps/public_api/views.py` (mesmo padrão das vizinhas):

```python
@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([_PublicReadThrottle])
def public_store_bio(request, slug):
    from apps.stores.models import BioClickStat
    from . import bio as bio_mod
    store = _get_active_store(slug)
    BioClickStat.bump(store, 'page:view')
    return Response(bio_mod.bio_payload(store, request=request))
```

Rota em `apps/public_api/urls.py`, ANTES das rotas mais genéricas de `<slug>` se houver conflito de ordem:

```python
path('<slug:slug>/bio/', views.public_store_bio, name='public-store-bio'),
```

- [ ] **Step 4: Run tests** (`apps.public_api.tests.test_bio_public` ou caminho equivalente) — PASS.

- [ ] **Step 5: Commit** — `feat(bio): endpoint público do payload da página Link na Bio`

---

### Task 4: server2 — Redirect contador `GET /api/v1/public/<slug>/bio/r/<key>/`

**Files:**
- Modify: `apps/public_api/views.py` (view `public_store_bio_redirect`)
- Modify: `apps/public_api/urls.py`
- Test: `apps/public_api/tests/test_bio_redirect.py`

**Interfaces:**
- Consumes: `resolve_link_url`, `bio_page_url` (Task 3), `BioClickStat.bump` (Task 1), `_get_active_store`.
- Produces: rota `GET /api/v1/public/<slug>/bio/r/<key>/` → 302. `key` na URL usa `:` (ex.: `auto:menu`, `custom:<uuid>`) — usar `<str:key>` no path (str aceita `:`; NÃO usar `<slug:key>`).

- [ ] **Step 1: Write the failing test**

```python
# apps/public_api/tests/test_bio_redirect.py
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import User
from apps.stores.models import BioClickStat, Store, StoreBioLink


class PublicBioRedirectTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='red-bio', email='red-bio@example.com', password='test-pass'
        )
        self.store = Store.objects.create(
            name='Red Bio', slug='red-bio', owner=self.owner,
            status='active', whatsapp_number='63988887777', plan='pro',
        )
        self.client = APIClient()

    def r(self, key):
        return self.client.get(f'/api/v1/public/red-bio/bio/r/{key}/')

    def test_auto_whatsapp_redirects_and_counts(self):
        resp = self.r('auto:whatsapp')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], 'https://wa.me/5563988887777')
        stat = BioClickStat.objects.get(
            store=self.store, date=timezone.localdate(), link_key='auto:whatsapp'
        )
        self.assertEqual(stat.clicks, 1)

    def test_custom_link_redirects(self):
        link = StoreBioLink.objects.create(store=self.store, title='P', url='https://forms.gle/x')
        resp = self.r(f'custom:{link.id}')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], 'https://forms.gle/x')

    def test_invalid_key_falls_back_to_bio_page_without_counting(self):
        resp = self.r('custom:00000000-0000-0000-0000-000000000000')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/red-bio', resp['Location'])
        self.assertFalse(
            BioClickStat.objects.filter(store=self.store, link_key__startswith='custom:').exists()
        )

    def test_no_open_redirect_via_query(self):
        resp = self.client.get('/api/v1/public/red-bio/bio/r/auto:menu/?to=https://evil.com')
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('evil.com', resp['Location'])

    def test_unknown_store_404(self):
        self.assertEqual(self.client.get('/api/v1/public/nope/bio/r/auto:menu/').status_code, 404)
```

- [ ] **Step 2: Run to verify it fails** (404)

- [ ] **Step 3: Implement**

```python
# em apps/public_api/views.py
from django.http import HttpResponseRedirect

@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([_PublicReadThrottle])
def public_store_bio_redirect(request, slug, key):
    from apps.stores.models import BioClickStat
    from . import bio as bio_mod
    store = _get_active_store(slug)
    target = bio_mod.resolve_link_url(store, key)
    if not target:
        return HttpResponseRedirect(bio_mod.bio_page_url(store))
    BioClickStat.bump(store, key)
    return HttpResponseRedirect(target)
```

```python
# urls.py — antes da rota genérica do slug
path('<slug:slug>/bio/r/<str:key>/', views.public_store_bio_redirect, name='public-store-bio-redirect'),
```

- [ ] **Step 4: Run tests** — PASS (rode também os da Task 3 juntos).

- [ ] **Step 5: Commit** — `feat(bio): redirect contador de cliques da página bio`

---

### Task 5: server2 — CRUD `bio-links` autenticado + reorder + gate 403

**Files:**
- Create: `apps/stores/api/views/bio_views.py`
- Modify: `apps/stores/api/serializers.py` (BioLinkSerializer no fim do arquivo)
- Modify: `apps/stores/urls.py` (`router.register(r'bio-links', ...)` junto do `coupons`)
- Test: `apps/stores/tests/test_bio_links_api.py`

**Interfaces:**
- Consumes: `StoreQuerysetMixin` (`apps/core/permissions.py`), `IsStoreOwnerOrStaff` (`apps/stores/api/views/base.py`), `StoreSlugOrIdField` (`apps/stores/api/serializers.py:1637`), `billing.plan_allows`, `StoreBioLink`.
- Produces: rotas `GET/POST /api/v1/stores/bio-links/?store=<uuid|slug>`, `PATCH/DELETE /api/v1/stores/bio-links/<id>/`, `POST /api/v1/stores/bio-links/reorder/` body `{"store": "<uuid|slug>", "order": ["<id1>", "<id2>"]}`. Serializer fields: `id, store, title, url, icon, sort_order, is_active`.

- [ ] **Step 1: Write the failing test**

```python
# apps/stores/tests/test_bio_links_api.py
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import User
from apps.stores.models import Store, StoreBioLink

BASE = '/api/v1/stores/bio-links/'


class BioLinksApiTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='links-owner', email='links-owner@example.com', password='test-pass'
        )
        self.other = User.objects.create_user(
            username='links-other', email='links-other@example.com', password='test-pass'
        )
        self.store = Store.objects.create(
            name='Links Store', slug='links-store', owner=self.owner, status='active', plan='pro'
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def _create(self, **extra):
        payload = {'store': 'links-store', 'title': 'Pesquisa', 'url': 'https://forms.gle/x', 'icon': '📝'}
        payload.update(extra)
        return self.client.post(BASE, payload, format='json')

    def test_create_list_update_delete(self):
        resp = self._create()
        self.assertEqual(resp.status_code, 201, resp.content)
        link_id = resp.json()['id']
        resp = self.client.get(BASE, {'store': 'links-store'})
        self.assertEqual(len(resp.json()['results'] if 'results' in resp.json() else resp.json()), 1)
        resp = self.client.patch(f'{BASE}{link_id}/', {'title': 'Pesquisa 2'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(StoreBioLink.objects.get(id=link_id).title, 'Pesquisa 2')
        resp = self.client.delete(f'{BASE}{link_id}/')
        self.assertEqual(resp.status_code, 204)

    def test_create_blocked_on_free_plan_with_403(self):
        self.store.plan = 'free'
        self.store.save(update_fields=['plan'])
        resp = self._create()
        self.assertEqual(resp.status_code, 403)
        self.assertIn('Pro', resp.json()['detail'])

    def test_non_owner_cannot_see_or_touch(self):
        resp = self._create()
        link_id = resp.json()['id']
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f'{BASE}{link_id}/').status_code, 404)
        self.assertEqual(
            self.client.patch(f'{BASE}{link_id}/', {'title': 'x'}, format='json').status_code, 404
        )
        resp = self._create()  # other tentando criar na loja alheia
        self.assertIn(resp.status_code, (400, 403, 404))

    def test_reorder(self):
        a = StoreBioLink.objects.create(store=self.store, title='A', url='https://a.com', sort_order=0)
        b = StoreBioLink.objects.create(store=self.store, title='B', url='https://b.com', sort_order=1)
        resp = self.client.post(
            f'{BASE}reorder/', {'store': 'links-store', 'order': [str(b.id), str(a.id)]}, format='json'
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        a.refresh_from_db(); b.refresh_from_db()
        self.assertEqual((b.sort_order, a.sort_order), (0, 1))
```

- [ ] **Step 2: Run to verify it fails** (404 na rota)

- [ ] **Step 3: Implement**

Serializer (fim de `apps/stores/api/serializers.py`, espelhando `StoreCouponCreateSerializer`):

```python
class BioLinkSerializer(serializers.ModelSerializer):
    store = StoreSlugOrIdField(queryset=Store.objects.all())

    class Meta:
        model = StoreBioLink
        fields = ['id', 'store', 'title', 'url', 'icon', 'sort_order', 'is_active']
        read_only_fields = ['id']
```

(import de `StoreBioLink` no topo junto dos outros models; conferir se `StoreSlugOrIdField` já faz o tenant-gate — o recon diz que sim, retornando 'Loja não encontrada' p/ loja inacessível.)

```python
# apps/stores/api/views/bio_views.py
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.core.permissions import StoreQuerysetMixin
from apps.stores import billing
from apps.stores.models import Store, StoreBioLink
from apps.stores.api.serializers import BioLinkSerializer
from .base import IsStoreOwnerOrStaff

UPGRADE_MSG = 'Links personalizados são exclusivos dos planos Pro e Premium. Faça upgrade do plano.'


class BioLinkViewSet(StoreQuerysetMixin, viewsets.ModelViewSet):
    queryset = StoreBioLink.objects.all()
    serializer_class = BioLinkSerializer
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    store_field = 'store'

    def get_queryset(self):
        qs = super().get_queryset()
        store_ref = self.request.query_params.get('store')
        if store_ref:
            qs = qs.filter(store__slug=store_ref) | qs.filter(store__id__in=Store.objects.filter(slug=store_ref).values('id'))
            # simplificação aceitável: seguir EXATAMENTE o padrão uuid-ou-slug de StoreCouponViewSet.get_queryset (coupon_views.py:27-35)
        return qs

    def _check_gate(self, store):
        if not billing.plan_allows(store, 'bio_custom_links'):
            raise PermissionDenied(UPGRADE_MSG)

    def perform_create(self, serializer):
        self._check_gate(serializer.validated_data['store'])
        serializer.save()

    def perform_update(self, serializer):
        self._check_gate(serializer.instance.store)
        serializer.save()

    @action(detail=False, methods=['post'])
    def reorder(self, request):
        store_ref = request.data.get('store')
        order = request.data.get('order') or []
        store = Store.objects.filter(slug=store_ref).first() or Store.objects.filter(id__in=Store.objects.filter(slug=store_ref).values('id')).first()
        # idem: usar o mesmo resolve uuid-ou-slug do padrão coupon; validar acesso via queryset scoped:
        links = {str(l.id): l for l in self.get_queryset().filter(store__slug=store_ref) if True}
        if not links:
            return Response({'detail': 'Loja não encontrada ou sem links.'}, status=status.HTTP_404_NOT_FOUND)
        for pos, link_id in enumerate(order):
            link = links.get(str(link_id))
            if link and link.sort_order != pos:
                link.sort_order = pos
                link.save(update_fields=['sort_order'])
        return Response({'ok': True})
```

ATENÇÃO implementador: os dois pontos comentados acima ("seguir padrão coupon") são instrução real — abra `apps/stores/api/views/coupon_views.py:18-36` e copie o idioma exato de resolução `?store=` uuid-ou-slug para `get_queryset` e para o `reorder` (a versão esboçada acima compila mas o padrão canônico do repo é o do coupon). O teste é a autoridade.

Rota em `apps/stores/urls.py`, junto do register de coupons (linha ~188):

```python
from apps.stores.api.views.bio_views import BioLinkViewSet
router.register(r'bio-links', BioLinkViewSet, basename='bio-link')
```

- [ ] **Step 4: Run tests** — PASS.

- [ ] **Step 5: Commit** — `feat(bio): CRUD autenticado de links da bio com gate de plano e reorder`

---

### Task 6: server2 — `GET /api/v1/stores/stores/<id|slug>/bio-stats/` + suíte completa

**Files:**
- Modify: `apps/stores/api/views/store_views.py` (action `bio_stats` no `StoreViewSet`, ao lado de `meta_tracking` linha ~128)
- Test: `apps/stores/tests/test_bio_stats_api.py`

**Interfaces:**
- Consumes: `BioClickStat`, `billing.plan_allows`, `bio_links`/`AUTO_TITLES` de `apps/public_api/bio.py`, `StoreViewSet.get_object()` (aceita uuid ou slug, non-owner → 404).
- Produces payload:
  ```json
  {"days": 30,
   "page_views": {"total": 12, "series": [{"date": "2026-07-28", "views": 12}]},
   "links": [{"key": "auto:menu", "title": "Cardápio", "total": 5}]}
  ```
  `links` ordenado por total desc; títulos: automáticos de `AUTO_TITLES`, custom do `StoreBioLink.title` (deletado → key crua).

- [ ] **Step 1: Write the failing test**

```python
# apps/stores/tests/test_bio_stats_api.py
import datetime

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import User
from apps.stores.models import BioClickStat, Store, StoreBioLink


class BioStatsApiTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='stats-owner', email='stats-owner@example.com', password='test-pass'
        )
        self.other = User.objects.create_user(
            username='stats-other', email='stats-other@example.com', password='test-pass'
        )
        self.store = Store.objects.create(
            name='Stats Store', slug='stats-store', owner=self.owner, status='active', plan='pro'
        )
        self.url = f'/api/v1/stores/stores/{self.store.id}/bio-stats/'
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_stats_payload(self):
        today = timezone.localdate()
        old = today - datetime.timedelta(days=40)
        BioClickStat.objects.create(store=self.store, date=today, link_key='page:view', clicks=7)
        BioClickStat.objects.create(store=self.store, date=today, link_key='auto:menu', clicks=3)
        link = StoreBioLink.objects.create(store=self.store, title='Pesquisa', url='https://f.gle/x')
        BioClickStat.objects.create(store=self.store, date=today, link_key=f'custom:{link.id}', clicks=5)
        BioClickStat.objects.create(store=self.store, date=old, link_key='page:view', clicks=99)
        data = self.client.get(self.url).json()
        self.assertEqual(data['page_views']['total'], 7)  # 99 fora da janela de 30d
        totals = {l['key']: l['total'] for l in data['links']}
        self.assertEqual(totals[f'custom:{link.id}'], 5)
        self.assertEqual(totals['auto:menu'], 3)
        titles = {l['key']: l['title'] for l in data['links']}
        self.assertEqual(titles[f'custom:{link.id}'], 'Pesquisa')
        self.assertEqual(titles['auto:menu'], 'Cardápio')
        self.assertEqual(data['links'][0]['key'], f'custom:{link.id}')  # ordenado desc

    def test_gate_403_on_free(self):
        self.store.plan = 'free'
        self.store.save(update_fields=['plan'])
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 403)
        self.assertIn('Pro', resp.json()['detail'])

    def test_non_owner_404(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
```

- [ ] **Step 2: Run to verify it fails**

- [ ] **Step 3: Implement** (em `store_views.py`, ao lado do `meta_tracking`):

```python
@action(detail=True, methods=['get'], url_path='bio-stats')
def bio_stats(self, request, pk=None):
    import datetime
    from django.utils import timezone
    from rest_framework.exceptions import PermissionDenied
    from apps.public_api.bio import AUTO_TITLES
    from apps.stores import billing
    from apps.stores.models import BioClickStat, StoreBioLink

    store = self.get_object()
    if not billing.plan_allows(store, 'bio_analytics'):
        raise PermissionDenied('Estatísticas do Link na Bio são exclusivas dos planos Pro e Premium. Faça upgrade do plano.')
    try:
        days = min(max(int(request.query_params.get('days', 30)), 1), 90)
    except (TypeError, ValueError):
        days = 30
    since = timezone.localdate() - datetime.timedelta(days=days - 1)
    stats = BioClickStat.objects.filter(store=store, date__gte=since)
    views = stats.filter(link_key='page:view').order_by('date')
    series = [{'date': s.date.isoformat(), 'views': s.clicks} for s in views]
    link_totals = {}
    for s in stats.exclude(link_key='page:view'):
        link_totals[s.link_key] = link_totals.get(s.link_key, 0) + s.clicks
    custom_titles = {f'custom:{l.id}': l.title for l in StoreBioLink.objects.filter(store=store)}
    links = []
    for key, total in sorted(link_totals.items(), key=lambda kv: -kv[1]):
        if key.startswith('auto:'):
            title = AUTO_TITLES.get(key.split(':', 1)[1], key)
        else:
            title = custom_titles.get(key, key)
        links.append({'key': key, 'title': title, 'total': total})
    return Response({
        'days': days,
        'page_views': {'total': sum(s.clicks for s in views), 'series': series},
        'links': links,
    })
```

(mover imports que já existirem no topo do arquivo para lá; sem import redundante.)

- [ ] **Step 4: Run ALL bio tests** (`test_bio_models test_bio_billing test_bio_public test_bio_redirect test_bio_links_api test_bio_stats_api`) — PASS.

- [ ] **Step 5: Full suite no container** — comparar com baseline 1277 pass/45 falhas conhecidas; zero falha nova.

- [ ] **Step 6: Commit** — `feat(bio): endpoint bio-stats com gate bio_analytics`

---

### Task 7: cardapidex-web — página `/bio/[slug]` SSR

**Files:**
- Create: `pages/bio/[slug].js`
- Create: `src/pages/BioPage.jsx`
- Create: `src/styles/bio.css` (importar no próprio componente)
- Modify: `src/lib/storefrontRouting.js` (adicionar `'bio'` a `RESERVED_ROOT_PATHS`)
- Test: `src/pages/__tests__/BioPage.test.jsx`

**Interfaces:**
- Consumes: `GET {API_INTERNAL_URL|NEXT_PUBLIC_API_URL}/public/{slug}/bio/` (payload da Task 3); `hasTrackingConsent()` de `src/utils/cookieConsent.js`.
- Produces: página standalone (SEM StoreProvider — não seta `storeSlug`/`initialCatalog`/`previewStoreConfig` em pageProps, de propósito, pra não montar carrinho/catálogo). Tema via CSS vars inline no wrapper (`--color-primary`, `--color-secondary`) a partir dos props SSR (sem FOUC). Cada botão aponta pra `{NEXT_PUBLIC_API_URL}/public/{slug}/bio/r/{key}/`.

- [ ] **Step 1: Write the failing test**

```jsx
// src/pages/__tests__/BioPage.test.jsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import BioPage from '../BioPage';

vi.mock('../../utils/cookieConsent', () => ({ hasTrackingConsent: () => false }));

const payload = {
  store: {
    name: 'Cê Saladas', slug: 'ce-saladas', logo_url: 'https://backend.pastita.com.br/media/logo.png',
    primary_color: '#649e20', secondary_color: '#f97316',
    clarity_id: '', clarity_enabled: false, meta_pixel_id: '', meta_pixel_enabled: false,
  },
  headline: 'Salada fresca todo dia',
  links: [
    { key: 'auto:menu', title: 'Cardápio', icon: '🍽️', url: 'https://cardapidex.com.br/ce-saladas' },
    { key: 'custom:abc', title: 'Pesquisa de satisfação', icon: '📝', url: 'https://forms.gle/x' },
  ],
  show_branding: true,
};

describe('BioPage', () => {
  it('renderiza nome, headline e botões apontando pro redirect', () => {
    render(<BioPage bio={payload} />);
    expect(screen.getByText('Cê Saladas')).toBeInTheDocument();
    expect(screen.getByText('Salada fresca todo dia')).toBeInTheDocument();
    const menu = screen.getByRole('link', { name: /Cardápio/ });
    expect(menu.getAttribute('href')).toContain('/public/ce-saladas/bio/r/auto:menu/');
    expect(screen.getByRole('link', { name: /Pesquisa de satisfação/ })).toBeInTheDocument();
  });

  it('mostra rodapé Cardapidex quando show_branding', () => {
    render(<BioPage bio={payload} />);
    expect(screen.getByText(/Cardapidex/)).toBeInTheDocument();
  });

  it('esconde rodapé quando show_branding=false e aplica cor da loja', () => {
    const { container } = render(<BioPage bio={{ ...payload, show_branding: false }} />);
    expect(screen.queryByText(/feito com/i)).toBeNull();
    const wrapper = container.querySelector('.bio-page');
    expect(wrapper.style.getPropertyValue('--color-primary')).toBe('#649e20');
  });
});
```

- [ ] **Step 2: Run** `npx vitest run src/pages/__tests__/BioPage.test.jsx` — FAIL (módulo inexistente).

- [ ] **Step 3: Implement**

```jsx
// src/pages/BioPage.jsx
import Head from 'next/head';
import { useEffect, useState } from 'react';
import { hasTrackingConsent } from '../utils/cookieConsent';
import '../styles/bio.css';

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace(/\/+$/, '');

export default function BioPage({ bio }) {
  const { store, headline, links, show_branding: showBranding } = bio;
  const [consent, setConsent] = useState(false);
  useEffect(() => { setConsent(hasTrackingConsent()); }, []);

  useEffect(() => {
    if (!consent || !store.clarity_enabled || !/^[a-z0-9]{4,32}$/i.test(store.clarity_id || '')) return;
    if (document.head.querySelector('script[src*="clarity.ms"]')) return;
    const s = document.createElement('script');
    s.async = true;
    s.src = `https://www.clarity.ms/tag/${store.clarity_id}`;
    document.head.appendChild(s);
  }, [consent, store.clarity_enabled, store.clarity_id]);

  const themeVars = {
    '--color-primary': store.primary_color || '#649e20',
    '--color-secondary': store.secondary_color || '#f97316',
  };

  return (
    <div className="bio-page" style={themeVars}>
      <Head>
        <title>{`${store.name} — Links`}</title>
        <meta name="description" content={headline || `Links de ${store.name}`} />
        <meta property="og:title" content={store.name} />
        {store.logo_url ? <meta property="og:image" content={store.logo_url} /> : null}
        <meta name="robots" content="index,follow" />
      </Head>
      <main className="bio-card">
        {store.logo_url ? (
          <img className="bio-logo" src={store.logo_url} alt={store.name} />
        ) : null}
        <h1 className="bio-name">{store.name}</h1>
        {headline ? <p className="bio-headline">{headline}</p> : null}
        <nav className="bio-links">
          {links.map((link) => (
            <a
              key={link.key}
              className="bio-link"
              href={`${API_BASE}/public/${store.slug}/bio/r/${link.key}/`}
              rel="noopener"
            >
              {link.icon ? <span className="bio-link__icon" aria-hidden="true">{link.icon}</span> : null}
              <span className="bio-link__title">{link.title}</span>
            </a>
          ))}
        </nav>
        {showBranding ? (
          <a className="bio-branding" href="https://cardapidex.com.br" rel="noopener">
            feito com <strong>Cardapidex</strong>
          </a>
        ) : null}
      </main>
    </div>
  );
}
```

```css
/* src/styles/bio.css */
.bio-page {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  padding: 32px 16px 48px;
  background:
    radial-gradient(1200px 500px at 50% -10%, color-mix(in srgb, var(--color-primary) 22%, transparent), transparent),
    #101014;
  color: #f5f5f4;
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
}
.bio-card { width: 100%; max-width: 460px; text-align: center; }
.bio-logo {
  width: 96px; height: 96px; border-radius: 50%; object-fit: cover;
  border: 3px solid var(--color-primary); margin: 8px auto 12px; display: block;
  background: #fff;
}
.bio-name { font-size: 1.5rem; font-weight: 700; margin: 0 0 4px; }
.bio-headline { margin: 0 0 20px; opacity: 0.8; font-size: 0.95rem; }
.bio-links { display: flex; flex-direction: column; gap: 12px; margin-top: 20px; }
.bio-link {
  display: flex; align-items: center; justify-content: center; gap: 10px;
  padding: 14px 18px; border-radius: 14px; text-decoration: none;
  background: color-mix(in srgb, var(--color-primary) 16%, #1b1b20);
  border: 1px solid color-mix(in srgb, var(--color-primary) 45%, transparent);
  color: inherit; font-weight: 600; font-size: 1rem;
  transition: transform 0.12s ease, background 0.12s ease;
}
.bio-link:hover { transform: translateY(-2px); background: color-mix(in srgb, var(--color-primary) 30%, #1b1b20); }
.bio-link__icon { font-size: 1.15rem; }
.bio-branding {
  display: inline-block; margin-top: 28px; font-size: 0.8rem; opacity: 0.6;
  color: inherit; text-decoration: none;
}
.bio-branding:hover { opacity: 1; }
```

NOTA: se o build reclamar de import de CSS fora de `_app.js` (regra do pages router p/ CSS global), mover o `import '../styles/bio.css'` para `pages/_app.js` (import incondicional no topo, junto dos outros globais) e remover do componente. Classes são namespaced (`bio-*`), sem colisão.

```js
// pages/bio/[slug].js
import BioPage from '../../src/pages/BioPage';

const apiUrl = (process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace(/\/+$/, '');

export async function getServerSideProps({ params }) {
  try {
    const resp = await fetch(`${apiUrl}/public/${params.slug}/bio/`, { cache: 'no-store' });
    if (!resp.ok) return { notFound: true };
    const bio = await resp.json();
    return { props: { bio } };
  } catch (err) {
    return { notFound: true };
  }
}

export default BioPage;
```

Em `src/lib/storefrontRouting.js`, adicionar `'bio'` ao `RESERVED_ROOT_PATHS`.

- [ ] **Step 4: Run tests + build** — `npm test` (142 + 3 novos, zero regressão) e `npm run build` limpo.

- [ ] **Step 5: Commit** — `feat(bio): página pública /bio/[slug] standalone com tema da loja`

---

### Task 8: cardapidex-web — host routing `bio.cardapidex.com.br` no `proxy.js`

**Files:**
- Modify: `proxy.js` (branch de hosts bio ANTES da lógica de store-by-domain)
- Test: `src/lib/__tests__/bioHost.test.js` (testar o helper puro extraído)

**Interfaces:**
- Consumes: estrutura atual de `proxy.js` (`PLATFORM_DOMAINS`, `normalizeDomain`, `NextResponse.rewrite`).
- Produces: helper puro exportado `bioRewritePath(domain, pathname) -> string | null` em `src/lib/bioHost.js`: para domínio em `BIO_DOMAINS` (`bio.cardapidex.com.br`, `bio.localhost` + extras via env `BIO_DOMAINS` separados por vírgula): `/` → `null` com marcação especial (redirect pra `https://cardapidex.com.br`), `/<slug>` → `/bio/<slug>`; domínio fora da lista → `null`.

- [ ] **Step 1: Write the failing test**

```js
// src/lib/__tests__/bioHost.test.js
import { describe, expect, it } from 'vitest';
import { isBioDomain, bioRewritePath } from '../bioHost';

describe('bioHost', () => {
  it('reconhece domínios bio', () => {
    expect(isBioDomain('bio.cardapidex.com.br')).toBe(true);
    expect(isBioDomain('cardapidex.com.br')).toBe(false);
    expect(isBioDomain('cesaladas.com.br')).toBe(false);
  });

  it('reescreve /<slug> para /bio/<slug>', () => {
    expect(bioRewritePath('/ce-saladas')).toBe('/bio/ce-saladas');
    expect(bioRewritePath('/ce-saladas/')).toBe('/bio/ce-saladas');
  });

  it('raiz não reescreve (vira redirect pro site institucional)', () => {
    expect(bioRewritePath('/')).toBe(null);
  });

  it('não reescreve assets/_next', () => {
    expect(bioRewritePath('/_next/static/x.js')).toBe(null);
    expect(bioRewritePath('/favicon.ico')).toBe(null);
  });
});
```

- [ ] **Step 2: Run** — FAIL (módulo inexistente).

- [ ] **Step 3: Implement**

```js
// src/lib/bioHost.js
const DEFAULT_BIO_DOMAINS = ['bio.cardapidex.com.br', 'bio.localhost'];

export function bioDomains() {
  const extra = (process.env.BIO_DOMAINS || '')
    .split(',')
    .map((d) => d.trim().toLowerCase())
    .filter(Boolean);
  return new Set([...DEFAULT_BIO_DOMAINS, ...extra]);
}

export function isBioDomain(domain) {
  return bioDomains().has(String(domain || '').toLowerCase());
}

export function bioRewritePath(pathname) {
  const clean = String(pathname || '/').replace(/\/+$/, '') || '/';
  if (clean === '/') return null;
  if (clean.startsWith('/_next') || clean.startsWith('/bio/')) return null;
  if (/\.[a-z0-9]+$/i.test(clean)) return null; // assets (favicon.ico etc.)
  const slug = clean.split('/')[1];
  if (!slug) return null;
  return `/bio/${slug}`;
}
```

Em `proxy.js`, logo após calcular `domain` e ANTES do bloco `if (!PLATFORM_DOMAINS.has(domain))`:

```js
import { isBioDomain, bioRewritePath } from './src/lib/bioHost';

// dentro do handler:
if (isBioDomain(domain)) {
  const rewritten = bioRewritePath(url.pathname);
  if (rewritten) {
    const target = request.nextUrl.clone();
    target.pathname = rewritten;
    return NextResponse.rewrite(target);
  }
  if (url.pathname === '/' || url.pathname === '') {
    return NextResponse.redirect('https://cardapidex.com.br');
  }
  return NextResponse.next();
}
```

(adaptar nomes de variáveis ao código real do `proxy.js` — ler o arquivo antes; o matcher existente já exclui `_next/static` etc., a checagem extra no helper é cinto-e-suspensório.)

- [ ] **Step 4: Run** `npm test` + `npm run build` — verde.

- [ ] **Step 5: Smoke local** — `npm run dev` (ou servidor de prod local) e `curl -H 'Host: bio.localhost' http://127.0.0.1:3000/ce-saladas` → HTML da página bio (se o backend local não tiver a loja, basta ver a rota `/bio/ce-saladas` sendo atingida, não 404 de rota).

- [ ] **Step 6: Commit** — `feat(bio): host routing bio.cardapidex.com.br no proxy`

---

### Task 9: pastita-dash — página "Link na Bio"

**Files:**
- Create: `src/services/bioApi.ts`
- Create: `src/pages/bio/LinkBioPage.tsx`
- Modify: `src/App.tsx` (lazy import + rota `stores/:storeId/link-bio`, junto da rota `fidelidade` linhas ~44 e ~230)
- Modify: `src/components/layout/navSections.tsx` (item "Link na Bio" na seção Cardápio, ícone `LinkIcon` de heroicons/24/outline)
- Test: `src/pages/bio/__tests__/LinkBioPage.test.tsx`

**Interfaces:**
- Consumes: endpoints das Tasks 5-6; `getStores`/`updateStore` de `src/services/storesApi.ts`; `api` axios default de `src/services/api.ts`; `PaywallModal` de `src/components/billing/PaywallModal.tsx` (`{open, message, onClose}`); UI de `src/components/common` (`Card, Button, Input, Switch, Loading, Badge`); `TimeSeriesChart` (`{data,xKey,yKey,label,type}`) e `RankBarList` (`{items: {label,value}[]}`) de `src/components/reports/`.
- Produces:
  ```ts
  // bioApi.ts
  export interface BioLink { id: string; store: string; title: string; url: string; icon: string; sort_order: number; is_active: boolean; }
  export interface BioStats { days: number; page_views: { total: number; series: { date: string; views: number }[] }; links: { key: string; title: string; total: number }[]; }
  export const listBioLinks: (storeRef: string) => Promise<BioLink[]>;
  export const createBioLink: (data: Partial<BioLink> & { store: string }) => Promise<BioLink>;
  export const updateBioLink: (id: string, data: Partial<BioLink>) => Promise<BioLink>;
  export const deleteBioLink: (id: string) => Promise<void>;
  export const reorderBioLinks: (storeRef: string, order: string[]) => Promise<void>;
  export const getBioStats: (storeId: string, days?: number) => Promise<BioStats>;
  ```

- [ ] **Step 1: Write the failing test**

```tsx
// src/pages/bio/__tests__/LinkBioPage.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import LinkBioPage from '../LinkBioPage';

jest.mock('../../../services/storesApi', () => ({
  getStores: jest.fn(),
  updateStore: jest.fn(),
}));
jest.mock('../../../services/bioApi', () => ({
  listBioLinks: jest.fn(),
  createBioLink: jest.fn(),
  updateBioLink: jest.fn(),
  deleteBioLink: jest.fn(),
  reorderBioLinks: jest.fn(),
  getBioStats: jest.fn(),
}));

const { getStores } = jest.requireMock('../../../services/storesApi');
const { listBioLinks, getBioStats } = jest.requireMock('../../../services/bioApi');

const store = {
  id: 'uuid-1', slug: 'ce-saladas', name: 'Cê Saladas',
  metadata: { bio_settings: { headline: 'Oi', links: {}, instagram_url: '' } },
};

function mount() {
  return render(
    <MemoryRouter initialEntries={['/stores/ce-saladas/link-bio']}>
      <Routes>
        <Route path="/stores/:storeId/link-bio" element={<LinkBioPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('LinkBioPage', () => {
  beforeEach(() => {
    jest.resetAllMocks();
    getStores.mockResolvedValue({ count: 1, next: null, previous: null, results: [store] });
    listBioLinks.mockResolvedValue([
      { id: 'l1', store: 'uuid-1', title: 'Pesquisa', url: 'https://f.gle/x', icon: '📝', sort_order: 0, is_active: true },
    ]);
    getBioStats.mockResolvedValue({
      days: 30,
      page_views: { total: 12, series: [{ date: '2026-07-28', views: 12 }] },
      links: [{ key: 'custom:l1', title: 'Pesquisa', total: 5 }],
    });
  });

  it('mostra a URL pública da bio e os links customizados', async () => {
    mount();
    await waitFor(() => expect(screen.getByText(/bio\.cardapidex\.com\.br\/ce-saladas/)).toBeInTheDocument());
    expect(screen.getByText('Pesquisa')).toBeInTheDocument();
  });

  it('mostra paywall quando stats devolve 403', async () => {
    getBioStats.mockRejectedValue({ response: { status: 403, data: { detail: 'Estatísticas do Link na Bio são exclusivas dos planos Pro e Premium. Faça upgrade do plano.' } } });
    mount();
    await waitFor(() => expect(screen.getByText(/exclusivas dos planos Pro e Premium/)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run** `npx jest src/pages/bio` — FAIL.

- [ ] **Step 3: Implement `bioApi.ts`**

```ts
// src/services/bioApi.ts
import api from './api';

export interface BioLink {
  id: string; store: string; title: string; url: string;
  icon: string; sort_order: number; is_active: boolean;
}
export interface BioStats {
  days: number;
  page_views: { total: number; series: { date: string; views: number }[] };
  links: { key: string; title: string; total: number }[];
}

const BASE = '/stores/bio-links';

export const listBioLinks = async (storeRef: string): Promise<BioLink[]> => {
  const { data } = await api.get(`${BASE}/`, { params: { store: storeRef } });
  return Array.isArray(data) ? data : data.results ?? [];
};
export const createBioLink = async (payload: Partial<BioLink> & { store: string }): Promise<BioLink> => {
  const { data } = await api.post(`${BASE}/`, payload);
  return data;
};
export const updateBioLink = async (id: string, payload: Partial<BioLink>): Promise<BioLink> => {
  const { data } = await api.patch(`${BASE}/${id}/`, payload);
  return data;
};
export const deleteBioLink = async (id: string): Promise<void> => {
  await api.delete(`${BASE}/${id}/`);
};
export const reorderBioLinks = async (storeRef: string, order: string[]): Promise<void> => {
  await api.post(`${BASE}/reorder/`, { store: storeRef, order });
};
export const getBioStats = async (storeId: string, days = 30): Promise<BioStats> => {
  const { data } = await api.get(`/stores/stores/${storeId}/bio-stats/`, { params: { days }, skipAutoLogout: true });
  return data;
};
```

- [ ] **Step 4: Implement `LinkBioPage.tsx`** — seguir a ESTRUTURA da `FidelidadePage.tsx` (resolve loja por slug/uuid via `getStores`, effects com flag `active`, guard `<Loading />`, wrapper `space-y-6`, header `h1 text-xl font-semibold text-fg-token`). Seções (cada uma um `<Card>`):

  1. **Sua página** — URL `https://bio.cardapidex.com.br/{slug}` em `<code>` + `<Button>` "Copiar" (`navigator.clipboard.writeText`) + `<a>` "Abrir" target _blank.
  2. **Conteúdo** — `<Input label="Headline" maxLength={120}>`, `<Input label="Instagram (URL)">`, 4 `<Switch>` (Cardápio, WhatsApp, Como chegar, Instagram) lendo/salvando `store.metadata.bio_settings` via `updateStore(store.id, { metadata: { ...store.metadata, bio_settings: novo } })`; botão Salvar por card.
  3. **Links personalizados** — lista de `BioLink` ordenada por `sort_order`; cada linha: ícone, título, url truncada, `<Switch>` ativo, botões ↑/↓ (troca `sort_order` com o vizinho e chama `reorderBioLinks` com a ordem inteira), editar (form inline ou Modal), excluir. Form de novo link (título, URL, emoji). Erros 403 do create/update → `setPaywall(detail)`.
  4. **Estatísticas (30 dias)** — `getBioStats`; sucesso: `<TimeSeriesChart data={stats.page_views.series} xKey="date" yKey="views" label="Visitas" type="bar" />` + `<RankBarList items={stats.links.map(l => ({ label: l.title, value: l.total }))} />` + total de visitas; 403: renderizar inline o `detail` + botão "Ver planos" (Link `/assinatura`) — e também alimentar o `<PaywallModal open={!!paywall} message={paywall ?? ''} onClose={() => setPaywall(null)} />` compartilhado da página.

  Copiar o tratamento de erro do padrão ProductFormModal: `catch (err: any) { const detail = err?.response?.data?.detail; if (err?.response?.status === 403 && detail) setPaywall(detail); else setError(...); }`. No caso do teste, o 403 das stats deve renderizar o texto do detail na seção de estatísticas (por isso o assert `getByText(/exclusivas dos planos/)`).

- [ ] **Step 5: Wire rota + nav** — `App.tsx`: `const LinkBioPage = lazy(() => import('./pages/bio/LinkBioPage'));` + `<Route path="stores/:storeId/link-bio" element={<PageBoundary><LinkBioPage /></PageBoundary>} />`. `navSections.tsx`: na seção Cardápio, após Fidelidade: `{ name: 'Link na Bio', href: storeHref('link-bio'), icon: LinkIcon }` (import `LinkIcon` de `@heroicons/react/24/outline`).

- [ ] **Step 6: Run** `npx jest` (524 + novos, zero regressão) e `npx tsc --noEmit` — limpos.

- [ ] **Step 7: Commit** — `feat(bio): página Link na Bio no dash (config, links, estatísticas)`

---

### Task 10: Deploy + DNS/Tunnel + verificação ao vivo

**Files:** nenhum código novo; operação.

- [ ] **Step 1: Deploy server2** — padrão vigente do repo (memória `project_server2_deploy` / `project_server2_docker_logs_fix`): `docker cp` dos arquivos alterados nos 3 containers (web/celery/beat) + `docker commit` da imagem, rodar `migrate` no container web, restart. Conferir `docker ps` saudável e `curl https://backend.pastita.com.br/api/v1/public/ce-saladas/bio/` retornando payload.
- [ ] **Step 2: Deploy cardapidex-web** — `npm run deploy:local` (build staged + swap + restart + healthcheck com rollback automático).
- [ ] **Step 3: DNS + Tunnel** — adicionar hostname `bio.cardapidex.com.br → http://localhost:3010` no ingress do Cloudflare Tunnel (`/etc/cloudflared/config.yml` ou o config ativo em `/home/graco/.cloudflared/`; conferir qual tunnel serve `cardapidex.com.br`), `cloudflared tunnel route dns <tunnel> bio.cardapidex.com.br` (cria o CNAME), restart do serviço cloudflared. Se o config exigir sudo, PARAR e pedir ao usuário rodar os comandos (`! sudo ...`).
- [ ] **Step 4: Deploy dash** — `git push origin main` (Vercel auto-deploy). Antes: `git fetch` + reconciliar (regra branch única).
- [ ] **Step 5: Verificação ao vivo** — abrir `https://bio.cardapidex.com.br/ce-saladas`: página com tema da loja; clicar "Cardápio" → 302 pro cardápio; no dash, página Link na Bio mostra a visita e o clique; criar um link custom ("Pesquisa de satisfação") e vê-lo aparecer na página pública (loja Pro/exempt); loja free (se houver) mostra rodapé Cardapidex.
- [ ] **Step 6: Atualizar memória** (`project_link_na_bio_jul28.md`) com commits/estado final.

---

## Como rodar testes do server2 (sem python local)

Container descartável + Postgres efêmero (SQLite falha em AddIndexConcurrently). Padrão usado nas últimas sessões:

```bash
docker run -d --name bio-test-db -e POSTGRES_PASSWORD=test -e POSTGRES_DB=test postgres:15-alpine
docker run --rm --link bio-test-db:db \
  -v /home/graco/WORK/server2:/app -w /app \
  -e DJANGO_SETTINGS_MODULE=config.settings.development \
  -e DATABASE_URL=postgres://postgres:test@db:5432/test \
  pastita_backend:latest \
  python manage.py test apps.stores.tests.test_bio_models -v1 --keepdb
docker rm -f bio-test-db
```

Ajustar env vars ao que `config/settings/development.py` espera (ver runs anteriores; o script `server2-test.sh` existe mas IGNORA argumentos — preferir o comando direto acima). NÃO editar a árvore enquanto a suíte completa roda.
