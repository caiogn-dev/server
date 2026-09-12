"""Bandeira sem integracao: o pedido nasce, o pagamento vem por link.

A Volus nao tem API — nem `api.volus.com.br` existe em DNS, e nenhum gateway
brasileiro a lista. Mas o cliente que tem o cartao existe e quer comprar.

Entao o caminho e: ele escolhe, o pedido E CRIADO com pagamento pendente, e a
loja manda o link de cobranca pelo WhatsApp. Sem criar o pedido, a loja nao
teria o que cobrar e o cliente repetiria tudo na conversa.

Isto e generico de proposito. Bandeira sem integracao e um CASO, nao uma
excecao: a proxima entra como uma linha no catalogo, igual as outras.
"""
from django.test import TestCase

from apps.stores.services.voucher import bandeiras


class CatalogoManualTests(TestCase):
    def test_a_volus_esta_no_catalogo_manual(self):
        self.assertIn('volus', bandeiras.valores_manuais())

    def test_bandeira_manual_nao_entra_no_catalogo_automatico(self):
        """Misturar as duas faria o checkout pedir cartao para quem nao tem
        como cobrar — e a cobranca falharia no clique."""
        self.assertNotIn('volus', bandeiras.valores())

    def test_manual_tem_rotulo_proprio(self):
        self.assertEqual(bandeiras.rotulo('volus'), 'Volus')

    def test_rotulo_funciona_para_os_dois_catalogos(self):
        self.assertEqual(bandeiras.rotulo('vr'), 'VR Benefícios')
        self.assertEqual(bandeiras.rotulo('volus'), 'Volus')

    def test_valor_desconhecido_continua_voltando_como_veio(self):
        self.assertEqual(bandeiras.rotulo('xpto'), 'xpto')

    def test_os_dois_catalogos_nao_se_cruzam(self):
        automaticas = set(bandeiras.valores())
        manuais = set(bandeiras.valores_manuais())
        self.assertEqual(automaticas & manuais, set())
