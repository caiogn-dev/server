# Backend Quick Wins — Performance, Complexidade e Custo (server2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aplicar os quick wins baratos de performance/custo do server2 — destravar tooling de complexidade, matar o N+1 dos combos, parar de montar o contexto do cliente 2x por mensagem, cachear o contexto estático do LLM em Redis (provider-agnóstico, serve pro NVIDIA), instrumentar tokens/custo, e ligar coverage.

**Architecture:** Django 4 + DRF, multi-tenant por `store`. Camada LLM em `apps/agents/services/langchain_service.py` usando LangChain; o provider em produção é **NVIDIA NIM** via `ChatOpenAI` (OpenAI-compatible, modelo `meta/llama-3.1-70b-instruct`). Cache de aplicação via Redis (`django.core.cache`, já configurado em `config/settings/base.py`). O caching do contexto é feito na camada de aplicação (Redis), **não** via prompt-cache de API — assim funciona com NVIDIA e qualquer provider.

**Tech Stack:** Python, Django, DRF, LangChain, `langchain-openai` (NVIDIA), Redis (django-redis), pytest + pytest-django, radon/xenon/coverage.

## Global Constraints

- Provider LLM-alvo: **NVIDIA** (`Agent.AgentProvider.NVIDIA`, `ChatOpenAI` apontando para `https://integrate.api.nvidia.com/v1`). O caminho Anthropic existe mas é opcional — **nada neste plano pode depender de `cache_control` da Anthropic**.
- Comportamento de saída do agente (ordem e conteúdo das strings de contexto) **não pode mudar** — `_build_dynamic_context` é revenue-crítico. Toda mudança nele exige teste de caracterização ANTES.
- Tests rodam com `pytest` + `pytest-django`. Settings de teste: `config.settings.development` (a menos que `DJANGO_SETTINGS_MODULE` já esteja fixado no CI — ver `.github/workflows/ci.yml`).
- Commits em português (padrão do repo). Co-autoria conforme convenção do repositório.
- TDD obrigatório: teste falhando → mínimo pra passar → verde → commit. Zero regressões (919 funções de teste existentes devem continuar passando).

---

## File Structure

| Arquivo | Responsabilidade | Ação |
|---|---|---|
| `apps/stores/services/checkout_service.py` | Checkout (hot path) | Modify — remover BOM linha 1 |
| `apps/core/services/dashboard_stats.py` | Stats do dashboard (hot path) | Modify — remover BOM linha 1 |
| `apps/stores/api/serializers.py` | `build_combo_groups` (N+1) | Modify — ordenar em Python, não no manager |
| `apps/stores/api/views/product_views.py` | `StoreComboViewSet` (admin) | Modify — prefetch no queryset |
| `apps/agents/services/langchain_service.py` | Contexto LLM + tokens | Modify — store-first, cache Redis, instrumentação |
| `apps/agents/services/llm_cost.py` | Tabela de preço + cálculo de custo | Create |
| `apps/agents/models.py` (ou nova migration) | Persistir tokens/custo por conversa | Modify/Create |
| `pytest.ini` | Config de teste + coverage | Create |
| `requirements-dev.txt` (ou requirements.txt) | coverage, pytest-cov, xenon | Modify |
| `.github/workflows/ci.yml` | Gate de complexidade + coverage | Modify |
| `apps/.../tests/...` | Testes de cada task | Create |

---

### Task 1: Remover BOM de checkout_service e dashboard_stats

O BOM UTF-8 (`U+FEFF`, bytes `EF BB BF`) na linha 1 faz radon/xenon falharem silenciosamente nesses dois arquivos — dois hot paths num ponto cego de tooling. Confirmado: `head -c3` retorna `efbbbf` nos dois.

**Files:**
- Modify: `apps/stores/services/checkout_service.py:1`
- Modify: `apps/core/services/dashboard_stats.py:1`
- Test: `apps/core/tests/test_no_bom.py` (Create)

**Interfaces:**
- Consumes: nada.
- Produces: nada (mudança de bytes invisível ao Python). Garante que radon volta a enxergar esses arquivos.

- [ ] **Step 1: Escrever o teste que falha**

