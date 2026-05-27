from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from apps.stores.models import Store

User = get_user_model()


class StoreByDomainTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(username='storefront-owner', password='x')
        self.store = Store.objects.create(
            name='Cê Saladas',
            slug='ce-saladas-test',
            custom_domain='cesaladas.com.br',
            primary_color='#2D6A4F',
            secondary_color='#1B4332',
            template='fresh',
            tagline='Saladas frescas',
            status='active',
            owner=self.owner,
        )

    def test_encontra_loja_por_dominio(self):
        response = self.client.get('/api/v1/public/store-by-domain/?domain=cesaladas.com.br')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['slug'], 'ce-saladas-test')
        self.assertEqual(data['template'], 'fresh')
        self.assertEqual(data['tagline'], 'Saladas frescas')
        self.assertEqual(data['primary_color'], '#2D6A4F')

    def test_dominio_com_porta_retorna_loja(self):
        response = self.client.get('/api/v1/public/store-by-domain/?domain=cesaladas.com.br:3000')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['slug'], 'ce-saladas-test')

    def test_dominio_inexistente_retorna_404(self):
        response = self.client.get('/api/v1/public/store-by-domain/?domain=naoexiste.com.br')
        self.assertEqual(response.status_code, 404)

    def test_sem_parametro_retorna_400(self):
        response = self.client.get('/api/v1/public/store-by-domain/')
        self.assertEqual(response.status_code, 400)

    def test_loja_inativa_retorna_404(self):
        self.store.status = 'inactive'
        self.store.save()
        response = self.client.get('/api/v1/public/store-by-domain/?domain=cesaladas.com.br')
        self.assertEqual(response.status_code, 404)

    def test_resposta_inclui_campos_storefront(self):
        response = self.client.get('/api/v1/public/store-by-domain/?domain=cesaladas.com.br')
        data = response.json()
        for field in ('slug', 'name', 'template', 'tagline', 'primary_color', 'secondary_color'):
            self.assertIn(field, data, f'Campo {field!r} ausente na resposta')

    def test_serializer_store_detail_inclui_template_e_tagline(self):
        """PublicStoreSerializer no endpoint store-detail deve expor template e tagline."""
        response = self.client.get('/api/v1/public/ce-saladas-test/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('template', data)
        self.assertIn('tagline', data)
