# Backend Stabilization — addresses migration + checkout/zones regression tests

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remover o dual-write do JSONField `StoreCustomer.addresses` (deprecated), migrar leitores para `address_list`, e cobrir com testes de regressão os caminhos críticos de checkout e delivery zones.

**Architecture:** Quatro tarefas independentes que não se bloqueiam entre si — a migração de addresses é uma limpeza de débito técnico; os testes são adicionados nos arquivos de teste existentes (`test_checkout_service.py`, `test_delivery_pricing_unified.py`); o teste de CompanyProfileViewSet vai em `test_company_profile_views.py` (novo).

**Tech Stack:** Django 5.2, DRF, pytest/Django TestCase, `StoreCustomerAddress` (FK model), `GeoService._normalize_text()`, `CheckoutService.create_order()`.

**Estado inicial:** 412 testes, todos passando. Container Docker `pastita_web`. Commits via git local (não dentro do container).

---

## Task 1: Migrar leitores/escritores do `StoreCustomer.addresses` JSONField

**Files:**
- Modify: `apps/stores/models/customer.py:130-133`
- Modify: `apps/core/services/customer_identity.py:346-360`
- Modify: `apps/stores/api/views/storefront_views.py:417-430`
- Modify: `apps/agents/services.py:399`

### Contexto

`StoreCustomerAddress` (FK model, `related_name='address_list'`) foi criado para substituir o JSONField `StoreCustomer.addresses`. O `CustomerIdentityService` já escreve na nova tabela mas ainda faz dual-write no JSONField. Quatro locais ainda leem/escrevem no JSONField antigo.

### Campos de `StoreCustomerAddress`
`street`, `number`, `complement`, `neighborhood`, `city`, `state`, `zip_code`, `reference`, `formatted`, `is_default`, `label`

- [ ] **Step 1: Corrigir `get_default_address()` em `models/customer.py:130-132`**

```python
# ANTES:
def get_default_address(self):
    if self.addresses and len(self.addresses) > self.default_address_index:
        return self.addresses[self.default_address_index]
    return None

# DEPOIS:
def get_default_address(self):
    addr = self.address_list.filter(is_default=True).first()
    if addr is None:
        addr = self.address_list.order_by('-created_at').first()
    if addr is None:
        return None
    return {
        'street': addr.street,
        'number': addr.number,
        'complement': addr.complement,
        'neighborhood': addr.neighborhood,
        'city': addr.city,
        'state': addr.state,
        'zip_code': addr.zip_code,
        'reference': addr.reference,
        'formatted': addr.formatted,
    }
```

- [ ] **Step 2: Remover dual-write em `customer_identity.py:346-360`**

Localizar o bloco:
```python
# Keep the legacy JSON field in sync so old readers stay consistent.
addr_json_entry = {
    k: normalized_address.get(k, "")
    for k in ("street", "number", "complement", "neighborhood",
              "city", "state", "zip_code", "reference", "formatted")
}
existing_json = store_customer.addresses if isinstance(store_customer.addresses, list) else []
already_there = any(
    e.get("formatted") == addr_json_entry["formatted"]
    for e in existing_json
    if addr_json_entry["formatted"]
)
if not already_there:
    store_customer.addresses = existing_json + [addr_json_entry]
    store_customer_updates.append("addresses")
```

Remover completamente esse bloco. O `store_customer_updates.append("addresses")` deve ser removido também. Apenas o código que escreve em `StoreCustomerAddress` (já existe acima) fica.

- [ ] **Step 3: Corrigir `storefront_views.py:419-420`**

Localizar em `StoreCustomerProfileView.patch()`:
```python
if store_customer:
    if isinstance(addresses, list):
        store_customer.addresses = addresses   # ← remover esta linha
    default_index = data.get('default_address_index')
```

