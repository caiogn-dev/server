"""Login pelo celular no painel (03/10/2026).

O dono não conseguia entrar com o número: a busca por telefone do login usava
a resolução de CLIENTE, que exclui is_staff/is_superuser de propósito. Conta
de dono/administrador nunca era achada pelo celular.
"""
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import UserProfile


class LoginPorCelularTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _conta(self, username, telefone, **extra):
        u = User.objects.create_user(username, f'{username}@x.com', 'senha-forte-123', **extra)
        perfil, _ = UserProfile.objects.get_or_create(user=u)
        perfil.phone = telefone
        perfil.save()
        return u

    def _login(self, identificador, senha='senha-forte-123'):
        return self.client.post('/api/v1/auth/login/', {'email': identificador, 'password': senha}, format='json')

    def test_dono_superusuario_entra_pelo_celular(self):
        self._conta('dono', '5563999990001', is_superuser=True, is_staff=True)
        r = self._login('(63) 99999-0001')
        self.assertEqual(r.status_code, 200, r.data)

    def test_cliente_continua_entrando_pelo_celular(self):
        self._conta('cliente', '5563999990002')
        self.assertEqual(self._login('63999990002').status_code, 200)

    def test_senha_errada_continua_401(self):
        self._conta('dono2', '5563999990003', is_superuser=True)
        self.assertEqual(self._login('63999990003', 'errada').status_code, 401)


class CelularDoPerfilTest(TestCase):
    def test_celular_salvo_no_perfil_entra_no_login(self):
        u = User.objects.create_user('dono3', 'dono3@x.com', 'senha-forte-123', is_superuser=True, is_staff=True)
        c = APIClient()
        c.force_authenticate(u)
        r = c.patch('/api/v1/users/profile/', {'phone': '(63) 98888-7777'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        r = APIClient().post('/api/v1/auth/login/', {'email': '63 98888-7777', 'password': 'senha-forte-123'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
