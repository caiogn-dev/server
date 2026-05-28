# Plano de Implementação: CRM / PDV / WhatsApp Tools
**Data:** 2026-05-28  
**Spec:** `docs/superpowers/specs/2026-05-27-crm-pdv-whatsapp-design.md`  
**Projetos:** `server2` (backend) + `pastita-dash` (frontend)  
**Branch base:** `development` em ambos os repos

---

## Padrões descobertos (Phase 0)

| Padrão | Fonte | Usar em |
|--------|-------|---------|
| `TenantModel` (UUID pk, tenant FK, created_by, updated_by, timestamps) | `apps/core/models.py:146-183` | `StoreTeamMember`, `UserAddress` |
| `StorePermissionMixin` + `StoreQuerysetMixin` | `apps/core/permissions.py:229-285` | Todos os ViewSets CRM |
| `IsStoreOwnerOrStaff` — verifica `store.owner` ou `store.staff.all()` | `apps/stores/api/views/base.py:22-62` | Atualizar para checar `StoreTeamMember` |
| ViewSet: `StoreQuerysetMixin + viewsets.ModelViewSet` | `apps/stores/api/views/order_views.py:35-41` | ViewSets CRM/PDV |
| Serializer split: `{Model}Serializer` / `{Model}CreateSerializer` | `apps/stores/api/serializers.py:23+` | Todos os serializers |
| Nested router via `rest_framework_nested` | `apps/stores/urls.py:50-89` | Rotas CRM aninhadas |
| Lookup UUID + slug: try/except `uuid.UUID(param)` | `apps/stores/api/views/order_views.py:43-52` | Views CRM |
| `UnifiedUser` — identidade do cliente (phone + email) | `apps/users/models.py:12-48` | `UserAddress`, busca PDV |

---

## Fase 1 — Modelos de banco e migrações
**Branch:** `feature/crm-models`  
**Projetos:** `server2` apenas

### Tarefas

**1.1 — `StoreTeamMember` model**

Arquivo: `apps/stores/models/team.py` (novo)

```python
# Herda TenantModel (apps/core/models.py:146) — pega UUID pk, tenant FK, created_by, updated_by
class StoreTeamMember(TenantModel):
    class Role(models.TextChoices):
        OWNER    = 'owner',    'Dono'
        MANAGER  = 'manager',  'Gerente'
        OPERATOR = 'operator', 'Operador'
        VIEWER   = 'viewer',   'Visualizador'

    user       = FK(User, related_name='store_memberships', on_delete=CASCADE)
    role       = CharField(max_length=20, choices=Role.choices, default=Role.OPERATOR)
    is_active  = BooleanField(default=True)
    invited_by = FK(User, null=True, blank=True, on_delete=SET_NULL,
                    related_name='sent_invitations')

    class Meta:
        db_table = 'store_team_members'
        unique_together = [('tenant', 'user')]   # tenant = store (de TenantModel)
        indexes = [Index(fields=['tenant', 'role']), Index(fields=['user', 'is_active'])]
```

**1.2 — `UserAddress` model**

Arquivo: `apps/users/models.py` (adicionar classe)

```python
class UserAddress(TenantModel):
    unified_user = FK(UnifiedUser, related_name='addresses', on_delete=CASCADE)
    label        = CharField(max_length=50, default='Casa')
    street       = CharField(max_length=255, blank=True)
    number       = CharField(max_length=20, blank=True)
    neighborhood = CharField(max_length=100, blank=True)
    city         = CharField(max_length=100)
    state        = CharField(max_length=2)
    zip_code     = CharField(max_length=10, blank=True)
    lat          = DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng          = DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_default   = BooleanField(default=False)

    class Meta:
        db_table = 'user_addresses'
        ordering = ['-is_default', '-created_at']
        indexes = [Index(fields=['unified_user', 'tenant']),
                   Index(fields=['unified_user', 'is_default'])]
```

**1.3 — Campos novos em `Order`**

Arquivo: `apps/stores/models/order.py` (adicionar campos)

