"""Avaliação de pedido (StoreReview) — cliente avalia via access_token, sem login."""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder, StoreReview

User = get_user_model()


def _make_order(store, status='delivered'):
    return StoreOrder.objects.create(
        store=store,
        status=status,
        subtotal=50,
        total=50,
    )


class OrderReviewTests(APITestCase):
    def setUp(self):
        # Throttle anônimo usa cache — limpar para isolar os testes
        from django.core.cache import cache
        cache.clear()
        self.owner = User.objects.create_user(
            username='owner-review', email='owner-review@test.com', password='x',
        )
        self.store = Store.objects.create(
            name='Loja Review', slug='loja-review', owner=self.owner, status='active',
        )
        self.order = _make_order(self.store)
        self.url = f'/api/v1/stores/orders/by-token/{self.order.access_token}/review/'

    def test_cria_avaliacao_com_token_valido(self):
        resp = self.client.post(self.url, {'rating': 5, 'comment': 'Excelente!'}, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        review = StoreReview.objects.get(order=self.order)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.comment, 'Excelente!')
        self.assertEqual(review.store, self.store)

    def test_rating_obrigatorio_entre_1_e_5(self):
        for bad in (0, 6, None):
            resp = self.client.post(self.url, {'rating': bad}, format='json')
            self.assertEqual(resp.status_code, 400, f'rating={bad}')

    def test_nao_permite_avaliar_duas_vezes(self):
        self.client.post(self.url, {'rating': 4}, format='json')
        resp = self.client.post(self.url, {'rating': 1}, format='json')
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(StoreReview.objects.get(order=self.order).rating, 4)

    def test_token_invalido_404(self):
        resp = self.client.post(
            '/api/v1/stores/orders/by-token/token-inexistente/review/',
            {'rating': 5}, format='json',
        )
        self.assertEqual(resp.status_code, 404)

    def test_pedido_nao_entregue_nao_pode_avaliar(self):
        order = _make_order(self.store, status='preparing')
        url = f'/api/v1/stores/orders/by-token/{order.access_token}/review/'
        resp = self.client.post(url, {'rating': 5}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_get_retorna_avaliacao_existente(self):
        self.client.post(self.url, {'rating': 3, 'comment': 'ok'}, format='json')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['rating'], 3)

    def test_get_sem_avaliacao_404(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 404)

    def test_lojista_lista_avaliacoes_da_loja(self):
        self.client.post(self.url, {'rating': 5, 'comment': 'top'}, format='json')
        self.client.force_authenticate(self.owner)
        resp = self.client.get(f'/api/v1/stores/{self.store.slug}/reviews/')
        self.assertEqual(resp.status_code, 200, resp.content)
        results = resp.data.get('results', resp.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['rating'], 5)

    def test_lista_de_avaliacoes_exige_auth(self):
        resp = self.client.get(f'/api/v1/stores/{self.store.slug}/reviews/')
        self.assertIn(resp.status_code, (401, 403))
