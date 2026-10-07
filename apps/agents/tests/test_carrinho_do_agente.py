"""A IA não conseguia pôr NADA no carrinho.

28/09/2026, Cê Saladas, 11:49: a cliente disse "Salada de camarão", a IA
respondeu com a Magnifico Camarão e perguntou quantas. A cliente disse
"2 unidades". A ferramenta `adicionar_ao_carrinho` estourou com
`'bool' object is not callable` — duas vezes —, o grafo bateu no limite de
iterações, devolveu vazio, e o cliente recebeu "Como posso te ajudar? 👇".
Ela apertou "Atendente" e foi embora.

`StoreProduct.is_in_stock` é `@property` desde fevereiro; a ferramenta passou
a chamá-lo como método em 09/ago (6f92d32). Cinquenta dias em que nenhum
pedido conduzido pela IA pôde ser montado.
"""
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from apps.agents.models import Agent
from apps.agents.services.langchain_service import LangchainService
from apps.stores.tests.factories import make_product, make_store


def _tools(agent, store, phone='5563999990001'):
    redis = Mock()
    redis.get.return_value = None
    with patch.object(LangchainService, '_create_llm', return_value=Mock()), \
         patch.object(LangchainService, '_create_redis_client', return_value=redis):
        svc = LangchainService(agent)
    return {t.name: t for t in svc._build_tools(phone_number=phone, store=store)}, redis


@pytest.fixture
def agent(db):
    return Agent.objects.create(name='Atendente', provider=Agent.AgentProvider.NVIDIA)


def test_adicionar_ao_carrinho_adiciona_de_verdade(agent, db):
    store = make_store()
    make_product(store, name='Magnifico Camarão', price=Decimal('36.74'))
    tools, redis = _tools(agent, store)

    resultado = tools['adicionar_ao_carrinho'].invoke({'produto_nome': 'camarão', 'quantidade': 2})

    assert resultado.startswith('✓ 2x Magnifico Camarão'), resultado
    assert 'Erro' not in resultado
    assert redis.setex.called  # o carrinho foi gravado


def test_produto_sem_estoque_e_recusado_sem_estourar(agent, db):
    store = make_store()
    fora = make_product(store, name='Salmão', price=Decimal('50'))
    fora.track_stock = True
    fora.stock_quantity = 0
    fora.allow_backorder = False
    fora.save()
    make_product(store, name='Frango', price=Decimal('30'))
    tools, _ = _tools(agent, store)

    resultado = tools['adicionar_ao_carrinho'].invoke({'produto_nome': 'Salmão', 'quantidade': 1})

    assert 'SEM ESTOQUE' in resultado
    assert 'Frango' in resultado  # sugere o que tem
    assert 'Erro' not in resultado


def test_nome_ambiguo_pergunta_em_vez_de_escolher_o_mais_curto(agent, db):
    """"camarão" → Combo Camarão (R$ 124,70) em vez da salada de R$ 36,74."""
    store = make_store()
    make_product(store, name='Magnifico Camarão', price=Decimal('36.74'))
    make_product(store, name='Combo Camarão', price=Decimal('124.70'))
    tools, redis = _tools(agent, store)

    resultado = tools['adicionar_ao_carrinho'].invoke({'produto_nome': 'camarão', 'quantidade': 1})

    assert 'NÃO adicione' in resultado
    assert 'Magnifico Camarão' in resultado and 'Combo Camarão' in resultado
    assert not redis.setex.called


def test_nome_exato_vence_mesmo_com_outros_parecidos(agent, db):
    store = make_store()
    make_product(store, name='Magnifico Camarão', price=Decimal('36.74'))
    make_product(store, name='Combo Camarão', price=Decimal('124.70'))
    tools, _ = _tools(agent, store)

    resultado = tools['adicionar_ao_carrinho'].invoke({'produto_nome': 'Magnifico Camarão', 'quantidade': 1})

    assert resultado.startswith('✓ 1x Magnifico Camarão'), resultado


def test_item_da_ia_chega_na_sessao_do_pedido(agent, db):
    """07/10, Dr. Matheus (Cê Saladas): a IA disse "Adicionei 1x Especial Filé
    de Frango ao seu carrinho"; minutos depois ele mandou a localização e o
    bot respondeu "Escolha um item no cardápio", e o "crédito" virou "Não
    encontrei nenhum pedido aberto". A cópia do carrinho da IA para a sessão
    lia `sm.session`, que não existe no SessionManager — o AttributeError era
    engolido e o item nunca chegava ao fluxo do pedido.
    """
    from apps.automation.models import CompanyProfile
    from apps.automation.services.session_manager import get_session_manager

    store = make_store()
    produto = make_product(store, name='Especial Filé de Frango', price=Decimal('39.99'))
    CompanyProfile.objects.get_or_create(store=store)
    phone = '5563981007070'
    tools, _ = _tools(agent, store, phone=phone)

    tools['adicionar_ao_carrinho'].invoke({'produto_nome': 'especial filé de frango', 'quantidade': 1})

    sm = get_session_manager(CompanyProfile.objects.get(store=store), phone)
    itens = sm.get_pending_order_items()
    assert [(i['product_id'], i['quantity']) for i in itens] == [(str(produto.id), 1)]


def test_carrinho_da_ia_nasce_do_que_o_catalogo_ja_pos_na_sessao(agent, db):
    """O caminho inverso: pedido do catálogo grava em pending_items; se a IA
    entra na conversa depois, ela precisa ver esse item (mesmo AttributeError)."""
    from apps.automation.models import CompanyProfile
    from apps.automation.services.session_manager import get_session_manager

    store = make_store()
    produto = make_product(store, name='Queridinha', price=Decimal('28.99'))
    CompanyProfile.objects.get_or_create(store=store)
    phone = '5563981007071'
    sm = get_session_manager(CompanyProfile.objects.get(store=store), phone)
    sessao = sm.get_or_create_session()
    sessao.cart_data = {'pending_items': [{'product_id': str(produto.id), 'quantity': 2, 'unit_price': 28.99}]}
    sessao.save(update_fields=['cart_data'])
    tools, _ = _tools(agent, store, phone=phone)

    resultado = tools['ver_carrinho'].invoke({})

    assert 'Queridinha' in resultado, resultado
