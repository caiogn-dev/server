"""
P2 — IDOR: usuário is_staff sem vínculo com a loja vê ProductTypes INATIVOS de outro tenant.

CONTEXTO DO BUG
---------------
StoreProductTypeViewSet.get_queryset() linha ~522:

    if self.action == 'list' and not self.request.user.is_staff:
        queryset = queryset.filter(is_active=True)

Convenção do projeto (CLAUDE.md, apps/core/permissions.py):
  is_staff abre o /admin do Django — NÃO é bypass cross-tenant.
  Só is_superuser é bypass global (e mesmo assim, apenas intencional/operacional).

VETOR
-----
1. Atacante obtém conta com is_staff=True mas sem vínculo com a Loja B.
2. GET /api/v1/stores/product-types/?store=<loja-b-uuid>
   → vê product types inativos (rascunhos de cardápio) de outra empresa.

FIX ESPERADO
------------
is_admin deve ser True apenas para is_superuser ou para quem tem vínculo real
com a loja via accessible_store_ids (dono, staff M2M, StoreTeamMember).
Mesmo padrão do fix de StoreComboViewSet (PR #380, 2026-09-28).

Rodar:
  DJANGO_SETTINGS_MODULE=config.settings.test_serializer \
    python manage.py test apps.stores.tests.test_producttype_inactive_staff_idor -v 2
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreProductType

User = get_user_model()


def _make_user(username, *, is_staff=False, is_superuser=False):
    return User.objects.create_user(
        username=username,
        password='testpass',
        is_staff=is_staff,
        is_superuser=is_superuser,
    )


def _make_store(name, slug, owner):
    return Store.objects.create(name=name, slug=slug, owner=owner, status='active')


class StaffProductTypeInactiveIDORTest(APITestCase):
    """
    Usuário is_staff sem vínculo NÃO deve ver ProductTypes inativos de outro tenant.
    """

    def setUp(self):
        self.owner_b = _make_user('pt-owner-b')
        self.store_b = _make_store('Loja PT-B', 'loja-pt-b', self.owner_b)

        self.pt_active = StoreProductType.objects.create(
            store=self.store_b,
            name='Tipo Ativo da Loja B',
            slug='tipo-ativo-b',
            is_active=True,
        )
        self.pt_inactive = StoreProductType.objects.create(
            store=self.store_b,
            name='Tipo INATIVO da Loja B',
            slug='tipo-inativo-b',
            is_active=False,
        )
        self.staff_user = _make_user('pt-staff-sem-loja', is_staff=True)

    # ------------------------------------------------------------------
    # Caso 1 (P2 BUG): is_staff sem vínculo NÃO vê inativo via ?store=<uuid>
    # ------------------------------------------------------------------
    def test_staff_sem_vinculo_nao_ve_pt_inativo_via_store_param(self):
        """
        is_staff sem vínculo com a loja:
        GET ?store=<uuid> NÃO deve retornar product types inativos de outro tenant.
        """
        self.client.force_authenticate(user=self.staff_user)
        url = f'/api/v1/stores/product-types/?store={self.store_b.id}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        items = data.get('results', data) if isinstance(data, dict) else data
        ids = [str(r['id']) for r in items]
        self.assertNotIn(
            str(self.pt_inactive.id),
            ids,
            'IDOR: is_staff sem vínculo NÃO deve ver product type inativo de outro tenant',
        )
        self.assertIn(
            str(self.pt_active.id),
            ids,
            'Product type ativo deve continuar visível',
        )

    # ------------------------------------------------------------------
    # Caso 2: is_staff sem vínculo + ?is_active=false → lista vazia
    # ------------------------------------------------------------------
    def test_staff_sem_vinculo_nao_ve_inativo_com_is_active_false(self):
        """
        is_staff sem vínculo + ?is_active=false não deve retornar nada.
        """
        self.client.force_authenticate(user=self.staff_user)
        url = f'/api/v1/stores/product-types/?store={self.store_b.id}&is_active=false'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        items = data.get('results', data) if isinstance(data, dict) else data
        ids = [str(r['id']) for r in items]
        self.assertNotIn(
            str(self.pt_inactive.id),
            ids,
            'IDOR: is_staff sem vínculo NÃO deve ver inativo mesmo com ?is_active=false',
        )

    # ------------------------------------------------------------------
    # Caso 3 (regressão): dono da loja DEVE ver product types inativos da própria loja
    # ------------------------------------------------------------------
    def test_dono_da_loja_ve_pt_inativo_da_propria_loja(self):
        """
        Dono da loja deve continuar vendo product types inativos da própria loja.
        """
        self.client.force_authenticate(user=self.owner_b)
        url = f'/api/v1/stores/product-types/?store={self.store_b.id}&is_active=false'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        items = data.get('results', data) if isinstance(data, dict) else data
        ids = [str(r['id']) for r in items]
        self.assertIn(
            str(self.pt_inactive.id),
            ids,
            'Dono da loja DEVE ver product type inativo da própria loja',
        )

    # ------------------------------------------------------------------
    # Caso 4: is_superuser vê tudo (bypass intencional)
    # ------------------------------------------------------------------
    def test_superuser_ve_pts_inativos(self):
        superuser = _make_user('pt-superuser', is_superuser=True)
        self.client.force_authenticate(user=superuser)
        url = f'/api/v1/stores/product-types/?store={self.store_b.id}&is_active=false'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        items = data.get('results', data) if isinstance(data, dict) else data
        ids = [str(r['id']) for r in items]
        self.assertIn(
            str(self.pt_inactive.id),
            ids,
            'Superuser DEVE ver product types inativos de qualquer loja',
        )

    # ------------------------------------------------------------------
    # Caso 5: anônimo vê apenas ativos
    # ------------------------------------------------------------------
    def test_anonimo_ve_apenas_ativos(self):
        url = f'/api/v1/stores/product-types/?store={self.store_b.id}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        items = data.get('results', data) if isinstance(data, dict) else data
        ids = [str(r['id']) for r in items]
        self.assertIn(str(self.pt_active.id), ids, 'Ativo deve aparecer para anônimo')
        self.assertNotIn(
            str(self.pt_inactive.id),
            ids,
            'Inativo NÃO deve aparecer para anônimo',
        )
