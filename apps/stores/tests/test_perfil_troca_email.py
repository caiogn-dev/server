"""PATCH do perfil do cliente LOGADO trocando nome/e-mail.

24/11: o app mandava o e-mail novo, o servidor respondia 200 e não gravava —
`resolve_user` sai cedo quando há usuário autenticado e a atualização de
e-mail/nome mora depois desse retorno. Ninguém logado conseguia trocar.
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.stores.tests.factories import make_store

User = get_user_model()


@pytest.fixture
def cliente(db):
    return User.objects.create(username='cliente_5563991386719', email='velho@exemplo.com',
                               first_name='Ana', last_name='Souza')


def _patch(loja, user, corpo):
    c = APIClient()
    c.force_authenticate(user)
    return c.patch(f'/api/v1/stores/{loja.slug}/customer/profile/', corpo, format='json')


def test_logado_troca_o_email(cliente):
    loja = make_store()
    r = _patch(loja, cliente, {'name': 'Ana Souza', 'email': 'Novo@Exemplo.com'})
    assert r.status_code == 200
    cliente.refresh_from_db()
    assert cliente.email == 'novo@exemplo.com'
    assert r.json()['contact']['email'] == 'novo@exemplo.com'


def test_logado_troca_o_nome(cliente):
    r = _patch(make_store(), cliente, {'name': 'Ana Maria Souza'})
    assert r.status_code == 200
    cliente.refresh_from_db()
    assert (cliente.first_name, cliente.last_name) == ('Ana', 'Maria Souza')


def test_email_de_outra_conta_e_recusado_com_mensagem(cliente):
    User.objects.create(username='outro', email='ocupado@exemplo.com')
    r = _patch(make_store(), cliente, {'email': 'ocupado@exemplo.com'})
    assert r.status_code == 400
    assert 'outra conta' in r.json()['error']
    cliente.refresh_from_db()
    assert cliente.email == 'velho@exemplo.com'


def test_email_invalido_e_recusado(cliente):
    r = _patch(make_store(), cliente, {'email': 'nao-e-email'})
    assert r.status_code == 400
