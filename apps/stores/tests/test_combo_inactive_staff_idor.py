"""
P2 — IDOR: usuário is_staff sem vínculo com a loja vê combos INATIVOS de outro tenant.

CONTEXTO DO BUG
---------------
StoreComboViewSet.get_queryset() linha ~445:

    is_admin = self.request.user.is_authenticated and (
        self.request.user.is_staff or self.request.user.is_superuser
    )
    if self.action == 'list' and not is_admin:
        queryset = queryset.filter(is_active=True)

Convenção do projeto (CLAUDE.md, apps/core/permissions.py):
  is_staff abre o /admin do Django — NÃO é bypass cross-tenant.
  Só is_superuser é bypass (e ainda assim, só para fins operacionais).

VETOR
-----
1. Atacante obtém conta com is_staff=True mas sem vínculo com a Loja B.
2. GET /api/v1/stores/combos/?store=<loja-b-uuid>
   → vê combos inativos (rascunhos, produtos fora de temporada) de outra empresa.

FIX ESPERADO
------------
is_admin deve ser True apenas para is_superuser ou para quem tem acesso à loja
específica via accessible_store_ids (dono, staff M2M, StoreTeamMember).

Rodar:
  DJANGO_SETTINGS_MODULE=config.settings.test_serializer \
    python manage.py test apps.stores.tests.test_combo_inactive_staff_idor -v 2
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreCombo

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


class StaffComboInactiveIDORTest(APITestCase):
    """
    Usuário is_staff sem vínculo NÃO deve ver combos inativos de outro tenant.
    """

    def setUp(self):
        self.owner_b = _make_user('owner-b')
        self.store_b = _make_store('Loja B', 'loja-b', self.owner_b)

        self.combo_active = StoreCombo.objects.create(
            store=self.store_b,
            name='Combo ativo da Loja B',
            slug='combo-b-ativo',
            price=Decimal('30.00'),
            is_active=True,
        )
        self.combo_inactive = StoreCombo.objects.create(
            store=self.store_b,
            name='Combo INATIVO da Loja B',
            slug='combo-b-inativo',
            price=Decimal('20.00'),
            is_active=False,
        )
        self.staff_user = _make_user('staff-sem-loja', is_staff=True)

    # ------------------------------------------------------------------
    # Caso 1 (P2 BUG): is_staff sem vínculo não deve ver inativo via ?store=
    # ------------------------------------------------------------------
    def test_staff_sem_vinculo_nao_ve_combo_inativo_via_store_param(self):
        """
        is_staff sem vínculo com a loja:
        GET ?store=<uuid> NÃO deve retornar combos inativos de outro tenant.
        """
        self.client.force_authenticate(user=self.staff_user)
        url = f'/api/v1/stores/combos/?store={self.store_b.id}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        ids = [r['id'] for r in response.json().get('results', [])]
        self.assertNotIn(
            str(self.combo_inactive.id),
            ids,
            'IDOR: is_staff sem vínculo NÃO deve ver combo inativo de outro tenant',
        )
        # combo ativo pode ser visto (storefront usa AllowAny para ativos)
        self.assertIn(
            str(self.combo_active.id),
            ids,
            'Combo ativo deve continuar visível',
        )

    # ------------------------------------------------------------------
    # Caso 2: is_staff sem vínculo + ?is_active=false → lista vazia
    # ------------------------------------------------------------------
    def test_staff_sem_vinculo_nao_ve_inativo_com_is_active_false(self):
        """
        is_staff sem vínculo + ?is_active=false não deve retornar nada.
        """
        self.client.force_authenticate(user=self.staff_user)
        url = f'/api/v1/stores/combos/?store={self.store_b.id}&is_active=false'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        ids = [r['id'] for r in response.json().get('results', [])]
        self.assertNotIn(
            str(self.combo_inactive.id),
            ids,
            'IDOR: is_staff sem vínculo NÃO deve ver inativo mesmo com ?is_active=false',
        )

    # ------------------------------------------------------------------
    # Caso 3 (regressão): dono da loja DEVE ver combos inativos da própria loja
    # ------------------------------------------------------------------
    def test_dono_da_loja_ve_combo_inativo_da_propria_loja(self):
        """
        Dono da loja deve continuar vendo combos inativos da própria loja
        (nenhuma regressão no dashboard).
        """
        self.client.force_authenticate(user=self.owner_b)
        url = f'/api/v1/stores/combos/?store={self.store_b.id}&is_active=false'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        ids = [r['id'] for r in response.json().get('results', [])]
        self.assertIn(
            str(self.combo_inactive.id),
            ids,
            'Dono da loja DEVE ver combo inativo da própria loja',
        )

    # ------------------------------------------------------------------
    # Caso 4: is_superuser vê tudo (bypass intencional)
    # ------------------------------------------------------------------
    def test_superuser_ve_combos_inativos(self):
        superuser = _make_user('superuser-test', is_superuser=True)
        self.client.force_authenticate(user=superuser)
        url = f'/api/v1/stores/combos/?store={self.store_b.id}&is_active=false'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        ids = [r['id'] for r in response.json().get('results', [])]
        self.assertIn(
            str(self.combo_inactive.id),
            ids,
            'Superuser DEVE ver combos inativos de qualquer loja',
        )

    # ------------------------------------------------------------------
    # Caso 5: usuário sem autenticação vê apenas ativos
    # ------------------------------------------------------------------
    def test_anonimo_ve_apenas_ativos(self):
        url = f'/api/v1/stores/combos/?store={self.store_b.id}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        ids = [r['id'] for r in response.json().get('results', [])]
        self.assertIn(str(self.combo_active.id), ids, 'Ativo deve aparecer para anônimo')
        self.assertNotIn(
            str(self.combo_inactive.id),
            ids,
            'Inativo NÃO deve aparecer para anônimo',
        )
