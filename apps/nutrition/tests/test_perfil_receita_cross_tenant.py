"""Perfil nutricional não pode apontar para a receita de outra loja.

`ProductNutritionProfileSerializer` expõe `recipe` (FK gravável, queryset
global). Sem checagem, o dono da loja A ligava o seu perfil à receita da loja B
e lia, em `calculation`, `custo` e `ingredientes_declaracao`, a ficha do vizinho.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory

from apps.nutrition.api.serializers import ProductNutritionProfileSerializer
from apps.nutrition.models import ProductRecipe
from apps.stores.models import Store, StoreProduct

User = get_user_model()


def _loja(nome):
    dono = User.objects.create_user(username=f'dono-{nome}', password='x')
    loja = Store.objects.create(owner=dono, name=nome, slug=nome, status='active')
    produto = StoreProduct.objects.create(store=loja, name=f'Prato {nome}', price=Decimal('20'))
    return dono, produto


def _serializer(user, dados):
    req = APIRequestFactory().post('/')
    req.user = user
    return ProductNutritionProfileSerializer(data=dados, context={'request': req})


@pytest.mark.django_db
def test_recusa_receita_de_outra_loja():
    dono_a, produto_a = _loja('loja-a-rec')
    _, produto_b = _loja('loja-b-rec')
    receita_b = ProductRecipe.objects.create(product=produto_b)
    s = _serializer(dono_a, {'product': produto_a.pk, 'recipe': receita_b.pk, 'serving_size_g': '100'})
    assert not s.is_valid()
    assert 'recipe' in s.errors


@pytest.mark.django_db
def test_aceita_receita_da_propria_loja():
    dono_a, produto_a = _loja('loja-a-ok')
    receita_a = ProductRecipe.objects.create(product=produto_a)
    s = _serializer(dono_a, {'product': produto_a.pk, 'recipe': receita_a.pk, 'serving_size_g': '100'})
    s.is_valid()
    assert 'recipe' not in s.errors
