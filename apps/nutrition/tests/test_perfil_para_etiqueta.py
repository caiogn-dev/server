"""O perfil nutricional entrega à etiqueta o que a tabela ANVISA imprime além
dos nutrientes: a declaração de ingredientes (ordem decrescente de peso) e
as porções por embalagem da receita."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.nutrition.models import NutritionIngredient, ProductNutritionProfile, ProductRecipe, RecipeItem
from apps.stores.models import Store, StoreProduct, StoreSubscription

User = get_user_model()


class PerfilParaEtiquetaTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dona-n', email='dona-n@t.local', password='x')
        self.store = Store.objects.create(name='Loja N', slug='loja-n', owner=self.owner, status='active')
        StoreSubscription.objects.create(store=self.store, plan='pro', status='active', adicionais={'etiqueta_anvisa': {}})
        self.product = StoreProduct.objects.create(store=self.store, name='Bowl', price=Decimal('30'))
        self.recipe = ProductRecipe.objects.create(product=self.product, serving_size_g=350, household_measure='1 pote', servings_per_container=2)
        for nome, q in (('Frango', 150), ('Arroz integral', 120), ('Azeite', 10)):
            ing = NutritionIngredient.objects.create(store=self.store, canonical_name=nome.lower(), display_name=nome)
            RecipeItem.objects.create(recipe=self.recipe, ingredient=ing, quantity_g=q)
        self.profile = ProductNutritionProfile.objects.create(product=self.product, recipe=self.recipe, serving_size_g=350)
        self.client.force_authenticate(self.owner)

    def test_perfil_traz_ingredientes_em_ordem_de_peso_e_porcoes(self):
        r = self.client.get(f'/api/v1/nutrition/profiles/{self.profile.id}/')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['ingredientes_declaracao'], 'Frango, arroz integral, azeite')
        self.assertEqual(float(r.data['porcoes_por_embalagem']), 2.0)
