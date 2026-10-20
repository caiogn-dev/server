"""
Tabela nutricional DENTRO do cardápio (20/10).

O Prefiro mostra a aba "Tabela Nutricional" no modal do prato. Nós tínhamos as
tabelas (48 da Agrião, 34 da Cê) e só uma página HTML solta, para o QR da
embalagem — a vitrine nunca mostrava. Esta é a versão em dados da mesma
etiqueta, para o modal desenhar. Mesmas regras da página: a tabela declarada
sai número por número; sem tabela, 404 e a vitrine esconde a aba.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.nutrition.models import ProductNutritionProfile
from apps.nutrition.tests.test_tabela_declarada import TABELA
from apps.stores.models import Store, StoreProduct


class TabelaNaVitrineTest(TestCase):
    def setUp(self):
        dono = get_user_model().objects.create_user(username="vitrine", email="v@t.local", password="x")
        self.store = Store.objects.create(name="Agrião", slug="agriao-vitrine", owner=dono)
        self.produto = StoreProduct.objects.create(
            store=self.store, name="Parmegiana", slug="parm-v", price=Decimal("30"))
        self.client = APIClient()

    def _dados(self, produto=None):
        return self.client.get(f"/api/v1/nutrition/public/{(produto or self.produto).id}/dados/")

    def test_tabela_declarada_sai_numero_por_numero(self):
        ProductNutritionProfile.objects.create(
            product=self.produto, value_source=ProductNutritionProfile.ValueSource.MANUAL,
            serving_size_g=330, energy_kcal=209, tabela_declarada=TABELA)

        r = self._dados()

        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d["declarada"])
        self.assertEqual(d["porcao"], "330 g (1 marmita)")
        self.assertEqual(d["coluna_porcao"], "330 g")
        energia = d["linhas"][0]
        self.assertEqual(energia, {
            "campo": "energy_kcal", "rotulo": "Valor energético", "unidade": "kcal",
            "por_100": "209", "por_porcao": "691", "vd": "35",
        })
        self.assertEqual(len(d["linhas"]), 10)
        self.assertEqual(d["alergenicos"], ["ZERO LACTOSE", "CONTÉM GLÚTEN"])
        self.assertEqual(d["ingredientes"], TABELA["ingredientes"])

    def test_tabela_calculada_faz_a_conta_da_porcao(self):
        ProductNutritionProfile.objects.create(
            product=self.produto, serving_size_g=150, energy_kcal=200, protein_g=10)

        d = self._dados().json()

        self.assertFalse(d["declarada"])
        self.assertEqual(d["porcao"], "150 g")
        energia = next(l for l in d["linhas"] if l["campo"] == "energy_kcal")
        self.assertEqual((energia["por_100"], energia["por_porcao"], energia["vd"]), ("200", "300", ""))
        sodio = next(l for l in d["linhas"] if l["campo"] == "sodium_mg")
        self.assertEqual(sodio["por_100"], "")

    def test_produto_sem_tabela_e_404(self):
        self.assertEqual(self._dados().status_code, 404)

    def test_tabela_desligada_e_404(self):
        ProductNutritionProfile.objects.create(
            product=self.produto, energy_kcal=200, serving_size_g=100, is_active=False)
        self.assertEqual(self._dados().status_code, 404)

    def test_perfil_vazio_e_404(self):
        ProductNutritionProfile.objects.create(product=self.produto)
        self.assertEqual(self._dados().status_code, 404)
