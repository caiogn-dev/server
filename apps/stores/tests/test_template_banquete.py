"""O template só existe de verdade quando o painel consegue ligá-lo.

O `banquete` foi desenhado no storefront e gravado no banco por script — e
passou, porque `Model.save()` não valida `choices`. Pelo painel teria sido
recusado: o serializer valida contra `StoreTemplate`, e 'banquete' não estava
lá. Ou seja, o template existia na tela e não existia no produto.

Um template novo precisa das TRÊS camadas: choices do model (o backend aceita),
lista do painel (o dono escolhe) e os arquivos do storefront (o cliente vê).
"""
import pytest

from apps.stores.api.serializers import StoreSerializer
from apps.stores.models import Store
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    return make_store(name='Ivoneth Banqueteria')


@pytest.mark.django_db
class TestOPainelConsegueLigar:
    def test_banquete_e_um_template_valido(self):
        assert Store.StoreTemplate.BANQUETE == 'banquete'
        assert 'banquete' in dict(Store.StoreTemplate.choices)

    def test_o_serializer_aceita_banquete(self, loja):
        """É este caminho que o painel usa — e era ele que recusaria."""
        s = StoreSerializer(loja, data={'template': 'banquete'}, partial=True)
        assert s.is_valid(), s.errors
        s.save()
        loja.refresh_from_db()
        assert loja.template == 'banquete'

    def test_template_inventado_continua_recusado(self, loja):
        """A validação existe por um motivo: um slug sem arquivo no storefront
        renderizaria o fallback, e o dono acharia que escolheu outra coisa."""
        s = StoreSerializer(loja, data={'template': 'nao-existe'}, partial=True)
        assert not s.is_valid()
        assert 'template' in s.errors


@pytest.mark.django_db
class TestOQueNaoPodeMudar:
    def test_os_templates_antigos_seguem_validos(self, loja):
        for slug in ['fresh', 'bold', 'classic', 'minimal', 'dark', 'elegant']:
            s = StoreSerializer(loja, data={'template': slug}, partial=True)
            assert s.is_valid(), f'{slug} deixou de ser aceito: {s.errors}'