```python
# apps/core/tests/test_no_bom.py
from pathlib import Path
import pytest

REPO = Path(__file__).resolve().parents[2]  # .../server2
BOM = b"\xef\xbb\xbf"

CANDIDATES = [
    "apps/stores/services/checkout_service.py",
    "apps/core/services/dashboard_stats.py",
]

@pytest.mark.parametrize("rel", CANDIDATES)
def test_source_has_no_utf8_bom(rel):
    head = (REPO / rel).read_bytes()[:3]
    assert head != BOM, f"{rel} começa com BOM UTF-8 (quebra radon/xenon)"
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `pytest apps/core/tests/test_no_bom.py -v`
Expected: FAIL (2 casos) — os dois arquivos começam com BOM.

- [ ] **Step 3: Remover o BOM**

```bash
sed -i '1s/^\xEF\xBB\xBF//' apps/stores/services/checkout_service.py
sed -i '1s/^\xEF\xBB\xBF//' apps/core/services/dashboard_stats.py
```

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `pytest apps/core/tests/test_no_bom.py -v`
Expected: PASS (2 casos).

- [ ] **Step 5: Confirmar que radon volta a enxergar**

Run: `radon cc -s apps/stores/services/checkout_service.py apps/core/services/dashboard_stats.py`
Expected: saída com blocos/CC (antes vinha vazio).

- [ ] **Step 6: Commit**

```bash
git add apps/stores/services/checkout_service.py apps/core/services/dashboard_stats.py apps/core/tests/test_no_bom.py
git commit -m "fix: remover BOM UTF-8 de checkout_service e dashboard_stats (destrava radon/xenon)"
```

---

### Task 2: Matar o N+1 dos combos (prefetch não pode ser derrubado por order_by)

`build_combo_groups` (`serializers.py:1118`) faz `obj.groups.all().order_by('position')` (:1125), `group.variant_limits.all()` (:1128) e `group.product_options.all().order_by('position')` (:1147). O `.order_by()` sobre um manager **re-dispara query** mesmo quando o queryset pai já tem `prefetch_related` — derruba o prefetch. O storefront já prefetcha (`storefront_views.py:334`) mas perde o efeito; o ViewSet admin (`StoreComboViewSet`, `product_views.py:247`) não prefetcha nada. Como os volumes são pequenos, ordenar **em Python** sobre os dados já pré-carregados é robusto e simples.

**Files:**
- Modify: `apps/stores/api/serializers.py:1118-1160` (`build_combo_groups`)
- Modify: `apps/stores/api/views/product_views.py:244-247` (`StoreComboViewSet` — adicionar `get_queryset` com prefetch)
- Test: `apps/stores/tests/test_combo_queries.py` (Create)

**Interfaces:**
- Consumes: relateds confirmados — `StoreCombo.groups` (`combo_group.py:17`), `ComboProductGroup.variant_limits` (`:71`), `ComboProductGroup.product_options` (`:115`).
- Produces: `build_combo_groups(obj)` com mesma saída de dados (mesma ordem por `position`), mas O(1) queries quando o `obj` vem de um queryset com prefetch.

- [ ] **Step 1: Escrever o teste de contagem de queries (falha)**

```python
# apps/stores/tests/test_combo_queries.py
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from apps.stores.api.serializers import StoreComboSerializer
from apps.stores.api.views.product_views import StoreComboViewSet

class ComboQueryCountTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Usar fixtures/factories reais do projeto. Criar 1 store, 1 combo
        # com >=3 grupos, cada grupo com >=2 variant_limits e >=2 product_options.
        from apps.stores.tests.factories import make_combo_with_groups  # se não existir, criar helper
        cls.store, cls.combo = make_combo_with_groups(groups=3, variants=2, options=2)

    def test_admin_combo_list_is_constant_queries(self):
        qs = StoreComboViewSet.queryset_for_test(self.store)  # ver Step 3
        with CaptureQueriesContext(connection) as ctx:
            data = StoreComboSerializer(qs, many=True).data
            # forçar avaliação completa dos grupos
            _ = [g for c in data for g in c["groups"]]
        # Sem prefetch eram 1 + G + G*(2) queries. Com prefetch: poucas e constantes.
        assert len(ctx.captured_queries) <= 6, [q["sql"] for q in ctx.captured_queries]
