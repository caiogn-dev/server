"""Regressão de integridade de dados: Store.owner era on_delete=CASCADE.

Deletar 1 User apagava a loja inteira + todo o histórico financeiro
(pedidos, pagamentos) em cascata. Um tenant não pode evaporar porque uma
conta de usuário foi removida. Fix: PROTECT — a exclusão é bloqueada até a
loja ser reatribuída/removida explicitamente.
"""
from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from django.test import TestCase

from apps.stores.models import Store

User = get_user_model()


class StoreOwnerProtectTest(TestCase):
    def test_deletar_owner_com_loja_e_bloqueado(self):
        owner = User.objects.create_user(username='prot-owner', email='p@t.com', password='x')
        store = Store.objects.create(name='Loja Protegida', slug='loja-prot', owner=owner, status='active')

        with self.assertRaises(ProtectedError):
            owner.delete()

        # A loja (e o histórico) sobrevive à tentativa de exclusão.
        self.assertTrue(Store.objects.filter(id=store.id).exists())

    def test_deletar_user_sem_loja_continua_funcionando(self):
        """Regressão: usuários que não são donos de loja seguem deletáveis."""
        u = User.objects.create_user(username='prot-nostore', email='n@t.com', password='x')
        uid = u.id
        u.delete()
        self.assertFalse(User.objects.filter(id=uid).exists())
