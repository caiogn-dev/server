# CRM / PDV / WhatsApp Tools — Design Spec
**Data:** 2026-05-27  
**Status:** Aprovado — aguardando plano de implementação  
**Projetos afetados:** `server2` (backend), `pastita-dash` (frontend)

---

## Contexto e motivação

O `pastita-dash` precisa evoluir de um painel de pedidos/WhatsApp para um CRM/ERP/PDV completo. O store owner precisa conseguir criar pedidos presencialmente, gerenciar equipe com papéis definidos, e ter visibilidade total do cliente — tudo sem sair do painel. O Django admin (com django-unfold) é o ponto de gestão da plataforma para o super-admin, sem fragmentar mais projetos.

---

## Módulo 1 — Modelo de dados (DB Layer)

### `StoreTeamMember`

Substitui o M2M `Store.staff` (existe hoje, sem roles). Nova tabela com hierarquia de papéis.

```python
class StoreTeamMember(BaseModel):
    store      = ForeignKey(Store, related_name='team_members', on_delete=CASCADE)
    user       = ForeignKey(User, related_name='store_memberships', on_delete=CASCADE)
    role       = CharField(max_length=20, choices=[
                     ('owner', 'Dono'),
                     ('manager', 'Gerente'),
                     ('operator', 'Operador'),
                     ('viewer', 'Visualizador'),
                 ])
    is_active  = BooleanField(default=True)
    invited_by = ForeignKey(User, null=True, blank=True, on_delete=SET_NULL,
                            related_name='sent_invitations')

    class Meta:
        unique_together = [('store', 'user')]
        db_table = 'store_team_members'
```

### Matriz de permissões por role

| Ação | owner | manager | operator | viewer |
|------|:-----:|:-------:|:--------:|:------:|
| Criar/editar catálogo | ✅ | ✅ | ❌ | ❌ |
| Criar pedido (PDV) | ✅ | ✅ | ✅ | ❌ |
| Cancelar pedido | ✅ | ✅ | ❌ | ❌ |
| Ver relatórios | ✅ | ✅ | ✅ | ✅ |
| Gerenciar equipe | ✅ | ❌ | ❌ | ❌ |
| Gerenciar WhatsApp | ✅ | ✅ | ❌ | ❌ |
| Editar config loja | ✅ | ❌ | ❌ | ❌ |

Permissões verificadas via helper `has_store_permission(user, store, action)` — importado em qualquer view sem acoplamento a content types.

### Migração de dados

Data migration converte o estado atual:
- `Store.staff` (todos) → `StoreTeamMember(role='operator')`
- `Store.owner` → `StoreTeamMember(role='owner')`
- Campo `staff` M2M mantido com `blank=True` (deprecated) — removido em release posterior após validação

### `UserAddress`

Endereços de clientes reutilizáveis pelo PDV e pelo bot/LLM.

```python
class UserAddress(BaseModel):
    unified_user = ForeignKey(UnifiedUser, related_name='addresses', on_delete=CASCADE)
    store        = ForeignKey(Store, on_delete=CASCADE)
    label        = CharField(max_length=50, default='Casa')  # "Casa", "Trabalho", "WhatsApp"
    street       = CharField(max_length=255)
    number       = CharField(max_length=20)
    neighborhood = CharField(max_length=100)
    city         = CharField(max_length=100)
    state        = CharField(max_length=2)
    zip_code     = CharField(max_length=10, blank=True)
    lat          = DecimalField(max_digits=9, decimal_places=6, null=True)
    lng          = DecimalField(max_digits=9, decimal_places=6, null=True)
    is_default   = BooleanField(default=False)

    class Meta:
        db_table = 'user_addresses'
        ordering = ['-is_default', '-created_at']
```

Quando cliente envia pin de localização no WhatsApp → reverse geocode → `UserAddress(label='WhatsApp')` criado automaticamente, disponível no PDV.

