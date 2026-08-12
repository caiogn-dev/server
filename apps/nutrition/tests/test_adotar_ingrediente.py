"""Adotar um alimento oficial (TACO/POF) para dentro da loja.

O catálogo oficial é compartilhado por todos os lojistas, então é somente
leitura — o dono da Cê Saladas não pode marcar "sem glúten" num arroz que
aparece também na loja do vizinho.

Só que a etiqueta se recusa a declarar alergênico enquanto houver ingrediente
não revisado na receita, e nenhum alimento oficial pode ser revisado por um
lojista. Resultado em produção (12/ago): as 27 receitas usavam ingredientes da
base e NENHUMA conseguia declarar nada — a tela oferecia um botão de revisar
que só sabia responder 400.

`POST /nutrition/ingredients/{id}/adotar/` resolve pelo caminho honesto: cria
uma CÓPIA do alimento dentro da loja, editável e revisável, e reaponta as
receitas daquela loja para a cópia. O oficial fica intocado.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.nutrition.models import NutritionIngredient, ProductRecipe, RecipeItem
from apps.stores.models import Store, StoreProduct

User = get_user_model()


class AdotarIngredienteTest(TestCase):
    def setUp(self):
        self.dono = User.objects.create_user(username='dono-nut', password='x')
        self.store = Store.objects.create(
            name='Loja NUT', slug='loja-nut', owner=self.dono, status='active',
        )
        self.oficial = NutritionIngredient.objects.create(
            canonical_name='Arroz, integral, cozido',
            display_name='Arroz, integral, cozido',
            category='Cereais', source='taco', source_code='TACO-001',
            energy_kcal=124, protein_g=2.6, carbohydrates_g=25.8,
        )
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=self.dono).key}',
        )

    def _adotar(self, **payload):
        return self.client.post(
            f'/api/v1/nutrition/ingredients/{self.oficial.id}/adotar/',
            {'store': str(self.store.id), **payload}, format='json',
        )

    def test_lojista_nao_pode_editar_o_oficial(self):
        """A trava que motiva tudo isso continua de pé."""
        r = self.client.patch(
            f'/api/v1/nutrition/ingredients/{self.oficial.id}/',
            {'allergens_reviewed': True}, format='json',
        )
        self.assertEqual(r.status_code, 400)
        self.oficial.refresh_from_db()
        self.assertFalse(self.oficial.allergens_reviewed)

    def test_adotar_cria_copia_na_loja_sem_tocar_no_oficial(self):
        r = self._adotar()

        self.assertEqual(r.status_code, 201, r.data)
        copia = NutritionIngredient.objects.get(id=r.data['id'])
        self.assertEqual(copia.store_id, self.store.id)
        self.assertEqual(copia.display_name, self.oficial.display_name)
        self.assertEqual(copia.energy_kcal, self.oficial.energy_kcal)
        # Procedência preservada: a cópia não vira "manual" e perde a fonte.
        self.assertEqual(copia.source, 'taco')
        self.assertEqual(copia.source_code, 'TACO-001')
        self.oficial.refresh_from_db()
        self.assertIsNone(self.oficial.store_id)

    def test_adotar_aceita_a_revisao_de_alergenicos_na_mesma_chamada(self):
        """O lojista clica no alimento, marca os alergênicos e salva uma vez."""
        r = self._adotar(allergens=['soja'], may_contain=['trigo'],
                         allergens_reviewed=True)

        copia = NutritionIngredient.objects.get(id=r.data['id'])
        self.assertEqual(copia.allergens, ['soja'])
        self.assertEqual(copia.may_contain, ['trigo'])
        self.assertTrue(copia.allergens_reviewed)

    def test_adotar_reaponta_as_receitas_da_loja(self):
        """Sem isso a cópia nasce órfã e a etiqueta continua travada."""
        produto = StoreProduct.objects.create(
            store=self.store, name='Bowl', slug='bowl', price=30,
        )
        receita = ProductRecipe.objects.create(product=produto, serving_size_g=100)
        item = RecipeItem.objects.create(
            recipe=receita, ingredient=self.oficial, quantity_g=80,
        )

        r = self._adotar(allergens_reviewed=True)

        item.refresh_from_db()
        self.assertEqual(str(item.ingredient_id), r.data['id'])

    def test_adotar_nao_toca_em_receita_de_outra_loja(self):
        outro = User.objects.create_user(username='outro-nut', password='x')
        vizinha = Store.objects.create(
            name='Vizinha', slug='vizinha-nut', owner=outro, status='active',
        )
        produto = StoreProduct.objects.create(
            store=vizinha, name='Prato', slug='prato-viz', price=20,
        )
        receita = ProductRecipe.objects.create(product=produto, serving_size_g=100)
        item = RecipeItem.objects.create(
            recipe=receita, ingredient=self.oficial, quantity_g=50,
        )

        self._adotar()

        item.refresh_from_db()
        self.assertEqual(item.ingredient_id, self.oficial.id)

    def test_adotar_duas_vezes_devolve_a_mesma_copia(self):
        primeira = self._adotar()
        segunda = self._adotar(allergens_reviewed=True)

        self.assertEqual(segunda.status_code, 200, segunda.data)
        self.assertEqual(primeira.data['id'], segunda.data['id'])
        self.assertEqual(
            NutritionIngredient.objects.filter(
                store=self.store, canonical_name=self.oficial.canonical_name,
            ).count(), 1,
        )
        # A segunda chamada ainda aplica a revisão.
        self.assertTrue(
            NutritionIngredient.objects.get(id=segunda.data['id']).allergens_reviewed
        )

    def test_alergenico_invalido_devolve_400_e_nao_500(self):
        """Erro de preenchimento tem que apontar o campo, não virar 'erro interno'."""
        r = self._adotar(allergens=['gluten'])  # a chave certa é 'trigo'

        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn('allergens', r.data['error']['details'])

    def test_nao_adota_para_loja_de_outro_dono(self):
        outro = User.objects.create_user(username='intruso-nut', password='x')
        alheia = Store.objects.create(
            name='Alheia', slug='alheia-nut', owner=outro, status='active',
        )

        r = self.client.post(
            f'/api/v1/nutrition/ingredients/{self.oficial.id}/adotar/',
            {'store': str(alheia.id)}, format='json',
        )

        self.assertIn(r.status_code, (400, 403))
        self.assertFalse(NutritionIngredient.objects.filter(store=alheia).exists())

    def test_nao_adota_ingrediente_que_ja_e_de_loja(self):
        proprio = NutritionIngredient.objects.create(
            store=self.store, canonical_name='Molho da casa',
            display_name='Molho da casa', source='manual',
        )

        r = self.client.post(
            f'/api/v1/nutrition/ingredients/{proprio.id}/adotar/',
            {'store': str(self.store.id)}, format='json',
        )

        self.assertEqual(r.status_code, 400)
