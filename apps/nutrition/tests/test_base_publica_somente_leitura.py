"""
A base oficial é de todas as lojas — ninguém edita a de ninguém.

A recusa já existia (no `validate` do serializer, não no viewset). O problema
era o outro lado: 17 alimentos oficiais estão EM USO nas receitas da loja, e
como ela não pode editá-los, nunca conseguiria revisar o alergênico deles —
e sem isso a etiqueta se recusa a declarar qualquer coisa, para sempre.

Adotar resolve: a loja ganha uma cópia sua, repontuando as receitas DELA. A
receita de outra loja continua no oficial, que é o certo — alergênico revisado
por um lojista não pode virar afirmação na etiqueta de outro.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.nutrition.models import NutritionIngredient, ProductRecipe, RecipeItem
from apps.stores.models import Store, StoreProduct


class BasePublicaTest(TestCase):
    def setUp(self):
        self.dona = get_user_model().objects.create_user(
            username="dona", email="dona@t.local", password="x")
        self.loja = Store.objects.create(name="Minha", slug="minha-loja", owner=self.dona)
        self.oficial = NutritionIngredient.objects.create(
            store=None, canonical_name="alface, crespa, crua", display_name="Alface, crespa, crua",
            source="taco", source_code="123", energy_kcal=10, allergens_reviewed=False)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.dona).key}")
        self.url = f"/api/v1/nutrition/ingredients/{self.oficial.id}/"

    def test_loja_nao_edita_alimento_oficial(self):
        # A regra vive no serializer (validate), então recusa como 400 e não
        # como 403. O que importa é que o alimento oficial não muda.
        r = self.client.patch(self.url, {"allergens_reviewed": True}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("somente leitura", r.content.decode())

        self.oficial.refresh_from_db()
        self.assertFalse(self.oficial.allergens_reviewed)

    def test_adotar_cria_copia_da_loja(self):
        r = self.client.post(f"{self.url}adotar/", {"store": str(self.loja.id)}, format="json")

        self.assertEqual(r.status_code, 201)
        copia = NutritionIngredient.objects.get(store=self.loja, canonical_name="alface, crespa, crua")
        self.assertEqual(copia.energy_kcal, self.oficial.energy_kcal)
        self.assertNotEqual(copia.id, self.oficial.id)

    def test_copia_nasce_nao_revisada(self):
        # Adotar é dizer "quero cuidar deste", não "já conferi".
        self.oficial.allergens_reviewed = True
        self.oficial.save()
        self.client.post(f"{self.url}adotar/", {"store": str(self.loja.id)}, format="json")

        copia = NutritionIngredient.objects.get(store=self.loja)
        self.assertFalse(copia.allergens_reviewed)

    def test_adotar_repontua_as_receitas_da_loja(self):
        produto = StoreProduct.objects.create(store=self.loja, name="Salada", slug="salada", price=10)
        receita = ProductRecipe.objects.create(product=produto, serving_size_g=100)
        item = RecipeItem.objects.create(recipe=receita, ingredient=self.oficial, quantity_g=50)

        r = self.client.post(f"{self.url}adotar/", {"store": str(self.loja.id)}, format="json")

        self.assertEqual(r.json()["itens_repontuados"], 1)
        item.refresh_from_db()
        self.assertEqual(item.ingredient.store_id, self.loja.id)

    def test_receita_de_outra_loja_continua_no_oficial(self):
        outra_dona = get_user_model().objects.create_user(
            username="outra", email="outra@t.local", password="x")
        outra = Store.objects.create(name="Outra", slug="outra-loja", owner=outra_dona)
        produto = StoreProduct.objects.create(store=outra, name="Prato", slug="prato-o", price=10)
        receita = ProductRecipe.objects.create(product=produto, serving_size_g=100)
        item = RecipeItem.objects.create(recipe=receita, ingredient=self.oficial, quantity_g=50)

        self.client.post(f"{self.url}adotar/", {"store": str(self.loja.id)}, format="json")

        item.refresh_from_db()
        self.assertEqual(item.ingredient_id, self.oficial.id)

    def test_adotar_duas_vezes_nao_duplica(self):
        self.client.post(f"{self.url}adotar/", {"store": str(self.loja.id)}, format="json")
        self.client.post(f"{self.url}adotar/", {"store": str(self.loja.id)}, format="json")

        self.assertEqual(NutritionIngredient.objects.filter(store=self.loja).count(), 1)

    def test_nao_adota_para_loja_alheia(self):
        alheia = Store.objects.create(
            name="Alheia", slug="alheia",
            owner=get_user_model().objects.create_user(username="z", email="z@t.local", password="x"))

        r = self.client.post(f"{self.url}adotar/", {"store": str(alheia.id)}, format="json")

        self.assertEqual(r.status_code, 403)

    def test_ingrediente_ja_da_loja_nao_se_adota(self):
        meu = NutritionIngredient.objects.create(
            store=self.loja, canonical_name="meu", display_name="Meu", source="manual")
        r = self.client.post(f"/api/v1/nutrition/ingredients/{meu.id}/adotar/",
                             {"store": str(self.loja.id)}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_loja_continua_editando_o_que_e_dela(self):
        meu = NutritionIngredient.objects.create(
            store=self.loja, canonical_name="meu", display_name="Meu", source="manual")
        r = self.client.patch(f"/api/v1/nutrition/ingredients/{meu.id}/",
                              {"allergens_reviewed": True}, format="json")
        self.assertEqual(r.status_code, 200)