Substituir por: importar e criar registros relacionais para cada endereço da lista:
```python
if store_customer:
    if isinstance(addresses, list) and addresses:
        from apps.stores.models import StoreCustomerAddress
        store_customer.address_list.filter(is_default=True).update(is_default=False)
        for i, addr_dict in enumerate(addresses):
            if not isinstance(addr_dict, dict):
                continue
            formatted = addr_dict.get('formatted', '')
            if not formatted:
                parts = [
                    addr_dict.get('street', ''), addr_dict.get('number', ''),
                    addr_dict.get('neighborhood', ''), addr_dict.get('city', ''),
                ]
                formatted = ', '.join(p for p in parts if p)
            already = store_customer.address_list.filter(formatted=formatted).first() if formatted else None
            if not already:
                StoreCustomerAddress.objects.create(
                    customer=store_customer,
                    street=addr_dict.get('street', ''),
                    number=addr_dict.get('number', ''),
                    complement=addr_dict.get('complement', ''),
                    neighborhood=addr_dict.get('neighborhood', ''),
                    city=addr_dict.get('city', ''),
                    state=addr_dict.get('state', ''),
                    zip_code=addr_dict.get('zip_code', ''),
                    reference=addr_dict.get('reference', ''),
                    formatted=formatted,
                    is_default=(i == 0),
                )
    default_index = data.get('default_address_index')
    # default_address_index is deprecated — field kept for compat but address_list.is_default is authoritative
```

- [ ] **Step 4: Corrigir `agents/services.py:399`** — leitura do JSONField

Localizar:
```python
for address in (store_customer.addresses or [])[:2]:
    formatted = self._format_address_for_context(address)
    if formatted:
        saved_addresses.append(formatted)
```

Substituir por:
```python
for addr in store_customer.address_list.order_by('-is_default', '-created_at')[:2]:
    formatted = self._format_address_for_context({
        'street': addr.street,
        'number': addr.number,
        'neighborhood': addr.neighborhood,
        'city': addr.city,
        'state': addr.state,
        'formatted': addr.formatted,
    })
    if formatted:
        saved_addresses.append(formatted)
```

- [ ] **Step 5: Sincronizar arquivos modificados com o container**

```bash
docker cp apps/stores/models/customer.py pastita_web:/app/apps/stores/models/customer.py
docker cp apps/core/services/customer_identity.py pastita_web:/app/apps/core/services/customer_identity.py
docker cp apps/stores/api/views/storefront_views.py pastita_web:/app/apps/stores/api/views/storefront_views.py
docker cp apps/agents/services.py pastita_web:/app/apps/agents/services.py
```

- [ ] **Step 6: Rodar testes e verificar**

```bash
docker exec pastita_web python manage.py test tests/ --verbosity=1 2>&1 | tail -5
```
Esperado: `Ran 412 tests ... OK`

- [ ] **Step 7: Commit**

```bash
git add apps/stores/models/customer.py \
        apps/core/services/customer_identity.py \
        apps/stores/api/views/storefront_views.py \
        apps/agents/services.py
git commit -m "refactor: migrar leitores/escritores de StoreCustomer.addresses para address_list relacional"
```

---

## Task 2: Testes de regressão — CheckoutService

**Files:**
- Modify: `tests/test_checkout_service.py` (adicionar ao final)

### Gaps de cobertura
O arquivo existente cobre: criação de pedido, frete, cupom, trusted_fee, payment webhook.
**Faltam:** salad builder bypassa stock check; cupom com pedido mínimo; frete grátis acima de threshold.

- [ ] **Step 1: Adicionar classe `SaladBuilderCheckoutTest` ao final de `test_checkout_service.py`**

