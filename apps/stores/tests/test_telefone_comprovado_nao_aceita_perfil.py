"""`telefone_comprovado` não pode aceitar o telefone do PERFIL como prova.

O BURACO (confirmado lendo o código em 14/set): o perfil é gravável pelo
próprio cliente, sem código nenhum —

    PATCH /api/v1/auth/profile/ {"phone": "<número da vítima>"}   (auth_views.ProfileView)
    POST  /api/v1/auth/register/ {"phone": "<número da vítima>"}  (auth_views.RegisterView)

e o checkout logado também grava `profile.phone` com o que veio no corpo
(CustomerIdentityService.sync_checkout_customer). Como `telefone_comprovado`
aceitava "logado + profile.phone batendo", qualquer um lia o saldo pré-pago,
o histórico com `access_token` (→ endereço de casa) e gastava a carteira de
quem tivesse o número fora de um perfil — a maioria dos clientes do bot e do
PDV.

O PR #364 propunha confiar só no username `cliente_<dígitos>`. Não basta: o
cadastro por e-mail deriva o username da parte local do e-mail, então
`cliente_556399998888@x.com` vira o username `cliente_556399998888` (com senha).
E trancaria fora quem faz OTP numa conta antiga que não tem esse username.

A PROVA agora é o que só o código do WhatsApp produz:
- `UserProfile.telefone_verificado`, gravado em verify_whatsapp_auth_code; ou
- (legado) username `cliente_<dígitos>` SEM senha utilizável — conta criada
  pelo próprio fluxo de OTP, que não tem outro jeito de receber token.
"""
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APIRequestFactory

from apps.core.models import UserProfile
from apps.stores.services.carteira_service import telefone_comprovado

User = get_user_model()
VITIMA = '5563991386719'


def _request(user):
    req = APIRequestFactory().get('/')
    req.user = user
    return req


def _com_perfil(user, phone):
    perfil, _ = UserProfile.objects.get_or_create(user=user)
    perfil.phone = phone
    perfil.save()
    return perfil


@pytest.mark.django_db
def test_perfil_com_o_numero_da_vitima_nao_comprova():
    atacante = User.objects.create_user(username='atacante', email='a@x.com', password='x')
    _com_perfil(atacante, VITIMA)
    assert telefone_comprovado(_request(atacante), VITIMA) is False


@pytest.mark.django_db
def test_username_cliente_com_senha_nao_comprova():
    """O cadastro por e-mail `cliente_<dígitos>@...` produz este username."""
    atacante = User.objects.create_user(username='cliente_556391386719', password='x')
    assert telefone_comprovado(_request(atacante), VITIMA) is False


@pytest.mark.django_db
def test_cadastro_por_email_nao_forja_username_de_otp():
    cliente = APIClient()
    resp = cliente.post('/api/v1/auth/register/', {
        'email': 'cliente_556391386719@evil.com', 'password': 'SenhaForte!123',
        'first_name': 'X',
    }, format='json')
    assert resp.status_code in (200, 201), resp.content
    user = User.objects.get(email='cliente_556391386719@evil.com')
    assert telefone_comprovado(_request(user), VITIMA) is False


@pytest.mark.django_db
def test_patch_do_perfil_nao_comprova():
    atacante = User.objects.create_user(username='atacante2', email='a2@x.com', password='x')
    c = APIClient()
    c.force_authenticate(user=atacante)
    resp = c.patch('/api/v1/auth/profile/', {'phone': VITIMA}, format='json')
    assert resp.status_code == 200, resp.content
    atacante.refresh_from_db()
    assert telefone_comprovado(_request(atacante), VITIMA) is False


@pytest.mark.django_db
def test_conta_criada_pelo_otp_sem_senha_comprova():
    legado = User.objects.create(username=f'cliente_{VITIMA}')
    legado.set_unusable_password()
    legado.save()
    assert telefone_comprovado(_request(legado), VITIMA) is True
    assert telefone_comprovado(_request(legado), '5563999990000') is False


@pytest.mark.django_db
def test_telefone_verificado_comprova_por_variante():
    dono = User.objects.create_user(username='conta-antiga', email='c@x.com', password='x')
    perfil = _com_perfil(dono, VITIMA)
    perfil.telefone_verificado = VITIMA
    perfil.save()
    # wa_id sem o nono dígito é o mesmo número
    assert telefone_comprovado(_request(dono), '556391386719') is True
    assert telefone_comprovado(_request(dono), '5563999990000') is False


@pytest.mark.django_db
def test_login_por_codigo_grava_o_numero_verificado():
    """Conta antiga (e-mail/senha) com o telefone no perfil faz OTP e passa a comprovar."""
    dono = User.objects.create_user(username='conta-email', email='e@x.com', password='x')
    _com_perfil(dono, VITIMA)
    assert telefone_comprovado(_request(dono), VITIMA) is False

    with mock.patch(
        'apps.core.auth.views.WhatsAppAuthService.verify_code',
        return_value={'valid': True, 'message': 'ok', 'phone_number': VITIMA, 'user': {}},
    ):
        resp = APIClient().post('/api/v1/auth/whatsapp/verify/',
                                {'phone_number': VITIMA, 'code': '123456'}, format='json')
    assert resp.status_code == 200, resp.content
    assert resp.json()['user']['id'] == dono.id

    dono.refresh_from_db()
    assert telefone_comprovado(_request(dono), VITIMA) is True


@pytest.mark.django_db
def test_anonimo_nao_comprova():
    from django.contrib.auth.models import AnonymousUser
    assert telefone_comprovado(_request(AnonymousUser()), VITIMA) is False
