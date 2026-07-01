"""
Testes de isolamento multi-tenant para StoreComboViewSet e StoreProductTypeViewSet
na rota plana (sem store_slug na URL).

CONTEXTO DO BUG
---------------
GET /api/v1/stores/combos/           → StoreComboViewSet.get_queryset()
GET /api/v1/stores/product-types/    → StoreProductTypeViewSet.get_queryset()

Quando nenhum parâmetro de loja é fornecido (sem ?store= e sem store_slug no path),
ambos retornavam StoreCombo/StoreProductType.objects.all() — expondo dados de todos
os tenants a qualquer usuário autenticado. IDOR cross-tenant.

FIX ESPERADO
------------
- Usuário não autenticado → 0 resultados (ou 401, dependendo do permission_class)
- Usuário autenticado sem store_id no filtro → apenas lojas próprias (accessible_store_ids)
- Superuser → todos os registros (acesso cross-tenant intencional)
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreCombo
from apps.stores.models.product import StoreProductType

User = get_user_model()


def _make_user(username, *, is_superuser=False, is_staff=False):
    return User.objects.create_user(
        username=username,
        password='testpass123',
        is_superuser=is_superuser,
        is_staff=is_staff,
    )


def _make_store(name, slug, owner):
    return Store.objects.create(name=name, slug=slug, owner=owner, status='active')


class ComboCrossTenantIDORTest(APITestCase):
    """
    GET /api/v1/stores/combos/ sem ?store= NÃO deve retornar combos de outros tenants.
    """

    def setUp(self):
        self.user_a = _make_user('user-a')
        self.user_b = _make_user('user-b')
        self.store_a = _make_store('Store A', 'store-a', self.user_a)
        self.store_b = _make_store('Store B', 'store-b', self.user_b)

        self.combo_a = StoreCombo.objects.create(
            store=self.store_a,
            name='Combo da Loja A',
            slug='combo-a',
            price=Decimal('30.00'),
            is_active=True,
        )
        self.combo_b = StoreCombo.objects.create(
            store=self.store_b,
            name='Combo da Loja B',
            slug='combo-b',
            price=Decimal('40.00'),
            is_active=True,
        )

    # ------------------------------------------------------------------
    # Caso 1: usuário A não deve ver combo da loja B sem filtro de loja
    # ------------------------------------------------------------------
    def test_user_a_does_not_see_store_b_combos_without_filter(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get('/api/v1/stores/combos/')
        self.assertEqual(response.status_code, 200)
        ids = [r['id'] for r in response.json()['results']]
        self.assertIn(str(self.combo_a.id), ids, 'User A deve ver combo da própria loja')
        self.assertNotIn(
            str(self.combo_b.id),
            ids,
            'IDOR: User A não deve ver combo da loja B sem filtro de loja',
        )

    # ------------------------------------------------------------------
    # Caso 2: superuser pode ver todos (acesso cross-tenant intencional)
    # ------------------------------------------------------------------
    def test_superuser_sees_all_combos(self):
        superuser = _make_user('superuser', is_superuser=True)
        self.client.force_authenticate(user=superuser)
        response = self.client.get('/api/v1/stores/combos/')
        self.assertEqual(response.status_code, 200)
        ids = [r['id'] for r in response.json()['results']]
        self.assertIn(str(self.combo_a.id), ids)
        self.assertIn(str(self.combo_b.id), ids)

    # ------------------------------------------------------------------
    # Caso 3: anônimo não vê nada (sem autenticação)
    # ------------------------------------------------------------------
    def test_anonymous_sees_no_combos_on_flat_route(self):
        response = self.client.get('/api/v1/stores/combos/')
        # Pode ser 200 com 0 resultados ou 401 — o que NÃO pode é retornar dados
        if response.status_code == 200:
            self.assertEqual(
                response.json().get('results', []),
                [],
                'Anônimo não deve receber nenhum combo na rota plana',
            )

    # ------------------------------------------------------------------
    # Caso 4: filtro ?store= ainda funciona normalmente
    # ------------------------------------------------------------------
    def test_store_filter_still_works(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(f'/api/v1/stores/combos/?store={self.store_a.slug}')
        self.assertEqual(response.status_code, 200)
        ids = [r['id'] for r in response.json()['results']]
        self.assertIn(str(self.combo_a.id), ids)
        self.assertNotIn(str(self.combo_b.id), ids)


class ProductTypeCrossTenantIDORTest(APITestCase):
    """
    GET /api/v1/stores/product-types/ sem ?store= NÃO deve retornar tipos de outros tenants.
    """

    def setUp(self):
        self.user_a = _make_user('pt-user-a')
        self.user_b = _make_user('pt-user-b')
        self.store_a = _make_store('PT Store A', 'pt-store-a', self.user_a)
        self.store_b = _make_store('PT Store B', 'pt-store-b', self.user_b)

        self.ptype_a = StoreProductType.objects.create(
            store=self.store_a,
            name='Tipo A',
            is_active=True,
        )
        self.ptype_b = StoreProductType.objects.create(
            store=self.store_b,
            name='Tipo B',
            is_active=True,
        )

    # ------------------------------------------------------------------
    # Caso 1: usuário A não deve ver tipos da loja B sem filtro de loja
    # ------------------------------------------------------------------
    def test_user_a_does_not_see_store_b_product_types_without_filter(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get('/api/v1/stores/product-types/')
        self.assertEqual(response.status_code, 200)
        ids = [r['id'] for r in response.json()['results']]
        self.assertIn(str(self.ptype_a.id), ids)
        self.assertNotIn(
            str(self.ptype_b.id),
            ids,
            'IDOR: User A não deve ver tipo da loja B sem filtro de loja',
        )

    # ------------------------------------------------------------------
    # Caso 2: superuser vê tudo
    # ------------------------------------------------------------------
    def test_superuser_sees_all_product_types(self):
        superuser = _make_user('pt-superuser', is_superuser=True)
        self.client.force_authenticate(user=superuser)
        response = self.client.get('/api/v1/stores/product-types/')
        self.assertEqual(response.status_code, 200)
        ids = [r['id'] for r in response.json()['results']]
        self.assertIn(str(self.ptype_a.id), ids)
        self.assertIn(str(self.ptype_b.id), ids)

    # ------------------------------------------------------------------
    # Caso 3: filtro ?store= segue funcionando
    # ------------------------------------------------------------------
    def test_store_filter_still_works(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(
            f'/api/v1/stores/product-types/?store={self.store_a.slug}'
        )
        self.assertEqual(response.status_code, 200)
        ids = [r['id'] for r in response.json()['results']]
        self.assertIn(str(self.ptype_a.id), ids)
        self.assertNotIn(str(self.ptype_b.id), ids)