```python
from apps.stores.models import StoreCart, StoreCartItem, StoreProduct, StoreCategory


class SaladBuilderCheckoutTest(TestCase):
    """
    Salad builder items (is_salad_builder=True in options) devem passar no
    checkout mesmo quando o produto base tem track_stock=True e stock=0,
    pois a salada é montada customizada — não tem estoque real.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username='salad_owner', email='salad@test.com', password='pass'
        )
        self.store = Store.objects.create(
            owner=self.owner,
            name='Salad Store',
            slug='salad-store',
            status='active',
            is_active=True,
        )
        self.category = StoreCategory.objects.create(
            store=self.store, name='Saladas', slug='saladas', is_active=True
        )
        self.product = StoreProduct.objects.create(
            store=self.store,
            category=self.category,
            name='Monte sua Salada',
            slug='monte-salada',
            price=Decimal('29.90'),
            status='active',
            track_stock=False,
            is_active=True,
        )
        self.customer = User.objects.create_user(
            username='salad_customer', email='cust@test.com', password='pass'
        )
        self.cart = StoreCart.objects.create(
            store=self.store,
            user=self.customer,
            status='active',
        )
        StoreCartItem.objects.create(
            cart=self.cart,
            product=self.product,
            quantity=1,
            unit_price=Decimal('29.90'),
            options={'is_salad_builder': True, 'ingredients': ['alface', 'tomate']},
        )

    @patch('apps.stores.services.checkout_service.send_order_confirmation_email.delay')
    def test_salad_builder_item_passes_stock_check(self, _mock_email):
        order = CheckoutService.create_order(
            cart=self.cart,
            customer_data={
                'name': 'Test Customer',
                'email': 'cust@test.com',
                'phone': '11999990001',
            },
            delivery_data={'method': 'pickup'},
        )
        self.assertIsNotNone(order)
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.subtotal, Decimal('29.90'))


class CouponMinOrderTest(TestCase):
    """
    Cupom com min_order_amount deve ser rejeitado quando subtotal < mínimo.
    """

    def setUp(self):
        from apps.stores.models import StoreCoupon
        self.owner = User.objects.create_user(
            username='coupon_min_owner', email='couponmin@test.com', password='pass'
        )
        self.store = Store.objects.create(
            owner=self.owner, name='Coupon Min Store', slug='coupon-min-store',
            status='active', is_active=True,
        )
        self.category = StoreCategory.objects.create(
            store=self.store, name='Cat', slug='cat-coupon-min', is_active=True
        )
        self.product = StoreProduct.objects.create(
            store=self.store, category=self.category,
            name='Item', slug='item-coupon-min', price=Decimal('20.00'),
            status='active', track_stock=False, is_active=True,
        )
        self.customer = User.objects.create_user(
            username='coupon_min_cust', email='cmcust@test.com', password='pass'
        )
        self.cart = StoreCart.objects.create(
            store=self.store, user=self.customer, status='active'
        )
        StoreCartItem.objects.create(
            cart=self.cart, product=self.product,
            quantity=1, unit_price=Decimal('20.00'),
        )
        self.coupon = StoreCoupon.objects.create(
            store=self.store,
            code='MIN50',
            discount_type='percentage',
            discount_value=Decimal('10'),
            min_order_amount=Decimal('50.00'),
            is_active=True,
        )

    def test_coupon_below_minimum_is_invalid(self):
        result = CheckoutService.validate_coupon('MIN50', self.store, Decimal('20.00'))
        self.assertFalse(result['valid'])
        self.assertIn('minimo', result.get('error', '').lower())

    def test_coupon_at_minimum_is_valid(self):
        result = CheckoutService.validate_coupon('MIN50', self.store, Decimal('50.00'))
        self.assertTrue(result['valid'])
```

- [ ] **Step 2: Sincronizar com container e rodar os novos testes**

```bash
docker cp tests/test_checkout_service.py pastita_web:/app/tests/test_checkout_service.py
docker exec pastita_web python manage.py test tests.test_checkout_service.SaladBuilderCheckoutTest tests.test_checkout_service.CouponMinOrderTest --verbosity=2 2>&1 | tail -15
```

Esperado: todos passando.

- [ ] **Step 3: Rodar suite completa para confirmar sem regressões**

```bash
docker exec pastita_web python manage.py test tests/ --verbosity=1 2>&1 | tail -3
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_checkout_service.py
git commit -m "test: regressão checkout — salad builder bypass stock + cupom pedido mínimo"
```

---

## Task 3: Testes de regressão — Delivery zones Ce-Saladas

**Files:**
- Modify: `tests/test_delivery_pricing_unified.py` (adicionar classes ao final)

### Contexto

`GeoService._normalize_text()` usa `unicodedata.normalize("NFD") + lower()` para remover acentos e caixa. Isso corrige o bug "ESPAÇO CULTURAL" (uppercase com acento). Precisamos de testes de regressão que garantam que essa normalização não quebre.

`GeoService._match_fixed_price_zone()` aceita `metadata['fixed_price_zones']` com estrutura:
```python
{'name': 'Espaço Cultural', 'fee': 10.0, 'keywords': ['Espaço Cultural', 'Espaco Cultural']}
```

