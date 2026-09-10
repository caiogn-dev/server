"""
O endereço do cliente não pode crescer a cada pedido.

Caso real da Leani (5563992618115), Cê Saladas. `street` no banco, em ordem:

    02/set 14:08  "Secretaria da cidadania e justiça"
    02/set 14:10  "Secretaria da cidadania e justiça,  — , Palmas-TO"
    10/set 13:19  "Secretaria da cidadania e justiça,  — , Palmas-TO,  — , Palmas-TO"

O PDV mandava um RÓTULO de exibição como endereço; `_build_address_record`
guarda texto solto em `street` e devolve `formatted = street + cidade + UF`.
No pedido seguinte o rótulo era montado em cima do rótulo. Catraca.

O painel já não manda mais rótulo, mas o texto solto ainda chega pelo bot do
WhatsApp e por qualquer integração. `formatted` tem que ser IDEMPOTENTE: passar
o próprio resultado de volta como rua não pode fazer o endereço crescer.
"""
from django.test import TestCase

from apps.core.services.customer_identity import CustomerIdentityService as Serv


class EnderecoNaoCresce(TestCase):
    def test_rotulo_devolvido_como_rua_nao_cresce(self):
        primeiro = Serv._build_address_record({
            "address": "Secretaria da cidadania e justiça",
            "city": "Palmas",
            "state": "TO",
        })
        self.assertEqual(primeiro["formatted"], "Secretaria da cidadania e justiça, Palmas, TO")

        segundo = Serv._build_address_record({
            "address": primeiro["formatted"],
            "city": "Palmas",
            "state": "TO",
        })
        self.assertEqual(segundo["formatted"], primeiro["formatted"])
        self.assertEqual(segundo["street"], "Secretaria da cidadania e justiça")

    def test_rotulo_do_pdv_antigo_e_desmontado(self):
        registro = Serv._build_address_record({
            "address": "Secretaria da cidadania e justiça,  — , Palmas-TO",
            "city": "Palmas",
            "state": "TO",
        })
        self.assertEqual(registro["street"], "Secretaria da cidadania e justiça")
        self.assertEqual(registro["formatted"], "Secretaria da cidadania e justiça, Palmas, TO")

    def test_duas_geracoes_de_rotulo_tambem_somem(self):
        registro = Serv._build_address_record({
            "address": "Secretaria da cidadania e justiça,  — , Palmas-TO,  — , Palmas-TO",
            "city": "Palmas",
            "state": "TO",
        })
        self.assertEqual(registro["street"], "Secretaria da cidadania e justiça")

    def test_rua_que_so_parece_com_a_cidade_fica_intacta(self):
        registro = Serv._build_address_record({
            "address": "Avenida Palmas Brasil, 120",
            "city": "Palmas",
            "state": "TO",
        })
        self.assertEqual(registro["street"], "Avenida Palmas Brasil, 120")

    def test_endereco_normal_nao_muda(self):
        registro = Serv._build_address_record({
            "street": "Avenida Juscelino Kubitscheck",
            "number": "38-76",
            "neighborhood": "Plano Diretor Norte",
            "city": "Palmas",
            "state": "TO",
            "zip_code": "77001-014",
        })
        self.assertEqual(registro["street"], "Avenida Juscelino Kubitscheck")
        self.assertEqual(registro["zip_code"], "77001014")
        self.assertEqual(
            registro["formatted"],
            "Avenida Juscelino Kubitscheck, 38-76, Plano Diretor Norte, Palmas, TO",
        )
