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


class ProductReviewItemTests(APITestCase):
    """Avaliação por produto (StoreProductReview) — mockup 'avaliações por produto'."""

    def setUp(self):
        from django.core.cache import cache
        from apps.stores.models import StoreOrderItem, StoreProduct
        cache.clear()
        self.owner = User.objects.create_user(
            username='owner-prev', email='owner-prev@test.com', password='x',
        )
        self.store = Store.objects.create(
            name='Loja PRev', slug='loja-prev', owner=self.owner, status='active',
        )
        self.caesar = StoreProduct.objects.create(
            store=self.store, name='Salada Caesar', slug='caesar', price=24.90, status='active', sku='C1',
        )
        self.suco = StoreProduct.objects.create(
            store=self.store, name='Suco Verde', slug='suco', price=12, status='active', sku='S1',
        )
        self.fora_do_pedido = StoreProduct.objects.create(
            store=self.store, name='Item Fora', slug='fora', price=9, status='active', sku='F1',
        )
        self.order = _make_order(self.store)
        for prod in (self.caesar, self.suco):
            StoreOrderItem.objects.create(
                order=self.order, product=prod, product_name=prod.name,
                unit_price=prod.price, quantity=1, subtotal=prod.price,
            )
        self.url = f'/api/v1/stores/orders/by-token/{self.order.access_token}/review/'

    def _post(self, payload):
        return self.client.post(self.url, payload, format='json')

    def test_cria_review_com_notas_por_item(self):
        from apps.stores.models import StoreProductReview
        resp = self._post({
            'rating': 5,
            'items': [
                {'product': str(self.caesar.id), 'rating': 5},
                {'product': str(self.suco.id), 'rating': 4},
            ],
        })
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(StoreProductReview.objects.filter(review__order=self.order).count(), 2)
        self.assertEqual(
            StoreProductReview.objects.get(product=self.suco).rating, 4,
        )

    def test_items_opcional_mantem_compat(self):
        resp = self._post({'rating': 4})
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_produto_fora_do_pedido_400(self):
        from apps.stores.models import StoreProductReview
        resp = self._post({
            'rating': 5,
            'items': [{'product': str(self.fora_do_pedido.id), 'rating': 5}],
        })
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(StoreProductReview.objects.count(), 0)
        self.assertEqual(StoreReview.objects.count(), 0)

    def test_rating_de_item_fora_da_faixa_400(self):
        resp = self._post({
            'rating': 5,
            'items': [{'product': str(self.caesar.id), 'rating': 6}],
        })
        self.assertEqual(resp.status_code, 400)

    def test_produto_duplicado_no_payload_400(self):
        resp = self._post({
            'rating': 5,
            'items': [
                {'product': str(self.caesar.id), 'rating': 5},
                {'product': str(self.caesar.id), 'rating': 1},
            ],
        })
        self.assertEqual(resp.status_code, 400)

    def _review_other_order(self, product_ratings, is_public=True):
        from apps.stores.models import StoreOrderItem, StoreProductReview
        order = _make_order(self.store)
        for prod, _ in product_ratings:
            StoreOrderItem.objects.create(
                order=order, product=prod, product_name=prod.name,
                unit_price=prod.price, quantity=1, subtotal=prod.price,
            )
        review = StoreReview.objects.create(
            store=self.store, order=order, rating=5, is_public=is_public,
        )
        for prod, rating in product_ratings:
            StoreProductReview.objects.create(review=review, product=prod, rating=rating)
        return review

    def test_catalogo_expoe_media_por_produto(self):
        self._review_other_order([(self.caesar, 5), (self.suco, 4)])
        self._review_other_order([(self.caesar, 3)])
        resp = self.client.get(f'/api/v1/stores/{self.store.slug}/catalog/')
        self.assertEqual(resp.status_code, 200, resp.content)
        by_name = {p['name']: p for p in resp.data['products']}
        self.assertEqual(by_name['Salada Caesar']['rating_count'], 2)
        self.assertEqual(float(by_name['Salada Caesar']['rating_avg']), 4.0)
        self.assertEqual(by_name['Suco Verde']['rating_count'], 1)
        self.assertEqual(by_name['Item Fora']['rating_count'], 0)
        self.assertIsNone(by_name['Item Fora']['rating_avg'])

    def test_review_oculto_nao_conta_na_media(self):
        self._review_other_order([(self.caesar, 5)])
        self._review_other_order([(self.caesar, 1)], is_public=False)
        resp = self.client.get(f'/api/v1/stores/{self.store.slug}/catalog/')
        by_name = {p['name']: p for p in resp.data['products']}
        self.assertEqual(by_name['Salada Caesar']['rating_count'], 1)
        self.assertEqual(float(by_name['Salada Caesar']['rating_avg']), 5.0)