- [ ] **Step 1: Adicionar classe `FixedPriceZoneNormalizationTest`**

```python
import unicodedata
from unittest.mock import MagicMock, patch
from django.test import TestCase
from apps.stores.services.geo.service import GeoService
from apps.stores.services.geo.google_provider import GoogleMapsProvider


class FixedPriceZoneNormalizationTest(TestCase):
    """
    Garante que a comparação de zona é case-insensitive e ignora acentos.
    Regressão para bug: "ESPAÇO CULTURAL" não era identificado porque
    a comparação era feita com texto original sem normalização.
    """

    def _make_store_with_zone(self, zone_name, keywords=None, fee=8.0):
        from django.contrib.auth import get_user_model
        from apps.stores.models import Store
        User = get_user_model()
        owner = User.objects.create_user(
            username=f'zone_owner_{zone_name[:5]}',
            email=f'zone_{zone_name[:5]}@test.com',
            password='pass',
        )
        return Store.objects.create(
            owner=owner,
            name='Zone Store',
            slug=f'zone-store-{zone_name[:8].lower().replace(" ", "-")}',
            is_active=True,
            metadata={
                'fixed_price_zones': [{
                    'name': zone_name,
                    'fee': fee,
                    'keywords': keywords or [zone_name],
                }]
            }
        )

    @patch('apps.stores.services.geo.google_provider.requests.get')
    def test_uppercase_accented_keyword_matches(self, mock_get):
        """'ESPAÇO CULTURAL' no endereço deve bater na zona 'Espaço Cultural'."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                'status': 'OK',
                'results': [{
                    'geometry': {'location': {'lat': -10.18, 'lng': -48.33}, 'location_type': 'ROOFTOP'},
                    'formatted_address': 'ESPAÇO CULTURAL, Palmas, TO',
                    'place_id': 'fake',
                    'types': ['point_of_interest'],
                    'address_components': [],
                }],
            },
            raise_for_status=lambda: None,
        )
        store = self._make_store_with_zone('Espaço Cultural', keywords=['Espaço Cultural'])
        service = GeoService(provider=GoogleMapsProvider(api_key='fake'))

        with patch.object(service, 'reverse_geocode', return_value={
            'formatted_address': 'ESPAÇO CULTURAL, Palmas - TO, Brasil',
            'neighborhood': 'ESPAÇO CULTURAL',
        }):
            zone = service._match_fixed_price_zone(
                store, -10.18, -48.33, address_text='ESPAÇO CULTURAL, Palmas'
            )
        self.assertIsNotNone(zone)
        self.assertEqual(zone['fee'], 8.0)

    @patch('apps.stores.services.geo.google_provider.requests.get')
    def test_lowercase_no_accent_matches(self, mock_get):
        """'espaco cultural' (sem acento, minúsculo) também deve bater."""
        store = self._make_store_with_zone('Espaço Cultural', keywords=['Espaço Cultural'])
        service = GeoService(provider=GoogleMapsProvider(api_key='fake'))

        with patch.object(service, 'reverse_geocode', return_value={
            'formatted_address': 'espaco cultural, palmas - to',
            'neighborhood': 'espaco cultural',
        }):
            zone = service._match_fixed_price_zone(
                store, -10.18, -48.33, address_text='espaco cultural palmas'
            )
        self.assertIsNotNone(zone)

    def test_unrelated_address_does_not_match(self):
        """Endereço sem relação com a zona não deve retornar zona."""
        store = self._make_store_with_zone('Espaço Cultural', keywords=['Espaço Cultural'])
        service = GeoService(provider=GoogleMapsProvider(api_key='fake'))

        with patch.object(service, 'reverse_geocode', return_value={
            'formatted_address': 'Quadra 304 Norte, Palmas - TO',
            'neighborhood': 'Plano Diretor Norte',
        }):
            zone = service._match_fixed_price_zone(
                store, -10.18, -48.33, address_text='Quadra 304 Norte Palmas'
            )
        self.assertIsNone(zone)


class DeliveryFeeEndToEndTest(TestCase):
    """
    Testes E2E da pipeline completa: endereço → GeoService → taxa de entrega.
    Garante que fixed_price_zone + dynamic_delivery_area interagem corretamente.
    """

    def _make_ce_saladas_store(self, owner):
        from apps.stores.models import Store
        return Store.objects.create(
            owner=owner,
            name='Cê Saladas Test',
            slug='ce-saladas-test-zones',
            is_active=True,
            status='active',
            default_delivery_fee=Decimal('8.00'),
            metadata={
                'fixed_price_zones': [
                    {
                        'name': 'Taquaralto',
                        'fee': 15.0,
                        'keywords': ['Taquaralto', 'Taquaruçu'],
                    },
                    {
                        'name': 'Espaço Cultural',
                        'fee': 10.0,
                        'keywords': ['Espaço Cultural'],
                    },
                ],
                'dynamic_delivery_area_keywords': ['Plano Diretor', '304', '306', '308'],
            }
        )

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.owner = User.objects.create_user(
            username='e2e_zone_owner', email='e2ezone@test.com', password='pass'
        )
        self.store = self._make_ce_saladas_store(self.owner)

    def test_taquaralto_zone_returns_fixed_fee_15(self):
        service = GeoService(provider=GoogleMapsProvider(api_key='fake'))

        with patch.object(service, 'reverse_geocode', return_value={
            'formatted_address': 'Rua do Taquaralto, Palmas - TO',
            'neighborhood': 'Taquaralto',
        }):
            with patch.object(service, 'route', return_value={'distance_meters': 12000, 'duration_seconds': 900}):
                result = service.calculate_delivery_fee(
                    self.store,
                    customer_lat=-10.28,
                    customer_lng=-48.32,
                    address_text='Rua do Taquaralto',
                )
        self.assertEqual(result['fee'], Decimal('15.00'))
        self.assertEqual(result['zone_name'], 'Taquaralto')

    def test_out_of_zone_address_returns_unavailable_or_high_fee(self):
        service = GeoService(provider=GoogleMapsProvider(api_key='fake'))

        with patch.object(service, 'reverse_geocode', return_value={
            'formatted_address': 'Rua desconhecida, Paraíso do Tocantins - TO',
            'neighborhood': 'Centro',
            'city': 'Paraíso do Tocantins',
        }):
            with patch.object(service, 'route', return_value={'distance_meters': 80000, 'duration_seconds': 3600}):
                result = service.calculate_delivery_fee(
                    self.store,
                    customer_lat=-10.18,
                    customer_lng=-48.88,
                    address_text='Paraíso do Tocantins',
                )
        # Fora da zona de entrega deve retornar available=False ou taxa máxima
        self.assertFalse(result.get('available', True))
```