### Campos novos em `Order` (acréscimo/desconto manual)

```python
manual_discount_type   = CharField(choices=['percent', 'fixed'], null=True, blank=True)
manual_discount_value  = DecimalField(max_digits=8, decimal_places=2, default=0)
manual_discount_reason = CharField(max_length=255, blank=True)
surcharge_value        = DecimalField(max_digits=8, decimal_places=2, default=0)
surcharge_reason       = CharField(max_length=255, blank=True)
created_by_staff       = ForeignKey(User, null=True, blank=True, on_delete=SET_NULL,
                                    related_name='created_orders')
```

Cálculo: `total = subtotal + delivery_fee + surcharge_value - discount_amount`  
onde `discount_amount = subtotal * (value/100)` se `percent`, ou `value` se `fixed`.

---

## Módulo 2 — Django admin com django-unfold

### Dependência

```
django-unfold  # substitui o admin padrão com UI moderna, zero outros deps
```

### URL do admin

`/django-admin/` configurável via `DJANGO_ADMIN_URL` env var (não exposto em `/admin/`).  
Acesso restrito a `is_staff=True`.

### Sidebar

```
🏪 Lojas
👥 Usuários & Equipe
📦 Pedidos (cross-loja)
💬 Conversas
⚙️  Sistema (Celery tasks, Webhooks)
```

### `StoreAdmin`

- **PlacesSearchWidget**: campo "Buscar no Google Maps" com `type=establishment`
  - Endpoint: `GET /api/v1/admin/places-search/?q=<query>`
  - Backend usa `GoogleMapsProvider` (já existe) + Places Text Search API
  - Ao selecionar: auto-preenche `lat`, `lng`, `address`, `city`, `state`, `phone`, `website`, `operating_hours`
- Inline de `StoreTeamMember`
- Ação "Definir dono" → cria/atualiza membro com `role='owner'`
- Fieldsets: Info básica / Localização / Entrega / Automação / Equipe

### `UserAdmin`

- Inline de `StoreTeamMember` (lojas em que o usuário participa)
- Botão "Adicionar a loja" → modal: seleciona loja + role → cria `StoreTeamMember`

---

## Módulo 3 — PDV / Novo Pedido (pastita-dash)

### Fluxo completo

1. Atendente abre **"Novo Pedido"** (botão no header ou atalho `N`)
2. **Busca cliente**: campo com debounce 300ms — `GET /stores/{slug}/crm/customers/search/?q=<texto>`
   - Pesquisa `UnifiedUser` por `name__icontains` OR `phone_number__icontains`
   - Retorna: nome, telefone, total pedidos, último pedido, endereços salvos
3. **Seleciona cliente** → preenche dados automaticamente
4. **Entrega ou retirada**:
   - Retirada: sem endereço, sem taxa
   - Entrega com endereço salvo: seleciona da lista → calcula rota + taxa automaticamente
   - Entrega com endereço novo: autocomplete Places → confirma → calcula rota → pergunta "Salvar endereço?"
5. **Monta o pedido**: busca produtos por nome, adiciona itens, seleciona variações/combos
6. **Acréscimo/desconto**: campo opcional com tipo (% ou R$) + motivo obrigatório
7. **Revisão**: subtotal / taxa entrega / acréscimo / desconto / **total final**
8. **Pagamento**: PIX, dinheiro, cartão, fiado
9. **Confirma** → `POST /stores/{slug}/orders/` com `created_by_staff` → pedido aparece no board em tempo real

### API de busca de cliente

```
GET /api/v1/stores/{slug}/crm/customers/search/?q=<texto>&limit=8
```

Permissão: `StoreTeamMember` com role `operator` ou superior.

### Endpoint de rota (já existe)

`POST /api/v1/stores/{slug}/route/` → `distance_km` + `delivery_fee` — cache Redis 24h.  
Chamado automaticamente ao confirmar endereço de entrega.

---