```

> Se `apps/stores/tests/factories.py`/`make_combo_with_groups` não existir, criar o helper mínimo neste mesmo commit usando os models reais (`StoreCombo`, `ComboProductGroup`, `ComboGroupVariantLimit`, `ComboGroupProductOption`). Não inventar campos — abrir os models e usar os obrigatórios.

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest apps/stores/tests/test_combo_queries.py -v`
Expected: FAIL — contagem de queries acima do limite (N+1) ou `queryset_for_test` inexistente.

- [ ] **Step 3: Adicionar prefetch no queryset admin**

Em `apps/stores/api/views/product_views.py`, dentro de `StoreComboViewSet`, definir o prefetch canônico e um `get_queryset`:

```python
COMBO_PREFETCH = (
    'groups__product',
    'groups__variant_limits__variant__product',
    'groups__product_options__product',
)

class StoreComboViewSet(viewsets.ModelViewSet):
    serializer_class = StoreComboSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        from apps.stores.models import StoreCombo
        return StoreCombo.objects.prefetch_related(*COMBO_PREFETCH)

    @classmethod
    def queryset_for_test(cls, store):
        from apps.stores.models import StoreCombo
        return StoreCombo.objects.filter(store=store).prefetch_related(*COMBO_PREFETCH)
```

E em `apps/stores/api/views/storefront_views.py:333`, alinhar o prefetch existente para incluir `groups__variant_limits__variant__product` (hoje só vai até `__variant`), garantindo que `build_combo_groups` não precise tocar o banco.

- [ ] **Step 4: Ordenar em Python dentro de build_combo_groups**

Em `apps/stores/api/serializers.py`, trocar os `.order_by()` sobre managers por `sorted(...)` sobre as listas já pré-carregadas:

```python
def build_combo_groups(obj):
    groups_out = []
    for group in sorted(obj.groups.all(), key=lambda g: g.position):
        # ... montar group_dict ...
        for limit in group.variant_limits.all():        # sem re-query
            ...
        for opt in sorted(group.product_options.all(), key=lambda o: o.position):
            ...
        groups_out.append(group_dict)
    return groups_out
```

> Manter exatamente os mesmos campos/chaves de saída de antes. Só muda a *fonte* da ordenação (Python sobre dados prefetchados), não o resultado.

- [ ] **Step 5: Rodar o teste e ver passar**

Run: `pytest apps/stores/tests/test_combo_queries.py -v`
Expected: PASS (≤6 queries).

- [ ] **Step 6: Rodar a suíte de combos/storefront pra garantir zero regressão**

Run: `pytest apps/stores/tests/ -k "combo or storefront or catalog" -q`
Expected: PASS (saída de dados idêntica).

- [ ] **Step 7: Commit**

```bash
git add apps/stores/api/serializers.py apps/stores/api/views/product_views.py apps/stores/api/views/storefront_views.py apps/stores/tests/test_combo_queries.py apps/stores/tests/factories.py
git commit -m "perf: eliminar N+1 em build_combo_groups (prefetch + sort em Python) no admin e storefront"
```

---

### Task 3: Resolver store ANTES de montar o contexto do cliente (1 chamada, não 2)

`_build_dynamic_context` (`langchain_service.py:666`) chama `_build_customer_context(..., store=None)` (:688), depois resolve o `store` (:700-733) e **refaz** `_build_customer_context(..., store=store)` (:734), descartando o primeiro resultado via filtro de string (`:739`). É trabalho de DB jogado fora a cada mensagem. Como o método é revenue-crítico e CC=93 sem cobertura, primeiro um **teste de caracterização**, depois a mudança mínima.

**Files:**
- Modify: `apps/agents/services/langchain_service.py:666-745` (`_build_dynamic_context`)
- Test: `apps/agents/tests/test_dynamic_context.py` (Create)