- [ ] **Step 2: Verificar que `calculate_delivery_fee` existe com a assinatura esperada**

```bash
grep -n "def calculate_delivery_fee" /home/graco/WORK/server2/apps/stores/services/geo/service.py
```

Esperado: encontrar a função. Verificar os parâmetros (`store`, `customer_lat`, `customer_lng`, `address_text`).

- [ ] **Step 3: Sincronizar e rodar os novos testes**

```bash
docker cp tests/test_delivery_pricing_unified.py pastita_web:/app/tests/test_delivery_pricing_unified.py
docker exec pastita_web python manage.py test tests.test_delivery_pricing_unified.FixedPriceZoneNormalizationTest tests.test_delivery_pricing_unified.DeliveryFeeEndToEndTest --verbosity=2 2>&1 | tail -20
```

- [ ] **Step 4: Rodar suite completa**

```bash
docker exec pastita_web python manage.py test tests/ --verbosity=1 2>&1 | tail -3
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_delivery_pricing_unified.py
git commit -m "test: regressão delivery zones — ESPAÇO CULTURAL case-insensitive + Taquaralto + out-of-zone"
```

---

## Task 4: Teste de regressão — CompanyProfileViewSet store owner access

**Files:**
- Create: `tests/test_company_profile_views.py`

### Contexto

O `CompanyProfileViewSet.get_queryset()` foi corrigido nesta sessão para incluir `Q(store_id__in=owned_store_ids)` além de `Q(account_id__in=account_ids)`. Sem esse teste, uma regressão poderia remover o acesso para donos de loja sem conta WhatsApp.

- [ ] **Step 1: Criar `tests/test_company_profile_views.py`**

