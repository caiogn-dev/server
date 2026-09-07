"""Regressão de segurança: is_staff bypassa filtro de inativos em StoreComboViewSet.

`get_queryset` usava `is_staff or is_superuser` para decidir se exibia combos
inativos na listagem. `is_staff` dá acesso ao /admin do Django, NÃO à gestão
de lojas dos tenants (invariante: só `is_superuser` tem acesso cross-tenant).

Além disso, proprietários de loja autenticados (não is_staff, não is_superuser)
não conseguiam ver os próprios combos inativos no painel — o filtro os bloqueava.

Cenários:
  1. is_staff sem vínculo com a loja não enxerga combos inativos alheios.
  2. Usuário autenticado dono da loja PODE ver seus combos inativos.
  3. Usuário anônimo nunca vê combos inativos.
  4. Superuser enxerga combos inativos de qualquer loja.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreCombo

User = get_user_model()

COMBOS_URL = '/api/v1/stores/combos/'


class ComboInactiveIsStaffBypassTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='ci-owner', email='ci-owner@t.com', password='x')
        self.store = Store.objects.create(
            name='Loja Teste', slug='ci-loja', owner=self.owner, status='active')
        self.combo_active = StoreCombo.objects.create(
            store=self.store, name='Combo Ativo', slug='ci-ativo',
            price=Decimal('25.00'), is_active=True)
        self.combo_inactive = StoreCombo.objects.create(
            store=self.store, name='Combo Inativo', slug='ci-inativo',
            price=Decimal('15.00'), is_active=False)

        # is_staff (acesso /admin) SEM vínculo com a loja.
        self.staff = User.objects.create_user(
            username='ci-staff', email='ci-staff@t.com', password='x', is_staff=True)
        self.superuser = User.objects.create_superuser(
            username='ci-super', email='ci-super@t.com', password='x')

    def _combo_names_in_response(self, resp):
        data = resp.data
        items = data.get('results', data) if isinstance(data, dict) else data
        return [c['name'] for c in items]

    def test_isstaff_sem_acesso_nao_ve_combo_inativo(self):
        """is_staff sem vínculo com a loja não deve enxergar combos inativos."""
        self.client.force_authenticate(self.staff)
        resp = self.client.get(COMBOS_URL, {'store': str(self.store.id)})
        self.assertEqual(resp.status_code, 200, resp.content)
        names = self._combo_names_in_response(resp)
        self.assertNotIn('Combo Inativo', names, names)

    def test_owner_autenticado_ve_combo_inativo_da_propria_loja(self):
        """Dono autenticado deve ver combos inativos para gestão no painel."""
        self.client.force_authenticate(self.owner)
        resp = self.client.get(COMBOS_URL, {'store': str(self.store.id)})
        self.assertEqual(resp.status_code, 200, resp.content)
        names = self._combo_names_in_response(resp)
        self.assertIn('Combo Inativo', names, names)

    def test_anonimo_nao_ve_combo_inativo(self):
        """Usuário anônimo nunca enxerga combos inativos."""
        resp = self.client.get(COMBOS_URL, {'store': str(self.store.id)})
        self.assertEqual(resp.status_code, 200, resp.content)
        names = self._combo_names_in_response(resp)
        self.assertNotIn('Combo Inativo', names, names)
        self.assertIn('Combo Ativo', names, names)

    def test_superuser_ve_combo_inativo(self):
        """Superuser deve enxergar combos inativos de qualquer loja."""
        self.client.force_authenticate(self.superuser)
        resp = self.client.get(COMBOS_URL, {'store': str(self.store.id)})
        self.assertEqual(resp.status_code, 200, resp.content)
        names = self._combo_names_in_response(resp)
        self.assertIn('Combo Inativo', names, names)