**Interfaces:**
- Consumes: `_build_customer_context(phone_number, conversation_id, store)`, `_resolve_store(conversation_id)` (extraído no Step 3).
- Produces: `_build_dynamic_context` com a mesma string final, mas chamando `_build_customer_context` **uma vez** (com o store já resolvido, ou `None` se não houver).

- [ ] **Step 1: Teste de caracterização — store é resolvido antes e customer_context roda 1x**

```python
# apps/agents/tests/test_dynamic_context.py
from unittest.mock import patch
from django.test import TestCase
from apps.agents.tests.factories import make_agent_with_store  # criar se faltar

class DynamicContextTest(TestCase):
    def setUp(self):
        self.agent, self.store, self.conv = make_agent_with_store()
        self.svc = ...  # instanciar LangchainService(self.agent) conforme o construtor real

    def test_customer_context_built_once_with_resolved_store(self):
        with patch.object(type(self.svc), "_build_customer_context",
                          return_value="👤 CONTEXTO DO CLIENTE: x") as spy:
            self.svc._build_dynamic_context(phone_number="5563...", conversation_id=str(self.conv.id))
        assert spy.call_count == 1, f"esperado 1 chamada, veio {spy.call_count}"
        # store resolvido deve ter sido passado (não None)
        _, kwargs = spy.call_args
        assert kwargs.get("store") is not None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest apps/agents/tests/test_dynamic_context.py -v`
Expected: FAIL — hoje `call_count == 2` e a 1ª chamada usa `store=None`.

- [ ] **Step 3: Extrair a resolução de store e reordenar**

Extrair o bloco de resolução (linhas ~700-733) para `_resolve_store(self, conversation_id) -> Optional[Store]`, chamá-lo **antes** do customer context, e fazer uma única chamada:

```python
def _build_dynamic_context(self, phone_number, conversation_id=None) -> str:
    context_parts = []
    if self.agent.context_prompt:
        context_parts.append(self.agent.context_prompt)

    store = self._resolve_store(conversation_id)   # resolvido primeiro

    try:
        customer_context = self._build_customer_context(
            phone_number=phone_number,
            conversation_id=conversation_id,
            store=store,                            # já scoped — sem 2ª passada
        )
        if customer_context:
            context_parts.append(customer_context)
    except Exception as e:
        logger.error(f"[AGENT CONTEXT] Error loading customer/order data: {e}")

    # ... resto do método (menu/guidance) usando `store` já resolvido ...
    return "\n\n".join(p for p in context_parts if p)
```

> Remover o filtro de string `[part for part in context_parts if not part.startswith("👤 CONTEXTO DO CLIENTE")]` — não é mais necessário, já que não há 1ª passada a descartar. Garantir que o restante do método (bloco de menu/conduta) use a variável `store` local.

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `pytest apps/agents/tests/test_dynamic_context.py -v`
Expected: PASS (`call_count == 1`, store não-None).

- [ ] **Step 5: Caracterizar a string final (snapshot) pra garantir saída idêntica**

Adicionar um segundo teste que monta o contexto com dados fixos e compara a string contra um snapshot conhecido (capturado da versão atual antes do refactor, via execução manual). Confirma que ordem/conteúdo não mudaram.

Run: `pytest apps/agents/tests/test_dynamic_context.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/agents/services/langchain_service.py apps/agents/tests/test_dynamic_context.py apps/agents/tests/factories.py
git commit -m "perf: resolver store antes de montar customer context (1 chamada por mensagem, nao 2)"
```

---

### Task 4: Cache Redis do contexto estático do LLM por loja (provider-agnóstico)

O bloco de menu/conduta (cardápio formatado + regras) é reconstruído do zero a cada mensagem e cresce com o catálogo. É idêntico entre mensagens da mesma loja até o catálogo mudar. Cachear a **string montada** em Redis (já há `RedisCache` em `base.py`) corta query + montagem em todo turno. Invalidar no `save`/`delete` de `StoreProduct`/`StoreCategory`. Isto substitui o "prompt caching da Anthropic" por algo que funciona com **NVIDIA** e qualquer provider.

