"""Prova social: catálogo público expõe nota média e contagem de avaliações da loja."""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder, StoreReview

User = get_user_model()


class StoreRatingCatalogTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner-rating', email='owner-rating@test.com', password='x',
        )
        self.store = Store.objects.create(
            name='Loja Rating', slug='loja-rating', owner=self.owner, status='active',
        )
        self.url = f'/api/v1/stores/{self.store.slug}/catalog/'

    def _review(self, rating, public=True):
        order = StoreOrder.objects.create(store=self.store, status='delivered', subtotal=10, total=10)
        return StoreReview.objects.create(store=self.store, order=order, rating=rating, is_public=public)

    def test_sem_avaliacoes_rating_nulo_e_contagem_zero(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200, resp.content)
        store = resp.data['store']
        self.assertIsNone(store['avg_rating'])
        self.assertEqual(store['reviews_count'], 0)

    def test_media_e_contagem_de_avaliacoes_publicas(self):
        self._review(5)
        self._review(4)
        self._review(3)
        resp = self.client.get(self.url)
        store = resp.data['store']
        self.assertEqual(store['avg_rating'], 4.0)
        self.assertEqual(store['reviews_count'], 3)

    def test_avaliacao_oculta_nao_conta(self):
        self._review(5)
        self._review(1, public=False)
        resp = self.client.get(self.url)
        store = resp.data['store']
        self.assertEqual(store['reviews_count'], 1)
        self.assertEqual(store['avg_rating'], 5.0)
