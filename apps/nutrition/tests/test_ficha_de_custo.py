"""Ficha técnica de CUSTO: quanto custa o prato e quanto sobra do preço.

A receita já era ingrediente × quantidade para a tabela nutricional. Com o
preço que o lojista PAGOU em cada ingrediente, a mesma receita responde a
pergunta que decide se o prato se paga: custo, CMV e margem bruta.

A regra é a mesma de `incomplete_ingredients`: nunca inventar zero. Um
ingrediente sem preço deixa o custo do prato em branco e diz QUEM falta — um
custo "parcial" mostraria margem maior do que a real, que é o erro que custa
dinheiro.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.utils.text import slugify
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.nutrition.models import NutritionIngredient, ProductRecipe, RecipeItem
from apps.nutrition.services.calculator import calculate_recipe
from apps.nutrition.services.custo import custo_por_g_ml, ficha_de_custo
from apps.stores.models import Store, StoreProduct

User = get_user_model()


def _ing(**campos):
    padrao = dict(default_unit="g", density_g_ml=None, preco_pago=None,
                  quantidade_comprada=None, unidade_compra="", quantidade_por_unidade=None)
    padrao.update(campos)
    return NutritionIngredient(**padrao)


class CustoPorGramaTest(SimpleTestCase):
    def test_comprado_na_mesma_unidade_da_receita(self):
        # R$ 30 por 1 kg de queijo = R$ 0,03 por grama.
        ing = _ing(preco_pago=Decimal("30"), quantidade_comprada=Decimal("1000"), unidade_compra="g")
        self.assertEqual(custo_por_g_ml(ing), Decimal("0.03"))

    def test_comprado_por_unidade_usa_o_conteudo_de_cada_unidade(self):
        # Bandeja de 30 ovos por R$ 24, cada ovo 50 g → R$ 0,016/g.
        ing = _ing(preco_pago=Decimal("24"), quantidade_comprada=Decimal("30"),
                   unidade_compra="un", quantidade_por_unidade=Decimal("50"))
        self.assertEqual(custo_por_g_ml(ing), Decimal("0.016"))

    def test_comprado_em_ml_e_receita_em_g_converte_pela_densidade(self):
        # Azeite: 500 ml por R$ 46, densidade 0,92 → 460 g → R$ 0,1/g.
        ing = _ing(preco_pago=Decimal("46"), quantidade_comprada=Decimal("500"),
                   unidade_compra="ml", density_g_ml=Decimal("0.92"))
        self.assertEqual(custo_por_g_ml(ing), Decimal("0.1"))

    def test_ml_contra_g_sem_densidade_nao_inventa_equivalencia(self):
        ing = _ing(preco_pago=Decimal("46"), quantidade_comprada=Decimal("500"), unidade_compra="ml")
        self.assertIsNone(custo_por_g_ml(ing))

    def test_sem_preco_e_none_e_nao_zero(self):
        self.assertIsNone(custo_por_g_ml(_ing()))


class ValidacaoDoPrecoTest(SimpleTestCase):
    def test_alimento_oficial_nao_tem_preco(self):
        ing = _ing(preco_pago=Decimal("10"), quantidade_comprada=Decimal("1000"), unidade_compra="g")
        with self.assertRaises(ValidationError) as erro:
            ing.clean()
        self.assertIn("preco_pago", erro.exception.message_dict)

    def test_preco_pela_metade_e_recusado(self):
        ing = _ing(store_id="00000000-0000-0000-0000-000000000001", preco_pago=Decimal("10"))
        with self.assertRaises(ValidationError) as erro:
            ing.clean()
        self.assertIn("quantidade_comprada", erro.exception.message_dict)

    def test_quantidade_zero_e_recusada(self):
        ing = _ing(store_id="00000000-0000-0000-0000-000000000001", preco_pago=Decimal("10"),
                   quantidade_comprada=Decimal("0"), unidade_compra="g")
        with self.assertRaises(ValidationError) as erro:
            ing.clean()
        self.assertIn("quantidade_comprada", erro.exception.message_dict)

    def test_por_unidade_exige_o_conteudo_da_unidade(self):
        ing = _ing(store_id="00000000-0000-0000-0000-000000000001", preco_pago=Decimal("24"),
                   quantidade_comprada=Decimal("30"), unidade_compra="un")
        with self.assertRaises(ValidationError) as erro:
            ing.clean()
        self.assertIn("quantidade_por_unidade", erro.exception.message_dict)


class FichaDeCustoTest(SimpleTestCase):
    def _calculo(self, custo):
        return {"custo_total": custo, "custo_por_porcao": custo, "ingredientes_sem_preco": []}

    def test_margem_e_cmv(self):
        f = ficha_de_custo(self._calculo(Decimal("7.50")), Decimal("25.00"))
        self.assertEqual(f["preco_de_venda"], Decimal("25.00"))
        self.assertEqual(f["margem_bruta_valor"], Decimal("17.50"))
        self.assertEqual(f["margem_bruta_pct"], Decimal("70.0"))
        self.assertEqual(f["cmv_pct"], Decimal("30.0"))

    def test_sem_custo_nao_ha_margem(self):
        f = ficha_de_custo(self._calculo(None), Decimal("25.00"))
        self.assertIsNone(f["margem_bruta_valor"])
        self.assertIsNone(f["margem_bruta_pct"])
        self.assertIsNone(f["cmv_pct"])

    def test_preco_zero_nao_divide(self):
        f = ficha_de_custo(self._calculo(Decimal("5")), Decimal("0"))
        self.assertEqual(f["margem_bruta_valor"], Decimal("-5.00"))
        self.assertIsNone(f["margem_bruta_pct"])
        self.assertIsNone(f["cmv_pct"])


class Cenario(TestCase):
    def setUp(self):
        self.dono = User.objects.create_user(username="dono-custo", password="x")
        self.loja = Store.objects.create(name="Loja Custo", slug="loja-custo", owner=self.dono, status="active")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.dono).key}")

    def ingrediente(self, nome, preco=None, quantidade=None, loja=True, **extra):
        return NutritionIngredient.objects.create(
            store=self.loja if loja else None, canonical_name=nome, display_name=nome,
            preco_pago=preco, quantidade_comprada=quantidade,
            unidade_compra="g" if preco is not None else "", **extra)

    def receita(self, nome, preco_venda, itens, serving=100):
        produto = StoreProduct.objects.create(store=self.loja, name=nome, slug=slugify(nome),
                                              price=Decimal(preco_venda))
        receita = ProductRecipe.objects.create(product=produto, serving_size_g=Decimal(serving))
        for ing, gramas in itens:
            RecipeItem.objects.create(recipe=receita, ingredient=ing, quantity_g=Decimal(gramas))
        return produto, receita


class CustoDaReceitaTest(Cenario):
    def test_custo_total_e_por_porcao(self):
        alface = self.ingrediente("Alface", Decimal("10"), Decimal("1000"))   # 0,01/g
        frango = self.ingrediente("Frango", Decimal("40"), Decimal("1000"))   # 0,04/g
        _, receita = self.receita("Salada", "30", [(alface, 200), (frango, 200)], serving=100)
        calc = calculate_recipe(receita)
        self.assertEqual(calc["custo_total"], Decimal("10.00"))
        # 400 g no total, porção de 100 g → um quarto do custo.
        self.assertEqual(calc["custo_por_porcao"], Decimal("2.50"))
        self.assertEqual(calc["ingredientes_sem_preco"], [])

    def test_ingrediente_sem_preco_deixa_o_custo_em_branco_e_diz_quem(self):
        alface = self.ingrediente("Alface", Decimal("10"), Decimal("1000"))
        arroz = self.ingrediente("Arroz TACO", loja=False)
        _, receita = self.receita("Salada", "30", [(alface, 200), (arroz, 100)])
        calc = calculate_recipe(receita)
        self.assertIsNone(calc["custo_total"])
        self.assertIsNone(calc["custo_por_porcao"])
        self.assertEqual(calc["ingredientes_sem_preco"], ["Arroz TACO"])

    def test_serializer_da_receita_expoe_custo_e_margem(self):
        alface = self.ingrediente("Alface", Decimal("10"), Decimal("1000"))
        produto, receita = self.receita("Salada", "20", [(alface, 500)])
        r = self.client.get(f"/api/v1/nutrition/recipes/{receita.id}/")
        self.assertEqual(r.status_code, 200)
        custo = r.data["custo"]
        self.assertEqual(custo["custo_total"], Decimal("5.00"))
        self.assertEqual(custo["preco_de_venda"], Decimal("20.00"))
        self.assertEqual(custo["margem_bruta_valor"], Decimal("15.00"))
        self.assertEqual(custo["margem_bruta_pct"], Decimal("75.0"))
        self.assertEqual(custo["cmv_pct"], Decimal("25.0"))
        self.assertEqual(custo["ingredientes_sem_preco"], [])

    def test_serializer_do_perfil_expoe_custo(self):
        alface = self.ingrediente("Alface", Decimal("10"), Decimal("1000"))
        produto, receita = self.receita("Salada", "20", [(alface, 500)])
        from apps.nutrition.models import ProductNutritionProfile
        perfil = ProductNutritionProfile.objects.create(product=produto, recipe=receita)
        r = self.client.get(f"/api/v1/nutrition/profiles/{perfil.id}/")
        self.assertEqual(r.data["custo"]["cmv_pct"], Decimal("25.0"))

    def test_previa_com_produto_traz_margem(self):
        alface = self.ingrediente("Alface", Decimal("10"), Decimal("1000"))
        produto = StoreProduct.objects.create(store=self.loja, name="Salada", price=Decimal("20"))
        r = self.client.post("/api/v1/nutrition/recipes/previa/", {
            "product": str(produto.id), "items": [{"ingredient": str(alface.id), "quantity_g": 500}],
        }, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["custo"]["margem_bruta_pct"], Decimal("75.0"))

    def test_previa_nao_revela_preco_de_produto_de_outra_loja(self):
        outro = User.objects.create_user(username="outro-custo", password="x")
        vizinha = Store.objects.create(name="Vizinha", slug="vizinha-custo", owner=outro, status="active")
        alheio = StoreProduct.objects.create(store=vizinha, name="Segredo", price=Decimal("99"))
        r = self.client.post("/api/v1/nutrition/recipes/previa/", {
            "product": str(alheio.id), "items": [],
        }, format="json")
        self.assertEqual(r.status_code, 404)


class PrecoDoIngredienteApiTest(Cenario):
    def test_lojista_grava_o_preco_e_ve_o_custo_por_grama(self):
        ing = self.ingrediente("Queijo")
        r = self.client.patch(f"/api/v1/nutrition/ingredients/{ing.id}/", {
            "preco_pago": "30.00", "quantidade_comprada": "1000", "unidade_compra": "g",
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(Decimal(r.data["custo_por_g_ml"]), Decimal("0.03"))

    def test_adotar_leva_o_preco_para_a_copia(self):
        oficial = self.ingrediente("Arroz TACO", loja=False, source="taco")
        r = self.client.post(f"/api/v1/nutrition/ingredients/{oficial.id}/adotar/", {
            "store": str(self.loja.id), "preco_pago": "6.00",
            "quantidade_comprada": "1000", "unidade_compra": "g",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        copia = NutritionIngredient.objects.get(store=self.loja, canonical_name="Arroz TACO")
        self.assertEqual(copia.preco_pago, Decimal("6.00"))
        oficial.refresh_from_db()
        self.assertIsNone(oficial.preco_pago)


class ResumoDeCustosDaLojaTest(Cenario):
    URL = "/api/v1/nutrition/custos/"

    def test_pior_margem_primeiro_e_incompletos_no_fim(self):
        barato = self.ingrediente("Alface", Decimal("10"), Decimal("1000"))   # 0,01/g
        caro = self.ingrediente("Camarão", Decimal("100"), Decimal("1000"))   # 0,10/g
        sem = self.ingrediente("Molho")
        self.receita("Salada verde", "20", [(barato, 200)])        # custo 2  → 90%
        self.receita("Camarão", "30", [(caro, 200)])               # custo 20 → 33,3%
        self.receita("Com molho", "25", [(barato, 100), (sem, 50)])  # incompleto

        r = self.client.get(self.URL, {"store": str(self.loja.id)})
        self.assertEqual(r.status_code, 200)
        self.assertEqual([p["produto"] for p in r.data], ["Camarão", "Salada verde", "Com molho"])
        primeiro, _, ultimo = r.data
        self.assertEqual(primeiro["margem_bruta_pct"], Decimal("33.3"))
        self.assertEqual(primeiro["cmv_pct"], Decimal("66.7"))
        self.assertEqual(primeiro["preco_de_venda"], Decimal("30.00"))
        self.assertTrue(primeiro["completo"])
        self.assertFalse(ultimo["completo"])
        self.assertIsNone(ultimo["custo_total"])
        self.assertEqual(ultimo["ingredientes_sem_preco"], ["Molho"])

    def test_so_produtos_da_loja_pedida(self):
        outro = User.objects.create_user(username="outro-resumo", password="x")
        vizinha = Store.objects.create(name="Vizinha", slug="vizinha-resumo", owner=outro, status="active")
        produto = StoreProduct.objects.create(store=vizinha, name="Do vizinho", price=Decimal("10"))
        ProductRecipe.objects.create(product=produto)
        self.receita("Meu prato", "10", [])
        r = self.client.get(self.URL, {"store": str(self.loja.id)})
        self.assertEqual([p["produto"] for p in r.data], ["Meu prato"])

    def test_loja_alheia_e_404_sem_vazar_nada(self):
        outro = User.objects.create_user(username="outro-404", password="x")
        vizinha = Store.objects.create(name="Vizinha", slug="vizinha-404", owner=outro, status="active")
        r = self.client.get(self.URL, {"store": str(vizinha.id)})
        self.assertEqual(r.status_code, 404)

    def test_superuser_sem_vinculo_e_barrado(self):
        admin = User.objects.create_superuser(username="su-custo", email="su@c.local", password="x")
        cliente = APIClient()
        cliente.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=admin).key}")
        r = cliente.get(self.URL, {"store": str(self.loja.id)})
        self.assertEqual(r.status_code, 404)

    def test_membro_da_equipe_ve(self):
        from apps.stores.models import StoreTeamMember
        gerente = User.objects.create_user(username="gerente-custo", password="x")
        StoreTeamMember.objects.create(tenant=self.loja, user=gerente, role="manager", is_active=True)
        cliente = APIClient()
        cliente.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=gerente).key}")
        r = cliente.get(self.URL, {"store": str(self.loja.id)})
        self.assertEqual(r.status_code, 200)

    def test_sem_loja_e_400(self):
        self.assertEqual(self.client.get(self.URL).status_code, 400)

    def test_loja_com_id_invalido_e_404(self):
        self.assertEqual(self.client.get(self.URL, {"store": "nao-e-uuid"}).status_code, 404)
