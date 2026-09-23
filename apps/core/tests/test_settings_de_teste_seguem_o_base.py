"""O settings de teste não pode ter a sua própria versão da verdade.

`config/settings/test_serializer.py` copiava à mão o que precisa bater com
`base.py`, e divergiu DUAS VEZES em uma semana: o escopo `auth` (PR #373) e
`public_read`/`lead_create` (PR #375).

O estrago não é o teste que falha, é COMO ele falha. O DRF resolve a taxa
dentro do `__init__` do throttle, antes de qualquer linha da view, e levanta
`ImproperlyConfigured`. Os testes que quebraram foram os de info-disclosure do
OTP — enquanto estouravam na criação do throttle, uma regressão de segurança
nesses endpoints passaria despercebida.

Este teste cobra a herança, não a lista: acrescentar escopo em `base.py` não
pode exigir lembrar de um segundo arquivo.
"""
import importlib


def test_as_taxas_de_throttle_vem_do_base():
    base = importlib.import_module('config.settings.base')
    teste = importlib.import_module('config.settings.test_serializer')

    esperado = base.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']
    obtido = teste.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']

    faltando = set(esperado) - set(obtido)
    assert not faltando, (
        f'escopos declarados em base.py e ausentes no settings de teste: '
        f'{sorted(faltando)} — o throttle estoura em ImproperlyConfigured '
        f'antes da view rodar'
    )


def test_a_versao_da_graph_api_vem_do_base():
    base = importlib.import_module('config.settings.base')
    teste = importlib.import_module('config.settings.test_serializer')

    assert teste.META_GRAPH_VERSION == base.META_GRAPH_VERSION
    assert teste.META_GRAPH_URL == base.META_GRAPH_URL