**Files:**
- Modify: `apps/agents/services/langchain_service.py` (extrair `_build_menu_context(store)` e envolver em cache)
- Modify: `apps/stores/models/product.py` e `apps/stores/models/category.py` (signal/override `save`/`delete` p/ invalidar) — ou `apps/stores/signals.py` se existir
- Test: `apps/agents/tests/test_menu_context_cache.py` (Create)

**Interfaces:**
- Consumes: `store.id`, `django.core.cache.cache` (já importado em `langchain_service.py:13`).
- Produces:
  - `menu_context_cache_key(store_id) -> str` → `f"agent:menu_ctx:{store_id}"`
  - `_build_menu_context(self, store) -> str` (cacheado)
  - `invalidate_menu_context(store_id) -> None`

- [ ] **Step 1: Teste — 2ª montagem não toca o banco (cache hit) e save invalida**

```python
# apps/agents/tests/test_menu_context_cache.py
from django.core.cache import cache
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from apps.agents.services.langchain_service import menu_context_cache_key
from apps.agents.tests.factories import make_agent_with_store

class MenuContextCacheTest(TestCase):
    def setUp(self):
        cache.clear()
        self.agent, self.store, _ = make_agent_with_store()
        self.svc = ...  # LangchainService(self.agent)

    def test_second_build_is_cache_hit(self):
        first = self.svc._build_menu_context(self.store)
        with CaptureQueriesContext(connection) as ctx:
            second = self.svc._build_menu_context(self.store)
        assert second == first
        assert len(ctx.captured_queries) == 0, "cache hit não deveria tocar o banco"

    def test_product_save_invalidates(self):
        self.svc._build_menu_context(self.store)
        assert cache.get(menu_context_cache_key(self.store.id)) is not None
        p = self.store.products.first()
        p.name = (p.name or "") + " editado"
        p.save()
        assert cache.get(menu_context_cache_key(self.store.id)) is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest apps/agents/tests/test_menu_context_cache.py -v`
Expected: FAIL — `_build_menu_context`/`menu_context_cache_key` não existem.

- [ ] **Step 3: Extrair e cachear**

```python
# apps/agents/services/langchain_service.py
_MENU_CTX_TTL = 60 * 30  # 30 min; invalidação por signal garante frescor

def menu_context_cache_key(store_id) -> str:
    return f"agent:menu_ctx:{store_id}"

def invalidate_menu_context(store_id) -> None:
    cache.delete(menu_context_cache_key(store_id))

# dentro de LangchainService:
def _build_menu_context(self, store) -> str:
    key = menu_context_cache_key(store.id)
    cached = cache.get(key)
    if cached is not None:
        return cached
    text = self._compose_menu_context(store)  # o código atual de montagem do menu
    cache.set(key, text, _MENU_CTX_TTL)
    return text
```

Mover o código de montagem do menu/conduta hoje inline em `_build_dynamic_context` para `_compose_menu_context(store)` e chamar `_build_menu_context(store)` no lugar.

- [ ] **Step 4: Invalidar no save/delete de produto e categoria**

```python
# apps/stores/signals.py (ou onde os signals do app vivem)
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from apps.stores.models import StoreProduct, StoreCategory
from apps.agents.services.langchain_service import invalidate_menu_context

@receiver([post_save, post_delete], sender=StoreProduct)
@receiver([post_save, post_delete], sender=StoreCategory)
def _invalidate_agent_menu_ctx(sender, instance, **kwargs):
    store_id = getattr(instance, "store_id", None)
    if store_id:
        invalidate_menu_context(store_id)
```

Garantir que o módulo de signals é importado no `AppConfig.ready()` do app stores.

- [ ] **Step 5: Rodar os testes e ver passar**

Run: `pytest apps/agents/tests/test_menu_context_cache.py -v`
Expected: PASS (cache hit = 0 queries; save invalida).

- [ ] **Step 6: Regressão do agente**

Run: `pytest apps/agents/tests/ -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/agents/services/langchain_service.py apps/stores/signals.py apps/agents/tests/test_menu_context_cache.py
git commit -m "perf: cachear contexto estatico do menu por loja em Redis + invalidacao no save de produto/categoria"
```

---

