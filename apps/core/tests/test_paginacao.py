"""
O `page_size` que o cliente pede tem que valer.

O padrão do DRF ignora o parâmetro sem reclamar, e uma lista truncada é
indistinguível de uma lista completa e curta. Foi assim que a tela de
ingredientes mostrou "1 da TACO e 19 da POF" com 2.555 alimentos no banco:
eram os 20 primeiros em ordem alfabética.
"""
from django.test import RequestFactory, SimpleTestCase

from apps.core.pagination import PaginacaoPadrao


class PaginacaoPadraoTest(SimpleTestCase):
    def setUp(self):
        self.pag = PaginacaoPadrao()
        self.fabrica = RequestFactory()

    def _tamanho(self, query=""):
        from rest_framework.request import Request
        return self.pag.get_page_size(Request(self.fabrica.get(f"/x/{query}")))

    def test_sem_parametro_usa_o_padrao(self):
        self.assertEqual(self._tamanho(), 20)

    def test_respeita_o_page_size_pedido(self):
        self.assertEqual(self._tamanho("?page_size=500"), 500)

    def test_teto_protege_contra_varredura_de_tabela(self):
        # page_size vem da URL: sem teto, ?page_size=999999 vira table scan.
        self.assertEqual(self._tamanho("?page_size=999999"), 500)

    def test_valor_invalido_cai_no_padrao(self):
        self.assertEqual(self._tamanho("?page_size=abc"), 20)

    def test_zero_cai_no_padrao(self):
        self.assertEqual(self._tamanho("?page_size=0"), 20)