## Módulo 4 — WhatsApp chat UI + ferramentas

### Painel lateral do cliente

Exibido ao lado de qualquer conversa ativa:

```
┌─────────────────────────────┐
│ 👤 Caio Nascimento           │
│ 📱 +55 63 9 9999-0000        │
│ 💰 R$342 gastos · 8 pedidos  │
│ 🕐 Último pedido: 2 dias     │
├─────────────────────────────┤
│ ENDEREÇOS SALVOS             │
│ 🏠 404 Sul, 15 (padrão)      │
│ 💼 Av. JK 500, Centro        │
├─────────────────────────────┤
│ PEDIDO ATIVO                 │
│ 🟡 Aguardando PIX · R$42,50  │
├─────────────────────────────┤
│ [📦 Novo Pedido]             │
│ [📍 Enviar localização]      │
│ [💳 Gerar link PIX]          │
│ [✅ Confirmar pedido]        │
│ [❌ Cancelar pedido]         │
└─────────────────────────────┘
```

Dados vindos de `UnifiedUser` + `UserAddress` + `Order` (pedido ativo).

### "Novo Pedido" inline

Botão abre **drawer** (não nova página) com o mesmo fluxo do PDV — endereço pré-preenchido do contexto da conversa (se bot já capturou via pin). Ao confirmar: pedido criado + mensagem de confirmação enviada automaticamente pro cliente via WhatsApp.

### Pin de localização WhatsApp → `UserAddress`

Fluxo já existe parcialmente (reverse geocode no bot). Extensão:
- Bot recebe pin → reverse geocode → cria `UserAddress(label='WhatsApp', unified_user=<resolvido pelo phone da conversa>, store=<store da conta WhatsApp>)`
- Painel lateral do atendente exibe o endereço imediatamente (WebSocket)
- Atendente não precisa pedir endereço de novo

### Templates

- Lista de templates aprovados da conta WhatsApp Business (via Meta API)
- Preview com campos variáveis editáveis (nome, valor, link)
- Envio registrado como mensagem na conversa com tipo `template`
- Variáveis validadas antes do envio para evitar rejeição da Meta

---

## Ordem de implementação sugerida

1. `StoreTeamMember` + `UserAddress` + campos `Order` (migrations + data migration)
2. Helper `has_store_permission()` + middleware/decorator para views
3. API `crm/customers/search/` + API `UserAddress` CRUD
4. django-unfold instalado + `StoreAdmin` com PlacesSearchWidget
5. `UserAdmin` com inline de `StoreTeamMember`
6. pastita-dash: fluxo PDV completo (busca cliente → endereço → produtos → total → confirmar)
7. pastita-dash: painel lateral WhatsApp (dados cliente + ações rápidas)
8. pastita-dash: drawer "Novo Pedido" inline no chat
9. pastita-dash: UI de templates WhatsApp
10. Integração pin WhatsApp → `UserAddress` automático

---

## Contratos de API novos

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/stores/{slug}/crm/customers/search/?q=` | Busca UnifiedUser |
| GET | `/stores/{slug}/crm/customers/{id}/` | Perfil completo |
| GET | `/stores/{slug}/crm/customers/{id}/addresses/` | Endereços salvos |
| POST | `/stores/{slug}/crm/customers/{id}/addresses/` | Criar endereço |
| GET | `/admin/places-search/?q=` | Busca Places (admin only) |
| GET | `/stores/{slug}/team/` | Listar equipe |
| POST | `/stores/{slug}/team/` | Adicionar membro |
| PATCH | `/stores/{slug}/team/{id}/` | Alterar role |
| DELETE | `/stores/{slug}/team/{id}/` | Remover membro |

---

## Dependências novas

| Pacote | Projeto | Motivo |
|--------|---------|--------|
| `django-unfold` | server2 | Admin UI moderno |

Nenhuma outra dependência nova. Google Maps, Redis, WebSocket, Celery — tudo já existe.