```python
manual_discount_type   = CharField(max_length=10, choices=[('percent','%'),('fixed','R$')],
                                   null=True, blank=True)
manual_discount_value  = DecimalField(max_digits=8, decimal_places=2, default=0)
manual_discount_reason = CharField(max_length=255, blank=True)
surcharge_value        = DecimalField(max_digits=8, decimal_places=2, default=0)
surcharge_reason       = CharField(max_length=255, blank=True)
created_by_staff       = FK(User, null=True, blank=True, on_delete=SET_NULL,
                            related_name='created_orders')
```

**1.4 — Adicionar `StoreTeamMember` ao `__init__.py` de models**

Arquivo: `apps/stores/models/__init__.py` — exportar `StoreTeamMember`

**1.5 — Gerar e aplicar migrations**

```bash
docker compose exec web python manage.py makemigrations stores users
docker compose exec web python manage.py migrate
```

**1.6 — Data migration: `Store.staff` → `StoreTeamMember`**

Arquivo: `apps/stores/migrations/XXXX_migrate_staff_to_team_members.py`

```python
def migrate_staff(apps, schema_editor):
    Store = apps.get_model('stores', 'Store')
    StoreTeamMember = apps.get_model('stores', 'StoreTeamMember')
    for store in Store.objects.all():
        # Owner
        StoreTeamMember.objects.get_or_create(
            tenant=store, user=store.owner,
            defaults={'role': 'owner'}
        )
        # Staff (sem role específico → operator)
        for user in store.staff.all():
            if user != store.owner:
                StoreTeamMember.objects.get_or_create(
                    tenant=store, user=user,
                    defaults={'role': 'operator'}
                )
```

### Verificação da Fase 1

```bash
# Confirmar tabelas criadas
docker compose exec web python manage.py shell -c "
from apps.stores.models import StoreTeamMember
from apps.users.models import UserAddress
print('StoreTeamMember count:', StoreTeamMember.objects.count())
print('UserAddress table OK')
"
# Confirmar data migration
docker compose exec web python manage.py shell -c "
from apps.stores.models import StoreTeamMember
print(StoreTeamMember.objects.values('role').distinct())
"
```

---

## Fase 2 — Sistema de permissões por role
**Branch:** `feature/crm-permissions` (a partir de `feature/crm-models`)  
**Projetos:** `server2` apenas

### Tarefas

**2.1 — Helper `has_store_permission()`**

Arquivo: `apps/stores/permissions.py` (novo)

```python
ROLE_PERMISSIONS = {
    'owner':    {'catalog','orders','cancel_order','reports','team','whatsapp','config'},
    'manager':  {'catalog','orders','cancel_order','reports','whatsapp'},
    'operator': {'orders','reports'},
    'viewer':   {'reports'},
}

def get_member_role(user, store) -> str | None:
    """Returns role string or None if not a member."""
    from apps.stores.models import StoreTeamMember
    if user.is_superuser or user.is_staff:
        return 'owner'
    member = StoreTeamMember.objects.filter(
        tenant=store, user=user, is_active=True
    ).first()
    return member.role if member else None

def has_store_permission(user, store, action: str) -> bool:
    role = get_member_role(user, store)
    if not role:
        return False
    return action in ROLE_PERMISSIONS.get(role, set())
```

**2.2 — Atualizar `IsStoreOwnerOrStaff`**

Arquivo: `apps/stores/api/views/base.py` — método `_user_can_access_store`

Adicionar fallback para `StoreTeamMember` após checar `store.owner` e `store.staff`:
```python
# Após checar store.owner e store.staff.all():
from apps.stores.permissions import get_member_role
if get_member_role(user, store) is not None:
    return True
```

**2.3 — Decorator `@require_store_permission(action)`**

Arquivo: `apps/stores/permissions.py` (adicionar)

```python
def require_store_permission(action):
    def decorator(view_func):
        def wrapper(self, request, *args, **kwargs):
            store = self.get_store()  # ViewSet deve implementar get_store()
            if not has_store_permission(request.user, store, action):
                raise PermissionDenied()
            return view_func(self, request, *args, **kwargs)
        return wrapper
    return decorator
```

