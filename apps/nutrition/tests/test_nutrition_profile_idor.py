"""IDOR de escrita no perfil nutricional (PR #332).

`ProductNutritionProfileSerializer` aceitava qualquer `product`: o get_queryset
só filtra LEITURA, então um autenticado criava/regravava o perfil nutricional
(alergênicos, tabela ANVISA) de produto de outra loja — e é esse perfil que sai
na etiqueta do lojista.

A régua é a mesma do resto do sistema: `user_can_access_store` (dono, staff M2M
ou StoreTeamMember ativo); só superuser atravessa tenant.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.test import APIRequestFactory

from apps.nutrition.api.serializers import ProductNutritionProfileSerializer
from apps.stores.models import Store, StoreProduct

User = get_user_model()


def _validar(user, product):
    req = APIRequestFactory().post('/')
    req.user = user
    return ProductNutritionProfileSerializer(context={'request': req}).validate_product(product)


@pytest.fixture
def cenario(db):
    dono = User.objects.create_user(username='dono-nut', email='dn@t.local', password='x')
    loja = Store.objects.create(owner=dono, name='Loja Nut', slug='loja-nut', status='active')
    produto = StoreProduct.objects.create(store=loja, name='Salada', price=Decimal('20'))
    return dono, loja, produto


def test_dono_passa(cenario):
    dono, _, produto = cenario
    assert _validar(dono, produto) == produto


def test_membro_da_equipe_passa(cenario):
    from apps.stores.models import StoreTeamMember
    _, loja, produto = cenario
    gerente = User.objects.create_user(username='gerente-nut', password='x')
    StoreTeamMember.objects.create(tenant=loja, user=gerente, role='manager', is_active=True)
    assert _validar(gerente, produto) == produto


def test_superuser_sem_vinculo_e_barrado(cenario):
    """16/set: superuser deixou de ser chave-mestra. Acesso vem de vínculo."""
    _, _, produto = cenario
    admin = User.objects.create_superuser(username='su-nut', email='su@t.local', password='x')
    with pytest.raises(serializers.ValidationError):
        _validar(admin, produto)


def test_usuario_de_outra_loja_e_barrado_sem_revelar_o_produto(cenario):
    _, _, produto = cenario
    outro = User.objects.create_user(username='outro-nut', password='x')
    Store.objects.create(owner=outro, name='Outra', slug='outra-nut', status='active')
    with pytest.raises(serializers.ValidationError) as exc:
        _validar(outro, produto)
    assert 'Salada' not in str(exc.value)
    assert str(produto.id) not in str(exc.value)


def test_is_staff_nao_atravessa_tenant(cenario):
    _, _, produto = cenario
    staff = User.objects.create_user(username='staff-nut', password='x', is_staff=True)
    with pytest.raises(serializers.ValidationError):
        _validar(staff, produto)
