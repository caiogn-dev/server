"""A URL pública da loja não pode virar lixo quando a env traz uma lista.

Descoberto em 11/ago ao montar o e-mail de marketing: para Pastita, Ivoneth e
Kero Kero, `get_storefront_base_url` devolvia

    https://cardapidex.com.br,https:

porque `FRONTEND_URL` em produção vale
`'https://cardapidex.com.br,https://painel.pastita.com.br'` — duas URLs
separadas por vírgula, no estilo de uma lista de origens — e o normalizador
tratava a string inteira como um host só.

Não é um problema de e-mail: essa mesma função monta o **redirect
pós-pagamento** e o link "avalie cada prato" que vai no WhatsApp. Toda loja sem
URL própria no metadata cai nesse fallback.
"""
import pytest
from django.test import override_settings

from apps.stores.services.checkout_service import CheckoutService
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    return make_store()


class TestNormalizacao:
    def test_lista_separada_por_virgula_usa_a_primeira(self):
        saida = CheckoutService._normalize_base_url(
            'https://cardapidex.com.br,https://painel.pastita.com.br'
        )
        assert saida == 'https://cardapidex.com.br'

    def test_lista_com_espaco_depois_da_virgula(self):
        saida = CheckoutService._normalize_base_url(
            'https://cardapidex.com.br, https://painel.pastita.com.br'
        )
        assert saida == 'https://cardapidex.com.br'

    def test_url_simples_continua_igual(self):
        assert CheckoutService._normalize_base_url(
            'https://cesaladas.com.br/'
        ) == 'https://cesaladas.com.br'

    def test_sem_esquema_ainda_funciona(self):
        assert CheckoutService._normalize_base_url(
            'cesaladas.com.br'
        ) == 'https://cesaladas.com.br'

    def test_vazio_continua_vazio(self):
        assert CheckoutService._normalize_base_url('') == ''
        assert CheckoutService._normalize_base_url(None) == ''

    def test_lista_com_primeiro_item_invalido_pega_o_proximo(self):
        assert CheckoutService._normalize_base_url(
            ' ,https://cesaladas.com.br'
        ) == 'https://cesaladas.com.br'


class TestUrlDaLoja:
    @override_settings(
        FRONTEND_URL='https://cardapidex.com.br,https://painel.pastita.com.br'
    )
    def test_loja_sem_url_propria_nao_recebe_url_quebrada(self, loja):
        url = CheckoutService.get_storefront_base_url(loja)

        assert url == 'https://cardapidex.com.br'
        assert ',' not in url

    @override_settings(FRONTEND_URL='https://cardapidex.com.br,https://outra.com')
    def test_url_propria_da_loja_ainda_ganha_do_fallback(self, loja):
        loja.metadata = {'frontend_url': 'https://cesaladas.com.br'}
        loja.save(update_fields=['metadata'])

        assert CheckoutService.get_storefront_base_url(loja) == 'https://cesaladas.com.br'