### Verificação da Fase 2

```bash
docker compose exec web python manage.py shell -c "
from apps.stores.models import Store
from apps.stores.permissions import has_store_permission
from django.contrib.auth import get_user_model
User = get_user_model()
store = Store.objects.first()
owner = store.owner
print('owner can manage team:', has_store_permission(owner, store, 'team'))
print('owner can create orders:', has_store_permission(owner, store, 'orders'))
"
```

---

## Fase 3 — APIs CRM (server2)
**Branch:** `feature/crm-apis` (a partir de `feature/crm-permissions`)  
**Projetos:** `server2` apenas

### Tarefas

**3.1 — API de busca de clientes**

Arquivo: `apps/stores/api/views/crm_views.py` (novo)

```python
class CustomerSearchView(APIView):
    """GET /api/v1/stores/{store_slug}/crm/customers/search/?q=<texto>&limit=8"""
    permission_classes = [IsAuthenticated, IsStoreOwnerOrStaff]

    def get(self, request, store_slug):
        store = get_object_or_404(Store, slug=store_slug)
        q = request.query_params.get('q', '').strip()
        limit = min(int(request.query_params.get('limit', 8)), 20)
        
        if len(q) < 2:
            return Response([])
        
        users = UnifiedUser.objects.filter(
            Q(name__icontains=q) | Q(phone_number__icontains=q)
        ).prefetch_related(
            Prefetch('addresses', queryset=UserAddress.objects.filter(tenant=store))
        )[:limit]
        
        return Response(CustomerSearchSerializer(users, many=True,
                        context={'store': store}).data)
```

Serializer retorna: `id, name, phone_number, email, total_orders, total_spent, last_order_at, addresses[]`

**3.2 — API de endereços do cliente**

```
GET  /api/v1/stores/{slug}/crm/customers/{user_id}/addresses/
POST /api/v1/stores/{slug}/crm/customers/{user_id}/addresses/
PATCH /api/v1/stores/{slug}/crm/customers/{user_id}/addresses/{id}/
```

ViewSet `CustomerAddressViewSet` com `StorePermissionMixin`. `perform_create` seta `unified_user` e `tenant`.

**3.3 — API de equipe**

```
GET    /api/v1/stores/{slug}/team/         → lista StoreTeamMember
POST   /api/v1/stores/{slug}/team/         → cria (role 'owner' obrigatório para criar)
PATCH  /api/v1/stores/{slug}/team/{id}/    → altera role
DELETE /api/v1/stores/{slug}/team/{id}/    → is_active=False (soft delete)
```

`TeamMemberViewSet` — `perform_create` verifica `has_store_permission(request.user, store, 'team')`.

**3.4 — API Places para admin**

Arquivo: `apps/stores/api/views/admin_views.py`

```python
@api_view(['GET'])
@permission_classes([IsAdminUser])
def places_search(request):
    """GET /api/v1/admin/places-search/?q=<texto>"""
    q = request.query_params.get('q', '')
    provider = GoogleMapsProvider()
    results = provider.search_places(q)  # novo método (ver 3.5)
    return Response(results)
```

**3.5 — `GoogleMapsProvider.search_places()`**

Arquivo: `apps/stores/services/geo/google_provider.py`

```python
GOOGLE_PLACES_TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"

def search_places(self, query: str, *, types: str = "establishment") -> List[Dict]:
    """Text search for business establishment (for admin store setup)."""
    params = {
        'query': query,
        'key': self.api_key,
        'language': 'pt-BR',
        'region': 'br',
        'type': types,
    }
    response = requests.get(GOOGLE_PLACES_TEXT_SEARCH_URL, params=params, timeout=10)
    response.raise_for_status()
    payload = response.json()
    
    results = []
    for place in payload.get('results', [])[:5]:
        loc = place.get('geometry', {}).get('location', {})
        results.append({
            'place_id':          place.get('place_id'),
            'name':              place.get('name'),
            'formatted_address': place.get('formatted_address'),
            'lat':               loc.get('lat'),
            'lng':               loc.get('lng'),
            'phone':             place.get('formatted_phone_number', ''),
            'website':           place.get('website', ''),
        })
    return results
```

