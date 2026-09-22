"""A trava de loja alheia mora num lugar só.

Havia 11 cópias de `validate_store` em 4 apps — e elas já tinham DIVERGIDO:
- stores e automation só checavam quando o usuário estava autenticado (anônimo
  passava reto);
- marketing checava sempre;
- nutrition tinha regra própria para ingrediente global.
Cópia de trava de segurança não envelhece junto: uma some, outra afrouxa, e
ninguém percebe até vazar loja de cliente.
"""
import pathlib
import re

import pytest
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from apps.core.serializers import LojaDoUsuarioMixin, checar_loja_do_usuario
from apps.stores.tests.factories import make_store


class _Pedido:
    def __init__(self, user):
        self.user = user


@pytest.fixture
def cenario(db):
    vizinho = get_user_model().objects.create_user(username='vizinho-trava', password='x')
    loja = make_store()
    return loja.owner, vizinho, loja


def test_dono_passa(cenario):
    dono, _, loja = cenario

    assert checar_loja_do_usuario(_Pedido(dono), loja) is loja


def test_loja_de_outro_responde_nao_encontrada(cenario):
    _, vizinho, loja = cenario

    with pytest.raises(ValidationError) as erro:
        checar_loja_do_usuario(_Pedido(vizinho), loja)

    assert 'não encontrada' in str(erro.value)


def test_anonimo_nao_passa(cenario):
    from django.contrib.auth.models import AnonymousUser

    _, _, loja = cenario

    with pytest.raises(ValidationError):
        checar_loja_do_usuario(_Pedido(AnonymousUser()), loja)


def test_sem_request_no_contexto_deixa_passar(cenario):
    """Uso interno (shell, tarefa, teste) não tem request — e não é IDOR."""
    _, _, loja = cenario

    assert checar_loja_do_usuario(None, loja) is loja


def test_mixin_usa_a_mesma_trava(cenario):
    dono, vizinho, loja = cenario

    class _Serializer(LojaDoUsuarioMixin, serializers.Serializer):
        pass

    s = _Serializer(context={'request': _Pedido(vizinho)})
    with pytest.raises(ValidationError):
        s.validate_store(loja)

    s_dono = _Serializer(context={'request': _Pedido(dono)})
    assert s_dono.validate_store(loja) is loja


def test_ninguem_reescreve_a_trava_a_mao():
    """Guarda estática: `validate_store` novo deve usar a trava comum."""
    copias = []
    for arquivo in pathlib.Path('apps').rglob('api/serializers.py'):
        fonte = arquivo.read_text()
        for trecho in re.findall(r'def validate_store\(self[^)]*\):(.{0,400})', fonte, re.S):
            if 'user_can_access_store' in trecho:
                copias.append(str(arquivo))

    assert copias == [], f'trava copiada à mão em: {sorted(set(copias))}'
