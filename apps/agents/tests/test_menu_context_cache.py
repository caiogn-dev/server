"""
Testes para o cache Redis do menu_text da loja (Task 4).

O menu_text derivado de StoreProduct é a única consulta de DB real no bloco
estático de _build_dynamic_context. Ele é cacheado em django.core.cache (Redis),
com invalidação no save de produto/categoria. Provider-agnóstico (NVIDIA) —
nada de cache_control da Anthropic.
"""
from unittest.mock import Mock, patch

import pytest
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.agents.models import Agent
from apps.agents.services.langchain_service import (
    LangchainService,
    menu_context_cache_key,
)
from apps.stores.tests.factories import make_store, make_product


def _make_service(agent):
    """Instancia o serviço sem tocar em rede/LLM/Redis."""
    with patch.object(LangchainService, '_create_llm', return_value=Mock()), \
         patch.object(LangchainService, '_create_redis_client', return_value=Mock()):
        return LangchainService(agent)


@pytest.fixture
def agent(db):
    return Agent.objects.create(
        name="Test Agent",
        provider=Agent.AgentProvider.NVIDIA,
        system_prompt="Você é um assistente.",
        context_prompt="",
    )


@pytest.fixture
def store_with_product(db):
    store = make_store()
    p = make_product(store, name="Produto A", price="10.00")
    return store, p


def test_second_build_is_cache_hit(agent, store_with_product):
    cache.clear()
    store, _ = store_with_product
    svc = _make_service(agent)

    first = svc._build_menu_text(store)
    assert first  # não-vazio: a loja tem produto

    with CaptureQueriesContext(connection) as ctx:
        second = svc._build_menu_text(store)

    assert second == first
    assert len(ctx.captured_queries) == 0, (
        f"cache hit não deveria tocar o DB, fez {len(ctx.captured_queries)} queries"
    )


def test_product_save_invalidates(agent, store_with_product):
    cache.clear()
    store, p = store_with_product
    svc = _make_service(agent)

    svc._build_menu_text(store)
    assert cache.get(menu_context_cache_key(store.id)) is not None

    p.name += " editado"
    p.save()

    assert cache.get(menu_context_cache_key(store.id)) is None


def test_product_delete_invalidates(agent, store_with_product):
    """post_delete: produto removido NÃO pode continuar no cardápio cacheado.

    O bot oferece só itens do menu; sem invalidar no delete, um produto removido
    seria oferecido por até 30min (TTL).
    """
    cache.clear()
    store, p = store_with_product
    svc = _make_service(agent)

    svc._build_menu_text(store)
    assert cache.get(menu_context_cache_key(store.id)) is not None

    p.delete()

    assert cache.get(menu_context_cache_key(store.id)) is None


def test_menu_text_identical_to_uncached(agent, store_with_product):
    cache.clear()
    store, p = store_with_product
    svc = _make_service(agent)

    menu_text = svc._build_menu_text(store)

    assert menu_text.startswith(f"\n📋 CARDÁPIO INTERNO - {store.name}")
    assert "【" in menu_text and "】" in menu_text
    assert f"• {p.name} - R$ {p.price}" in menu_text


def test_empty_store_caches_empty_string(agent, db):
    cache.clear()
    store = make_store()  # sem produtos
    svc = _make_service(agent)

    result = svc._build_menu_text(store)
    assert result == ""
    # '' é um hit válido: segunda chamada não toca o DB
    with CaptureQueriesContext(connection) as ctx:
        again = svc._build_menu_text(store)
    assert again == ""
    assert len(ctx.captured_queries) == 0
