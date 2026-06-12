"""Pausa rápida de produto (paused_until) — item esgotado some do cardápio em 1 clique."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreProduct

User = get_user_model()


def _make_store(owner):
    return Store.objects.create(
        name='Loja Teste', slug='loja-teste-pause', owner=owner, status='active',
    )


class ProductPauseModelTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner-pause', email='owner-pause@test.com', password='x',
        )
        self.store = _make_store(self.owner)
        self.product = StoreProduct.objects.create(
            store=self.store, name='Salada', price=30, track_stock=False,
        )

    def test_produto_sem_pausa_esta_disponivel(self):
        self.assertFalse(self.product.is_paused)
        self.assertTrue(self.product.is_in_stock)

    def test_produto_pausado_fica_indisponivel(self):
        self.product.paused_until = timezone.now() + timedelta(hours=2)
        self.product.save()
        self.assertTrue(self.product.is_paused)
        self.assertFalse(self.product.is_in_stock)

    def test_pausa_expirada_volta_a_disponivel(self):
        self.product.paused_until = timezone.now() - timedelta(minutes=1)
        self.product.save()
        self.assertFalse(self.product.is_paused)
        self.assertTrue(self.product.is_in_stock)


class ProductPauseAPITests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner-pause-api', email='owner-pause-api@test.com', password='x',
        )
        self.store = _make_store(self.owner)
        self.product = StoreProduct.objects.create(
            store=self.store, name='Suco', price=10, track_stock=False,
        )
        self.client.force_authenticate(self.owner)
        # Rota flat usada pelo pastita-dash (router products em apps/stores/urls.py:125)
        self.base = f'/api/v1/stores/products/{self.product.id}'

    def test_pause_endpoint_define_paused_until(self):
        resp = self.client.post(f'{self.base}/pause/', {'minutes': 120}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.product.refresh_from_db()
        self.assertIsNotNone(self.product.paused_until)
        self.assertTrue(self.product.is_paused)
        self.assertTrue(resp.data['is_paused'])

    def test_pause_sem_minutes_pausa_ate_amanha(self):
        resp = self.client.post(f'{self.base}/pause/', {}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.product.refresh_from_db()
        tomorrow = (timezone.localtime() + timedelta(days=1)).date()
        self.assertEqual(timezone.localtime(self.product.paused_until).date(), tomorrow)

    def test_unpause_endpoint_limpa_pausa(self):
        self.product.paused_until = timezone.now() + timedelta(hours=4)
        self.product.save()
        resp = self.client.post(f'{self.base}/unpause/', {}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.product.refresh_from_db()
        self.assertIsNone(self.product.paused_until)
        self.assertFalse(resp.data['is_paused'])

    def test_pause_exige_autenticacao(self):
        self.client.force_authenticate(None)
        resp = self.client.post(f'{self.base}/pause/', {'minutes': 60}, format='json')
        self.assertIn(resp.status_code, (401, 403))
