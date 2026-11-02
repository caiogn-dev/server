"""BrasilAPI deu 429 em 28/10 e o painel mostrou "Sem conexão com o servidor"
ao buscar o CNPJ do cliente. Quando a primeira fonte recusa, a segunda responde."""
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache

from apps.fiscal.consulta_cnpj import ConsultaIndisponivel, consultar_cnpj

CNPJ = '65486534000115'

CNPJ_WS = {
    'razao_social': 'HOA COMERCIO DE MOVEIS LTDA',
    'estabelecimento': {
        'nome_fantasia': 'BONTEMPO', 'situacao_cadastral': 'Ativa',
        'tipo_logradouro': 'QUADRA', 'logradouro': 'ARSE 22 ALAMEDA 2 LOTE', 'numero': '05',
        'complemento': 'LOJA  29 E 30', 'bairro': 'PLANO DIRETOR SUL', 'cep': '77020514',
        'ddd1': '61', 'telefone1': '84319122', 'email': 'FISCAL@primecontadores.com.br',
        'estado': {'sigla': 'TO'}, 'cidade': {'nome': 'Palmas'},
    },
}


def _resp(status, dados=None):
    r = MagicMock(status_code=status)
    r.json.return_value = dados or {}
    return r


@pytest.fixture(autouse=True)
def _sem_cache():
    cache.clear()
    yield
    cache.clear()


def test_brasilapi_recusa_e_cnpj_ws_responde():
    with patch('apps.fiscal.consulta_cnpj.requests.get', side_effect=[_resp(429), _resp(200, CNPJ_WS)]):
        dados = consultar_cnpj(CNPJ)
    assert dados['nome'] == 'HOA COMERCIO DE MOVEIS LTDA'
    assert dados['nome_fantasia'] == 'BONTEMPO'
    assert dados['email'] == 'fiscal@primecontadores.com.br'
    assert dados['telefone'] == '6184319122'
    assert dados['endereco'] == {
        'street': 'QUADRA ARSE 22 ALAMEDA 2 LOTE', 'number': '05', 'complement': 'LOJA 29 E 30',
        'neighborhood': 'PLANO DIRETOR SUL', 'city': 'Palmas', 'state': 'TO', 'zip_code': '77020514',
    }


def test_404_da_primeira_fonte_e_cnpj_inexistente():
    with patch('apps.fiscal.consulta_cnpj.requests.get', return_value=_resp(404)) as get:
        assert consultar_cnpj(CNPJ) is None
    assert get.call_count == 1


def test_as_duas_fora_do_ar():
    with patch('apps.fiscal.consulta_cnpj.requests.get', side_effect=[_resp(429), _resp(503)]):
        with pytest.raises(ConsultaIndisponivel):
            consultar_cnpj(CNPJ)
