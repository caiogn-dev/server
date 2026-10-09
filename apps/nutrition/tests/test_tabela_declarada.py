"""
Tabela nutricional PRONTA, entregue pela loja (laudo/nutricionista), não calculada.

A Agrião mandou 32 PDFs da Linha FIT (09/10). Guardar só o valor por 100 g e
recalcular a porção quebra a tabela: 209 kcal × 3,3 = 689,7, e o PDF declara
691 (o nutricionista arredonda a partir do valor cru). Etiqueta é declaração —
o que sai impresso tem de ser o que o responsável assinou, número por número.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.nutrition.models import ProductNutritionProfile
from apps.stores.models import Store, StoreProduct

TABELA = {
    "porcoes_por_embalagem": "1",
    "porcao": "330 g (1 marmita)",
    "coluna_porcao": "330 g",
    "linhas": {
        "energy_kcal": ["209", "691", "35"],
        "carbohydrates_g": ["21", "68", "23"],
        "total_sugars_g": ["1,7", "5,6", ""],
        "added_sugars_g": ["0", "0", "0"],
        "protein_g": ["16", "53", "106"],
        "total_fat_g": ["6,6", "22", "34"],
        "saturated_fat_g": ["1,7", "5,7", "29"],
        "trans_fat_g": ["0,1", "0,2", "10"],
        "fiber_g": ["0,8", "2,8", "11"],
        "sodium_mg": ["368", "1216", "61"],
    },
    "ingredientes": "Filé de peito de frango, leite zero lactose, farinha de trigo.",
    "declaracoes": ["ZERO LACTOSE", "CONTÉM GLÚTEN"],
}


class TabelaDeclaradaTest(TestCase):
    def setUp(self):
        dono = get_user_model().objects.create_user(username="agriao", email="a@t.local", password="x")
        self.store = Store.objects.create(name="Agrião", slug="agriao-td", owner=dono, billing_exempt=True)
        self.produto = StoreProduct.objects.create(store=self.store, name="Parmegiana", slug="parm", price=Decimal("30"))
        self.perfil = ProductNutritionProfile.objects.create(
            product=self.produto, value_source=ProductNutritionProfile.ValueSource.MANUAL,
            serving_size_g=330, energy_kcal=209, sodium_mg=368, tabela_declarada=TABELA,
        )
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=dono).key}")

    def test_api_entrega_a_tabela_e_os_ingredientes_declarados(self):
        r = self.client.get(f"/api/v1/nutrition/profiles/{self.perfil.id}/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["tabela_declarada"]["linhas"]["energy_kcal"], ["209", "691", "35"])
        # Sem receita, a etiqueta não teria ingrediente nenhum para imprimir.
        self.assertEqual(r.data["ingredientes_declaracao"], TABELA["ingredientes"])
        self.assertEqual(str(r.data["porcoes_por_embalagem"]), "1")

    def test_pagina_publica_imprime_a_porcao_declarada_nao_a_recalculada(self):
        html = self.client.get(f"/api/v1/nutrition/public/{self.produto.id}/").content.decode()
        self.assertIn("691", html)
        self.assertNotIn("689,7", html)
        self.assertIn("1216", html)       # sódio da porção
        self.assertIn("106", html)        # %VD de proteína
        self.assertIn("CONTÉM GLÚTEN", html)
        self.assertIn("ZERO LACTOSE", html)
        self.assertIn("farinha de trigo", html)
        self.assertNotIn("estimados a partir da composição", html)

    def test_tabela_malformada_e_recusada(self):
        r = self.client.patch(
            f"/api/v1/nutrition/profiles/{self.perfil.id}/",
            {"tabela_declarada": {"linhas": {"energy_kcal": ["209"]}}}, format="json",
        )
        self.assertEqual(r.status_code, 400)