**3.6 — Registrar URLs CRM**

Arquivo: `apps/stores/urls.py` — adicionar ao nested router:

```python
stores_router.register(r'crm/customers', CustomerViewSet, basename='store-crm-customers')
# + CustomerSearchView como path separado
path('<slug:store_slug>/crm/customers/search/', CustomerSearchView.as_view()),
path('<slug:store_slug>/team/', include(team_router.urls)),
path('admin/places-search/', places_search),
```

### Verificação da Fase 3

```bash
# Com token válido de owner:
curl -H "Authorization: Token <token>" \
  "http://localhost:8000/api/v1/stores/ce-saladas/crm/customers/search/?q=caio"

curl -H "Authorization: Token <token>" \
  "http://localhost:8000/api/v1/stores/ce-saladas/team/"
```

---

## Fase 4 — Django Unfold (admin customizado)
**Branch:** `feature/django-unfold` (a partir de `feature/crm-apis`)  
**Projetos:** `server2` apenas

### Tarefas

**4.1 — Instalar django-unfold**

```bash
# No Dockerfile.prod ou requirements.txt:
django-unfold>=0.40.0
```

`config/settings/base.py` — adicionar antes de `django.contrib.admin`:
```python
INSTALLED_APPS = [
    'unfold',
    'unfold.contrib.filters',
    'django.contrib.admin',
    ...
]
```

**4.2 — Configuração Unfold**

`config/settings/base.py`:
```python
UNFOLD = {
    "SITE_TITLE": "Cardapidex Admin",
    "SITE_HEADER": "Cardapidex",
    "SITE_URL": "/",
    "SITE_ICON": lambda request: static("img/cardapidex-logo.svg"),
    "COLORS": {
        "primary": {"500": "16 185 129"},  # verde Cardapidex
    },
    "SIDEBAR": {
        "navigation": [
            {"title": "Lojas", "icon": "store", "link": "/django-admin/stores/store/"},
            {"title": "Usuários", "icon": "people", "link": "/django-admin/auth/user/"},
            {"title": "Pedidos", "icon": "shopping_bag", "link": "/django-admin/stores/storeorder/"},
        ]
    }
}
```

**4.3 — `StoreAdmin` com PlacesSearchWidget**

Arquivo: `apps/stores/admin.py`

- `ModelAdmin` herda `UnfoldModelAdmin`
- Fieldsets: Info Básica / Localização / Entrega / WhatsApp / Equipe
- Inline `StoreTeamMemberInline` 
- Widget customizado `PlacesSearchWidget` no campo `address` — JavaScript que chama `/api/v1/admin/places-search/` e preenche `lat`, `lng`, `city`, `state`
- Ação "Ver no pastita-dash" → link para `/stores/{slug}/`

**4.4 — `UserAdmin` com StoreTeamMemberInline**

Arquivo: `apps/users/admin.py` (ou `apps/stores/admin.py`)

- Inline tabular de `StoreTeamMember`
- Mostra: loja, role, ativo, convidado por
- Botão "Adicionar a loja" no topo

**4.5 — URL do admin via env var**

`config/settings/base.py`:
```python
ADMIN_URL = os.environ.get('DJANGO_ADMIN_URL', 'django-admin') + '/'
```

`config/urls.py`:
```python
path(settings.ADMIN_URL, admin.site.urls),
```

### Verificação da Fase 4

```bash
docker compose up -d --build
# Acessar http://localhost:80/django-admin/
# Confirmar: sidebar, tema verde, inline equipe na tela de Store
```

---

## Fase 5 — pastita-dash: PDV (Novo Pedido)
**Branch:** `feature/pdv-new-order` em `pastita-dash`  
**Projetos:** `pastita-dash` apenas

### Tarefas

**5.1 — Serviço de API CRM**