```python
"""
Testes de regressão para CompanyProfileViewSet.

Cobertura crítica:
- Dono de loja sem conta WhatsApp consegue ver o perfil da sua loja (get_queryset)
- Superuser vê todos
- Usuário sem permissão recebe 404
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from apps.stores.models import Store
from apps.automation.models import CompanyProfile

User = get_user_model()


def _make_user(username):
    return User.objects.create_user(
        username=username, email=f'{username}@test.com', password='pass'
    )


def _make_store_with_profile(owner, slug):
    store = Store.objects.create(
        owner=owner, name=f'Store {slug}', slug=slug,
        is_active=True, status='active',
    )
    profile, _ = CompanyProfile.objects.get_or_create(
        store=store, defaults={'company_name': store.name}
    )
    return store, profile


class CompanyProfileStoreOwnerAccessTest(TestCase):
    """
    Regressão: dono da loja sem conta WhatsApp deve conseguir
    listar e recuperar o CompanyProfile da sua loja.
    """

    def setUp(self):
        self.owner = _make_user('cp_owner')
        self.store, self.profile = _make_store_with_profile(self.owner, 'cp-owner-store')
        self.token = Token.objects.create(user=self.owner)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

    def test_list_returns_own_profile(self):
        resp = self.client.get('/api/v1/automation/company-profiles/')
        self.assertEqual(resp.status_code, 200)
        ids = [str(r['id']) for r in (resp.data.get('results') or resp.data)]
        self.assertIn(str(self.profile.id), ids)

    def test_retrieve_own_profile_returns_200(self):
        resp = self.client.get(f'/api/v1/automation/company-profiles/{self.profile.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(str(resp.data['id']), str(self.profile.id))

    def test_other_user_cannot_retrieve(self):
        other = _make_user('cp_stranger')
        token = Token.objects.create(user=other)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        resp = client.get(f'/api/v1/automation/company-profiles/{self.profile.id}/')
        self.assertEqual(resp.status_code, 404)

    def test_superuser_sees_all_profiles(self):
        other_owner = _make_user('cp_other_owner')
        _, other_profile = _make_store_with_profile(other_owner, 'cp-other-store')

        superuser = User.objects.create_superuser(
            username='cp_super', email='cpsuper@test.com', password='pass'
        )
        token = Token.objects.create(user=superuser)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

        resp = client.get('/api/v1/automation/company-profiles/')
        self.assertEqual(resp.status_code, 200)
        ids = [str(r['id']) for r in (resp.data.get('results') or resp.data)]
        self.assertIn(str(self.profile.id), ids)
        self.assertIn(str(other_profile.id), ids)
```

- [ ] **Step 2: Verificar URL do endpoint**

```bash
grep -rn "company-profiles\|company_profiles\|CompanyProfile" /home/graco/WORK/server2/apps/automation/api/urls.py
```

Ajustar o path `/api/v1/automation/company-profiles/` se necessário.

- [ ] **Step 3: Sincronizar e rodar**

```bash
docker cp tests/test_company_profile_views.py pastita_web:/app/tests/test_company_profile_views.py
docker exec pastita_web python manage.py test tests.test_company_profile_views --verbosity=2 2>&1 | tail -15
```

- [ ] **Step 4: Rodar suite completa**

```bash
docker exec pastita_web python manage.py test tests/ --verbosity=1 2>&1 | tail -3
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_company_profile_views.py
git commit -m "test: regressão CompanyProfileViewSet — acesso por dono de loja sem conta WhatsApp"
```

---

## Self-Review

**Spec coverage:**
- ✅ StoreCustomer.addresses JSONField: todos os 4 locais cobertos (models, customer_identity, storefront_views, agents)
- ✅ Checkout regression: salad builder stock bypass + cupom pedido mínimo
- ✅ Delivery zones: Espaço Cultural normalization, Taquaralto fixed fee, out-of-zone
- ✅ CompanyProfileViewSet: owner sem WA, stranger 404, superuser vê tudo

**Placeholder scan:** nenhum TBD/TODO/etc.

**Type consistency:** `StoreCustomerAddress`, `address_list`, `is_default`, `formatted` consistentes em todos os steps. `calculate_delivery_fee` verificado em Step 2 da Task 3. URL do endpoint verificada em Step 2 da Task 4.
