"""Garante que PATCH /auth/profile/ não concede acesso ao saldo de outra pessoa.

ATAQUE REPRODUZÍVEL (sem OTP):

    1. Criar conta normal (email/senha)
    2. PATCH /api/v1/auth/profile/   {"phone": "55NÚMERO_DA_VÍTIMA"}
    3. GET  /api/v1/stores/{slug}/cashback/saldo/?phone=55NÚMERO_DA_VÍTIMA
    → sem o fix, retorna saldo da vítima (IDOR financeiro)

A única fonte confiável de posse do número é o username `cliente_<dígitos>`
gravado pelo fluxo de OTP do WhatsApp. `profile.phone` pode ser escrito por
qualquer usuário autenticado sem verificação e NÃO deve ser usada.
"""
from unittest.mock import MagicMock

import pytest

from apps.stores.services.carteira_service import telefone_comprovado

TELEFONE_VITIMA = '5563991386719'


def _request(username='usuario_normal', profile_phone='', authenticated=True):
    """Monta um request fake sem tocar no banco."""
    user = MagicMock()
    user.is_authenticated = authenticated
    user.username = username

    perfil = MagicMock()
    perfil.phone = profile_phone
    user.profile = perfil

    req = MagicMock()
    req.user = user
    return req


# ── vetor de ataque ──────────────────────────────────────────────────────────

def test_usuario_com_profile_phone_alterado_nao_e_comprovado():
    """Usuário sem OTP que escreveu o número da vítima no perfil não é comprovado."""
    req = _request(username='invasor@email.com', profile_phone=TELEFONE_VITIMA)
    assert telefone_comprovado(req, TELEFONE_VITIMA) is False


def test_username_cliente_invalido_com_profile_phone_nao_e_comprovado():
    """Username inválido + profile.phone = número da vítima → ainda não comprovado."""
    req = _request(username='cliente_abc', profile_phone=TELEFONE_VITIMA)
    assert telefone_comprovado(req, TELEFONE_VITIMA) is False


# ── caminho legítimo ─────────────────────────────────────────────────────────

def test_usuario_otp_sem_profile_phone_e_comprovado():
    """Usuário criado pelo OTP (username=cliente_<dígitos>) é comprovado mesmo sem profile.phone."""
    req = _request(username=f'cliente_{TELEFONE_VITIMA}', profile_phone='')
    assert telefone_comprovado(req, TELEFONE_VITIMA) is True


def test_usuario_otp_com_profile_phone_diferente_e_comprovado_pelo_username():
    """profile.phone desatualizado não impede acesso; o username é o que vale."""
    req = _request(username=f'cliente_{TELEFONE_VITIMA}', profile_phone='5511900000000')
    assert telefone_comprovado(req, TELEFONE_VITIMA) is True


def test_usuario_otp_nao_acessa_numero_diferente():
    """OTP para número A não concede acesso ao número B."""
    req = _request(username='cliente_5563911111111', profile_phone='')
    assert telefone_comprovado(req, TELEFONE_VITIMA) is False


# ── anônimo ──────────────────────────────────────────────────────────────────

def test_anonimo_nunca_comprovado():
    req = _request(authenticated=False)
    assert telefone_comprovado(req, TELEFONE_VITIMA) is False
