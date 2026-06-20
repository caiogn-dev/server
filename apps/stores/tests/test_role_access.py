"""
Testa que o acesso a lojas respeita StoreTeamMember (roles) e que is_staff
NÃO concede acesso cross-tenant (vazamento de todas as lojas).
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store, StoreTeamMember
from apps.core.permissions import accessible_store_ids, user_can_access_store

User = get_user_model()


class RoleAccessTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username='dono', password='x')
        cls.loja_a = Store.objects.create(name='Loja A', slug='loja-a', owner=cls.owner)
        cls.loja_b = Store.objects.create(name='Loja B', slug='loja-b', owner=cls.owner)

        # gerente só da Loja A via StoreTeamMember
        cls.gerente = User.objects.create_user(username='gerente', password='x')
        StoreTeamMember.objects.create(tenant=cls.loja_a, user=cls.gerente, role='manager')

        # staff do Django (acesso ao /admin) sem vínculo com loja nenhuma
        cls.staff = User.objects.create_user(username='staff', password='x', is_staff=True)

    def test_gerente_acessa_so_a_loja_dele(self):
        ids = set(accessible_store_ids(self.gerente))
        self.assertEqual(ids, {self.loja_a.id})
        self.assertTrue(user_can_access_store(self.gerente, self.loja_a))
        self.assertFalse(user_can_access_store(self.gerente, self.loja_b))

    def test_is_staff_NAO_vaza_todas_as_lojas(self):
        ids = set(accessible_store_ids(self.staff))
        self.assertEqual(ids, set(), "is_staff não pode enxergar nenhuma loja sem vínculo")
        self.assertFalse(user_can_access_store(self.staff, self.loja_a))

    def test_membro_inativo_perde_acesso(self):
        StoreTeamMember.objects.filter(user=self.gerente).update(is_active=False)
        self.assertFalse(user_can_access_store(self.gerente, self.loja_a))
        self.assertEqual(set(accessible_store_ids(self.gerente)), set())

    def test_owner_acessa_suas_lojas(self):
        ids = set(accessible_store_ids(self.owner))
        self.assertEqual(ids, {self.loja_a.id, self.loja_b.id})
