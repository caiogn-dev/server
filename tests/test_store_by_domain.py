"""
Tests for GET /api/v1/public/store-by-domain/
Endpoint público — sem autenticação — usado pelo storefront wrapper multi-tenant.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.stores.models import Store

User = get_user_model()


def _make_owner():
    return User.objects.create_user(
        username='domain-test-owner',
        email='domaintest@example.com',
        password='unused-test-password',
    )


def _make_active_store(owner):
    return Store.objects.create(
        owner=owner,
        name='Cê Saladas',
        slug='ce-saladas',
        custom_domain='cesaladas.com.br',
        primary_color='#2D6A4F',
        secondary_color='#1B4332',
        template='fresh',
        tagline='Saladas frescas',
        status='active',
    )


class StoreByDomainTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = _make_owner()
        self.store = _make_active_store(self.owner)

    def test_encontra_loja_por_dominio(self):
        url = '/api/v1/public/store-by-domain/?domain=cesaladas.com.br'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['slug'], 'ce-saladas')
        self.assertEqual(data['template'], 'fresh')
        self.assertEqual(data['primary_color'], '#2D6A4F')
        self.assertEqual(data['tagline'], 'Saladas frescas')

    def test_dominio_inexistente_retorna_404(self):
        url = '/api/v1/public/store-by-domain/?domain=naoexiste.com.br'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_sem_parametro_retorna_400(self):
        url = '/api/v1/public/store-by-domain/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)

    def test_loja_inativa_retorna_404(self):
        self.store.status = 'inactive'
        self.store.save()
        url = '/api/v1/public/store-by-domain/?domain=cesaladas.com.br'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_porta_no_dominio_e_ignorada(self):
        url = '/api/v1/public/store-by-domain/?domain=cesaladas.com.br:3000'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['slug'], 'ce-saladas')

    def test_serializer_retorna_template_e_tagline(self):
        """PublicStoreSerializer deve incluir template e tagline."""
        url = '/api/v1/public/ce-saladas/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('template', data)
        self.assertIn('tagline', data)
