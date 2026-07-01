"""
Testes de IDOR para o bypass de is_staff em StoreProductVariantViewSet e
StoreComboViewSet.

CONTEXTO DOS BUGS
-----------------
A convenção do projeto é: is_staff (acesso ao Django /admin) NÃO concede
acesso cross-tenant — apenas is_superuser pode ver/editar dados de todos os
tenants. Ver comentários em base.py e permissions.py.

Bug 1 — Leitura de variantes:
  StoreProductVariantViewSet.get_queryset usava `if not (user.is_staff or user.is_superuser)`
  para decidir se aplicava o filtro de tenant.  Usuários com is_staff=True
  bypassavam o filtro e enxergavam variantes de produtos de lojas alheias.

Bug 2 — Escrita de combos:
  StoreComboViewSet._assert_store_access tinha `if user.is_staff or user.is_superuser:
  return`.  Usuários com is_staff=True podiam criar/editar/deletar combos em
  qualquer loja sem ser donos ou membro da equipe dela.

FIX ESPERADO
------------
Ambos os checks devem usar apenas `is_superuser`, nunca `is_staff`.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreCombo
from apps.stores.tests.factories import make_store, make_product, make_variant

User = get_user_model()


def _staff_user(username):
    """Cria usuário com is_staff=True mas is_superuser=False."""
    return User.objects.create_user(
        username=username,
        password='testpass123',
        is_staff=True,
        is_superuser=False,
    )


class StaffVariantReadIDORTest(APITestCase):
    """
    is_staff NÃO deve ver variantes de produtos de lojas alheias.

    Rota: GET /api/v1/stores/products/{product_pk}/variants/
    """

    def setUp(self):
        self.store_b = make_store(name='Loja B', slug='loja-b-variant-idor')
        self.product_b = make_product(self.store_b, name='Produto B', slug='produto-b-variant-idor')
        self.variant_b = make_variant(self.product_b, name='Variante B')
        self.staff_user = _staff_user('staff-variant-idor')

    def _url(self):
        return f'/api/v1/stores/products/{self.product_b.pk}/variants/'

    def test_staff_cannot_read_other_store_variants(self):
        """is_staff sem acesso à loja deve receber lista vazia — não vazamento."""
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(self._url())
        self.assertIn(response.status_code, [200, 403, 404],
                      'Resposta inesperada')
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', []) if isinstance(data, dict) else data
            ids = [r['id'] for r in results]
            self.assertNotIn(
                str(self.variant_b.id),
                ids,
                'IDOR: is_staff não deve enxergar variantes de loja alheia',
            )

    def test_owner_can_read_own_variants(self):
        """Dono da loja ainda consegue ver suas variantes (regressão)."""
        self.client.force_authenticate(user=self.store_b.owner)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', []) if isinstance(data, dict) else data
        ids = [r['id'] for r in results]
        self.assertIn(
            str(self.variant_b.id),
            ids,
            'Dono deve ver variantes da própria loja',
        )

    def test_superuser_can_read_any_variants(self):
        """Superuser ainda pode ver variantes de qualquer loja (acesso intencional)."""
        su = User.objects.create_user(
            username='su-variant-idor', password='pw',
            is_staff=True, is_superuser=True,
        )
        self.client.force_authenticate(user=su)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', []) if isinstance(data, dict) else data
        ids = [r['id'] for r in results]
        self.assertIn(str(self.variant_b.id), ids)


class StaffComboWriteIDORTest(APITestCase):
    """
    is_staff NÃO deve criar/editar/deletar combos em lojas alheias.

    Rota: POST /api/v1/stores/combos/
          PATCH /api/v1/stores/combos/{pk}/
          DELETE /api/v1/stores/combos/{pk}/
    """

    def setUp(self):
        self.store_b = make_store(name='Loja B Combo', slug='loja-b-combo-idor')
        self.combo_b = StoreCombo.objects.create(
            store=self.store_b,
            name='Combo da Loja B',
            slug='combo-b-idor',
            price=Decimal('40.00'),
            is_active=True,
        )
        self.staff_user = _staff_user('staff-combo-idor')

    def _list_url(self):
        return '/api/v1/stores/combos/'

    def _detail_url(self):
        return f'/api/v1/stores/combos/{self.combo_b.pk}/'

    def test_staff_cannot_create_combo_in_other_store(self):
        """is_staff sem acesso à loja deve receber 403 ao criar combo."""
        self.client.force_authenticate(user=self.staff_user)
        payload = {
            'store': str(self.store_b.pk),
            'name': 'Combo Invasor',
            'slug': 'combo-invasor',
            'price': '25.00',
        }
        response = self.client.post(self._list_url(), payload, format='json')
        self.assertEqual(
            response.status_code, 403,
            f'is_staff deve receber 403 ao criar combo em loja alheia, '
            f'recebeu {response.status_code}: {response.content[:200]}',
        )

    def test_staff_cannot_update_combo_of_other_store(self):
        """is_staff sem acesso à loja deve receber 403 ou 404 ao editar combo.
        404 é aceitável: o queryset scoped já bloqueia antes de _assert_store_access."""
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.patch(
            self._detail_url(),
            {'name': 'Nome Alterado'},
            format='json',
        )
        self.assertIn(
            response.status_code, [403, 404],
            f'is_staff deve receber 403/404 ao editar combo de loja alheia, '
            f'recebeu {response.status_code}: {response.content[:200]}',
        )

    def test_staff_cannot_delete_combo_of_other_store(self):
        """is_staff sem acesso à loja deve receber 403 ou 404 ao deletar combo.
        404 é aceitável: o queryset scoped já bloqueia antes de _assert_store_access."""
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.delete(self._detail_url())
        self.assertIn(
            response.status_code, [403, 404],
            f'is_staff deve receber 403/404 ao deletar combo de loja alheia, '
            f'recebeu {response.status_code}: {response.content[:200]}',
        )

    def test_owner_can_create_combo_in_own_store(self):
        """Dono da loja ainda consegue criar combo (regressão)."""
        self.client.force_authenticate(user=self.store_b.owner)
        payload = {
            'store': str(self.store_b.pk),
            'name': 'Combo do Dono',
            'slug': 'combo-do-dono-idor',
            'price': '30.00',
        }
        response = self.client.post(self._list_url(), payload, format='json')
        self.assertIn(response.status_code, [200, 201],
                      f'Dono deve conseguir criar combo, recebeu {response.status_code}')

    def test_superuser_can_create_combo_anywhere(self):
        """Superuser ainda pode criar combo em qualquer loja (acesso intencional)."""
        su = User.objects.create_user(
            username='su-combo-idor', password='pw',
            is_staff=True, is_superuser=True,
        )
        self.client.force_authenticate(user=su)
        payload = {
            'store': str(self.store_b.pk),
            'name': 'Combo Superuser',
            'slug': 'combo-superuser-idor',
            'price': '50.00',
        }
        response = self.client.post(self._list_url(), payload, format='json')
        self.assertIn(response.status_code, [200, 201],
                      f'Superuser deve conseguir criar combo, recebeu {response.status_code}')
