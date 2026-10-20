"""Nair, 20/10/2026, Cê Saladas: "Colégio Marista".

A ferramenta `salvar_endereco_entrega` geocodificou o texto cru: o Google não
acha "Colégio Marista" como endereço e devolve o centro genérico de Palmas
(-10.249091, location_type OTHER), a 9,3 km da loja — R$ 15,29. Segundos
depois, `finalizar_pedido` passou pelo checkout, que usa `localizar()` (busca
o LUGAR: 110 Sul, 1,98 km) e cobrou R$ 8,00. O bot misturou as duas e mandou
"Taxa de entrega (9,3 km) — R$ 8,00".

O mesmo centro genérico já tinha cobrado errado da Ana em 05/10; o checkout foi
corrigido, as ferramentas do agente não.
"""
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from apps.agents.models import Agent
from apps.agents.services.langchain_service import LangchainService
from apps.stores.tests.factories import make_store

CENTRO_DE_PALMAS = {
    'lat': -10.249091, 'lng': -48.3242858, 'location_type': 'OTHER',
    'formatted_address': 'Colégio Marista - Palmas, TO, Brasil',
}
MARISTA = {
    'lat': -10.1913182, 'lng': -48.3123376, 'location_type': 'PLACE',
    'formatted_address': 'Q. 110 Sul Alameda 23, 23 - 110 Sul, Palmas - TO, 77020-158',
}


def _cotacao(store, customer_lat=None, customer_lng=None, **kw):
    perto = customer_lat is not None and abs(customer_lat - MARISTA['lat']) < 1e-6
    return {
        'fee': 8.0 if perto else 15.29,
        'distance_km': 1.98 if perto else 9.29,
        'is_within_area': True,
    }


@pytest.fixture
def agent(db):
    return Agent.objects.create(name='Atendente', provider=Agent.AgentProvider.NVIDIA)


def _svc(agent):
    redis = Mock()
    redis.get.return_value = None
    with patch.object(LangchainService, '_create_llm', return_value=Mock()), \
         patch.object(LangchainService, '_create_redis_client', return_value=redis):
        return LangchainService(agent)


def _geo(localizar):
    from apps.stores.services.geo import geo_service
    return patch.multiple(
        geo_service,
        geocode=Mock(return_value=CENTRO_DE_PALMAS),
        localizar=Mock(return_value=localizar),
        calculate_delivery_fee=Mock(side_effect=_cotacao),
    )


def test_salvar_endereco_usa_o_lugar_e_nao_o_centro_da_cidade(agent, db):
    store = make_store()
    tools = {t.name: t for t in _svc(agent)._build_tools(phone_number='5563984689350', store=store)}

    with _geo(MARISTA):
        resposta = tools['salvar_endereco_entrega'].invoke({'endereco': 'Colégio Marista'})

    assert '(2.0 km)' in resposta, resposta
    assert '8,00' in resposta
    assert '9.3' not in resposta and '15,29' not in resposta


def test_lugar_nao_achado_pede_localizacao_em_vez_de_cotar_o_centro(agent, db):
    store = make_store()
    tools = {t.name: t for t in _svc(agent)._build_tools(phone_number='5563984689350', store=store)}

    from apps.stores.services.geo import geo_service
    with _geo(None):
        resposta = tools['salvar_endereco_entrega'].invoke({'endereco': 'Colégio Marista'})
        assert not geo_service.calculate_delivery_fee.called

    assert 'localiza' in resposta.lower()
    assert '15,29' not in resposta


def test_cotacao_direta_de_frete_tambem_usa_o_lugar(agent, db):
    store = make_store()
    store.default_delivery_fee = Decimal('8.00')
    store.save()
    svc = _svc(agent)

    with _geo(MARISTA), patch.object(svc, '_looks_like_delivery_address', return_value=True), \
         patch.object(svc, '_match_fixed_delivery_zone_from_text', return_value=None):
        resposta = svc._get_delivery_fee_runtime_reply('taxa de entrega no Colégio Marista', store=store)

    assert resposta and '(2.0 km)' in resposta, resposta
    assert '9.3' not in resposta and '15,29' not in resposta