### Task 5: Instrumentar tokens e custo por mensagem (somando todas as iterações)

Hoje só se mede `usage_metadata.total_tokens` do **último** `response` (`langchain_service.py:1695`), ignorando as até 5 iterações do loop agêntico e a separação input/output. Sem custo em R$, sem visão por loja. Acumular o uso de todas as iterações e calcular custo via tabela de preço do modelo NVIDIA.

**Files:**
- Create: `apps/agents/services/llm_cost.py`
- Modify: `apps/agents/services/langchain_service.py` (acumulador no loop ~1592-1695)
- Modify/Create: persistência — campo/registro de uso por conversa (`apps/agents/models.py` + migration)
- Test: `apps/agents/tests/test_llm_cost.py` (Create)

**Interfaces:**
- Consumes: `response.usage_metadata` (dict com `input_tokens`, `output_tokens`, `total_tokens`).
- Produces:
  - `accumulate_usage(acc: dict, response) -> dict` (soma input/output/total)
  - `estimate_cost_brl(model_name: str, input_tokens: int, output_tokens: int) -> Decimal`

- [ ] **Step 1: Teste do acumulador e do custo (falha)**

```python
# apps/agents/tests/test_llm_cost.py
from decimal import Decimal
from types import SimpleNamespace
from apps.agents.services.llm_cost import accumulate_usage, estimate_cost_brl

def test_accumulate_sums_all_iterations():
    acc = {}
    for it in (100, 50, 30):
        acc = accumulate_usage(acc, SimpleNamespace(
            usage_metadata={"input_tokens": it, "output_tokens": it // 2, "total_tokens": it + it // 2}))
    assert acc["input_tokens"] == 180
    assert acc["output_tokens"] == 90

def test_estimate_cost_is_positive_for_known_model():
    cost = estimate_cost_brl("meta/llama-3.1-70b-instruct", 1000, 1000)
    assert isinstance(cost, Decimal) and cost > 0
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest apps/agents/tests/test_llm_cost.py -v`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar llm_cost.py**

```python
# apps/agents/services/llm_cost.py
from decimal import Decimal

# Preço por 1M tokens (USD) — ajustar conforme o pricing real do endpoint NVIDIA usado.
# input, output. Fallback genérico para modelos não listados.
_PRICE_USD_PER_M = {
    "meta/llama-3.1-70b-instruct": (Decimal("0.0"), Decimal("0.0")),  # NVIDIA build: preencher real
}
_FALLBACK = (Decimal("0.50"), Decimal("0.50"))
_USD_BRL = Decimal("5.40")  # parametrizar via settings depois

def accumulate_usage(acc: dict, response) -> dict:
    meta = getattr(response, "usage_metadata", None) or {}
    out = dict(acc)
    for k in ("input_tokens", "output_tokens", "total_tokens"):
        out[k] = out.get(k, 0) + int(meta.get(k, 0) or 0)
    return out

def estimate_cost_brl(model_name: str, input_tokens: int, output_tokens: int) -> Decimal:
    pin, pout = _PRICE_USD_PER_M.get(model_name, _FALLBACK)
    usd = (Decimal(input_tokens) * pin + Decimal(output_tokens) * pout) / Decimal(1_000_000)
    return (usd * _USD_BRL).quantize(Decimal("0.000001"))
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest apps/agents/tests/test_llm_cost.py -v`
Expected: PASS.

- [ ] **Step 5: Acumular no loop e persistir**

No loop agêntico (`langchain_service.py` ~1592-1695), manter `usage_acc = {}` e chamar `usage_acc = accumulate_usage(usage_acc, response)` a cada iteração. No retorno, trocar o `tokens_used` de única-iteração por `usage_acc.get("total_tokens", 0)` e registrar `estimate_cost_brl(model_name, usage_acc["input_tokens"], usage_acc["output_tokens"])` por conversa/loja (campo novo em `AgentConversation` ou tabela de uso — usar migration). Confirmar nome real do model via `self.llm.model_name`/config.

- [ ] **Step 6: Migration + regressão**

