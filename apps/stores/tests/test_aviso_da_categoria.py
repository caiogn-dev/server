"""
Aviso da categoria (Ivoneth, 25/11): "Pedidos até dia 15/12" na Ceia de Natal.

A descrição da categoria some no celular e no tema Elegant (texto decorativo),
então prazo/urgência precisa de campo próprio, que o storefront mostra em selo
ao lado do título e dentro do produto.
"""
import pytest

from apps.core.models import User
from apps.stores.api.serializers import StoreCategorySerializer
from apps.stores.models import Store, StoreCategory

pytestmark = pytest.mark.django_db


@pytest.fixture
def categoria(db):
    dono = User.objects.create_user(username='dono-aviso', email='dono-aviso@example.com', password='x')
    loja = Store.objects.create(name='Aviso', slug='aviso', owner=dono)
    return StoreCategory.objects.create(store=loja, name='Ceia de Natal', slug='ceia')


def test_aviso_vazio_por_padrao(categoria):
    assert StoreCategorySerializer(categoria).data['aviso'] == ''


def test_aviso_sai_no_serializer(categoria):
    categoria.aviso = 'Pedidos até dia 15/12'
    categoria.save()
    assert StoreCategorySerializer(categoria).data['aviso'] == 'Pedidos até dia 15/12'


def test_painel_grava_o_aviso(categoria):
    s = StoreCategorySerializer(categoria, data={'aviso': '  Pedidos até dia 15/12  '}, partial=True)
    assert s.is_valid(), s.errors
    s.save()
    categoria.refresh_from_db()
    assert categoria.aviso == 'Pedidos até dia 15/12'


def test_aviso_curto_cabe_no_selo(categoria):
    s = StoreCategorySerializer(categoria, data={'aviso': 'x' * 81}, partial=True)
    assert not s.is_valid()
    assert 'aviso' in s.errors