Arquivo: `src/services/crmApi.ts`

```typescript
export interface CustomerSearchResult {
  id: string;
  name: string;
  phone_number: string;
  email?: string;
  total_orders: number;
  total_spent: number;
  addresses: UserAddress[];
}

export const searchCustomers = (storeSlug: string, q: string) =>
  api.get<CustomerSearchResult[]>(`/stores/${storeSlug}/crm/customers/search/`, { params: { q } });

export const saveAddress = (storeSlug: string, userId: string, address: Partial<UserAddress>) =>
  api.post(`/stores/${storeSlug}/crm/customers/${userId}/addresses/`, address);
```

**5.2 — Hook `useCustomerSearch`**

Arquivo: `src/hooks/useCustomerSearch.ts`

- Debounce 300ms
- Estado: `query`, `results`, `loading`, `selectedCustomer`
- `selectCustomer(customer)` → popula formulário

**5.3 — Componente `NewOrderDrawer`**

Arquivo: `src/components/orders/NewOrderDrawer.tsx`

Steps (Stepper):
1. **Cliente** — `CustomerSearchInput` (busca + seleção ou "novo cliente")
2. **Entrega** — seleção de endereço salvo OU autocomplete Places → cálculo de rota automático
3. **Itens** — `ProductSearchInput` + carrinho inline
4. **Desconto/Acréscimo** — campos opcionais (tipo + valor + motivo)
5. **Pagamento** — PIX / Dinheiro / Cartão / Fiado
6. **Confirmar** — resumo completo com total

**5.4 — Integração com OrdersPage**

- Botão "Novo Pedido" (atalho `N`) abre `NewOrderDrawer`
- Após confirmar → invalidar query `orders` → pedido aparece no board em tempo real

**5.5 — `CustomerSearchInput`**

Arquivo: `src/components/crm/CustomerSearchInput.tsx`

- Input com debounce 300ms
- Dropdown com resultados (nome, telefone, total pedidos)
- Opção "Criar cliente" se não encontrar
- Ao selecionar: emite `onSelect(customer)` para o Drawer

### Verificação da Fase 5

```bash
cd pastita-dash && npm run build  # zero erros TypeScript
# Manual: abrir Novo Pedido, buscar "Caio", selecionar, preencher itens, confirmar
# Verificar: pedido aparece no board sem reload
```

---

## Fase 6 — pastita-dash: WhatsApp chat painel lateral
**Branch:** `feature/whatsapp-chat-tools` em `pastita-dash`  
**Projetos:** `pastita-dash` apenas

### Tarefas

**6.1 — `CustomerPanel` (painel lateral)**

Arquivo: `src/components/chat/CustomerPanel.tsx`

Seções:
- Header: nome, telefone, total gasto, pedidos
- Endereços salvos (lista com label)
- Pedido ativo (status + valor)
- Ações rápidas: botões com ícones

**6.2 — Integração com `ChatWindow`**

- Detectar `unified_user` da conversa via WebSocket context
- Chamar `GET /stores/{slug}/crm/customers/{id}/` quando conversa abre
- Painel desliza da direita (collapsed por default, toggle no header)

**6.3 — Ação "Novo Pedido" inline**

- Botão "📦 Novo Pedido" no painel → abre `NewOrderDrawer` (Fase 5) pré-preenchido com o cliente da conversa
- Endereço da conversa (se capturado pelo bot) aparece pré-selecionado

**6.4 — Ações rápidas**

- `📍 Enviar localização` → envia mensagem com coordenadas da loja via WhatsApp API
- `💳 Gerar link PIX` → abre modal com valor, gera link via `POST /stores/{slug}/payments/pix-link/`
- `✅ Confirmar pedido` → PATCH no pedido ativo para `status=confirmed`
- `❌ Cancelar pedido` → PATCH para `status=cancelled` com confirm modal

**6.5 — Templates WhatsApp**

Arquivo: `src/components/chat/TemplateSelector.tsx`