Run: `python manage.py makemigrations agents && pytest apps/agents/tests/ -q`
Expected: migration criada; testes PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/agents/services/llm_cost.py apps/agents/services/langchain_service.py apps/agents/models.py apps/agents/migrations/ apps/agents/tests/test_llm_cost.py
git commit -m "feat: instrumentar tokens (todas as iteracoes) e custo R$ por mensagem/loja"
```

---

### Task 6: Ligar coverage + gate de complexidade no CI

`coverage`/`pytest-cov` não estão instalados e não há `pytest.ini`. Sem isso, não dá pra medir regressão nem travar a complexidade crescente (`_build_dynamic_context` já regrediu 90→93).

**Files:**
- Create: `pytest.ini`
- Modify: `requirements-dev.txt` (ou `requirements.txt` se não houver dev)
- Modify: `.github/workflows/ci.yml`
- Test: o próprio CI valida.

**Interfaces:**
- Consumes: suíte pytest existente.
- Produces: relatório de coverage + gate xenon.

- [ ] **Step 1: Criar pytest.ini**

```ini
# pytest.ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings.development
python_files = test_*.py tests.py
addopts = --cov=apps --cov-report=term-missing --durations=25
```

- [ ] **Step 2: Adicionar deps de dev**

Acrescentar em `requirements-dev.txt` (criar se não existir):

```
coverage>=7.0
pytest-cov>=4.1
xenon>=0.9
radon>=6.0
```

Run: `pip install -r requirements-dev.txt`

- [ ] **Step 3: Rodar localmente**

Run: `pytest --durations=25`
Expected: suíte roda, mostra coverage e os 25 testes mais lentos.

- [ ] **Step 4: Gate de complexidade no CI**

Em `.github/workflows/ci.yml`, adicionar passo após os testes:

```yaml
      - name: Gate de complexidade (xenon)
        run: xenon --max-absolute E --max-modules C --max-average B apps
```

> `--max-absolute E` impede QUALQUER bloco novo pior que E. Como `_build_dynamic_context` já é F, este gate falharia hoje — então: ou (a) excluir `langchain_service.py` do gate temporariamente com nota "remover após refactor da Task 7 do plano de refactor LLM", ou (b) começar com `--max-absolute F` e apertar depois. Escolher (a) e documentar no YAML.

- [ ] **Step 5: Commit**

```bash
git add pytest.ini requirements-dev.txt .github/workflows/ci.yml
git commit -m "chore: ligar coverage (pytest-cov) + gate de complexidade xenon no CI"
```

---

## Sequência e dependências

1 → 2 → 3 → 4 → 5 → 6. Tasks 1, 2 e 6 são independentes entre si (podem paralelizar). Tasks 3 e 4 tocam o mesmo método (`_build_dynamic_context`) — fazer 3 **antes** de 4 (a Task 3 deixa `store` resolvido cedo, o que a Task 4 reutiliza). Task 5 é independente do contexto mas vive no mesmo arquivo — fazer por último pra evitar conflito de merge.

## Endpoints que este plano cria/prepara para o frontend

- **(futuro)** Os quick wins do pastita-dash que dependem do backend — `?customer=` em pedidos, KPIs agregados de clientes via `annotate`, paginação server-side — **não estão neste plano** (são esforço M+, não "quick win barato"). Ficam no plano de frontend como dependência explícita. Ver `pastita-dash/docs/superpowers/plans/2026-06-22-frontend-perf-data.md`.

## Self-Review

- Cobertura do spec (6 quick wins baratos do backend): BOM (T1), N+1 combo (T2), store-first (T3), cache Redis do contexto NVIDIA (T4), instrumentação de tokens/custo (T5), coverage+gate (T6). ✅
- Sem prompt-cache Anthropic em lugar nenhum — caching é 100% Redis/app-level. ✅
- Tipos consistentes: `menu_context_cache_key`/`invalidate_menu_context`/`_build_menu_context` usados igual entre Task 4 e testes; `accumulate_usage`/`estimate_cost_brl` idem Task 5. ✅
- Riscos sinalizados: factories podem não existir (instruído criar), nomes de campo dos models de combo a confirmar nos models reais, gate xenon precisa exclusão temporária do arquivo F. ✅