- Lista templates aprovados via `GET /stores/{slug}/whatsapp/templates/`
- Preview com variáveis editáveis
- Envio via botão "Enviar template"
- Toast de confirmação

### Verificação da Fase 6

```bash
npm run build  # zero erros
# Manual: abrir conversa, confirmar painel lateral com dados do cliente
# Testar: enviar template, clicar Novo Pedido inline
```

---

## Fase 7 — WhatsApp bot: pin → UserAddress automático
**Branch:** `feature/whatsapp-pin-address` (a partir de `feature/crm-apis`)  
**Projetos:** `server2` apenas

### Tarefas

**7.1 — Detectar mensagem tipo `location` no webhook**

Arquivo: `apps/automation/services/message_handler.py` (ou equivalente)

Quando `message.type == 'location'`:
1. `lat, lng = message.location.latitude, message.location.longitude`
2. `reverse_geocode(lat, lng)` → endereço
3. Buscar `UnifiedUser` pelo telefone do remetente
4. `UserAddress.objects.update_or_create(unified_user=user, tenant=store, label='WhatsApp', defaults={...})`

**7.2 — Emitir WebSocket para o dashboard**

Após salvar `UserAddress`:
```python
channel_layer.group_send(f'store_{store.slug}_chat', {
    'type': 'customer.address.updated',
    'user_id': str(unified_user.id),
    'address': UserAddressSerializer(address).data,
})
```

`ChatConsumer` trata `customer.address.updated` → pastita-dash atualiza painel lateral sem reload.

### Verificação da Fase 7

```bash
# Simular mensagem de localização via webhook de teste:
curl -X POST http://localhost:8000/webhooks/v1/whatsapp \
  -H "Content-Type: application/json" \
  -d '{"entry":[{"changes":[{"value":{"messages":[{"type":"location","from":"5563999999999","location":{"latitude":-10.19,"longitude":-48.33}}]}}]}]}' 
# Confirmar UserAddress criado:
docker compose exec web python manage.py shell -c "
from apps.users.models import UserAddress
print(UserAddress.objects.last())
"
```

---

## Fase 8 — Verificação e testes de integração

### Checklist final

```bash
# Testes server2
docker compose exec web python manage.py test \
  apps.stores.tests.test_crm \
  apps.stores.tests.test_team \
  apps.users.tests.test_addresses

# Build pastita-dash sem erros
cd pastita-dash && npm run build

# Smoke test: criar pedido pelo PDV
# 1. Login no pastita-dash como owner de ce-saladas
# 2. Abrir Novo Pedido → buscar "Caio" → selecionar → endereço 404 Sul
# 3. Confirmar rota calculada (R$10,72 para 404 Sul)
# 4. Adicionar item → confirmar → verificar no board

# Smoke test: admin unfold
# 1. Acessar /django-admin/ como superuser
# 2. Criar loja nova → buscar "Ce Saladas" no campo Places
# 3. Confirmar lat/lng preenchidos automaticamente
```

### Anti-padrões a evitar

- ❌ Não usar `store.staff.all()` direto — sempre usar `has_store_permission()` depois da Fase 2
- ❌ Não herdar `models.Model` nos novos modelos — usar `TenantModel` de `apps/core/models.py:146`
- ❌ Não inventar método `GoogleMapsProvider.find_business()` — o método correto é `search_places()` (criado na Fase 3.5)
- ❌ Não criar novo `axios` instance no pastita-dash — usar o `api` existente em `src/services/api.ts`
- ❌ Não hardcodar `ce-saladas` em nenhum lugar — sempre `store.slug` / `storeSlug` da context

---

## Ordem de execução e dependências

```
Fase 1 (models) → Fase 2 (permissions) → Fase 3 (APIs) → Fase 4 (unfold)
                                        ↘
                                          Fase 5 (PDV dash) → Fase 6 (chat dash)
                                          Fase 7 (pin bot)
                                        ↗
                              (paralelo com Fase 4)
```

Fases 1-3 são pré-requisito de tudo. Fase 5 pode começar após Fase 3 (APIs prontas). Fases 4 e 5 são independentes entre si.
