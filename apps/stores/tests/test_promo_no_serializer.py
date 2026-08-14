"""A promoção semanal precisa poder ser CADASTRADA.

`promo_price`/`promo_weekday` existiam no model e no cálculo de preço desde
14/ago, mas não estavam no serializer — ou seja, o recurso funcionava e ninguém
tinha como ligá-lo. Mesmo padrão do classificador que nunca foi injetado e do
agente que ficou `inactive`: pronto, desligado, silencioso.

O caso do dono: "30,75 é o preço da quarta... e tem outras, é um dia da semana
para cada salada".
"""
from decimal import Decimal

import pytest

from apps.stores.api.serializers import StoreProductSerializer
from apps.stores.models import StoreProduct
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    return make_store(name='Cê Saladas')


@pytest.fixture
def almondega(loja):
    return StoreProduct.objects.create(
        store=loja, name='Almôndega Premium', slug='almondega-premium',
        price=Decimal('44.90'), is_active=True, status='active',
    )


@pytest.mark.django_db
class TestCadastro:
    def test_os_campos_aparecem_na_leitura(self, almondega):
        dados = StoreProductSerializer(almondega).data

        assert 'promo_price' in dados
        assert 'promo_weekday' in dados

    def test_da_para_gravar_a_promocao(self, almondega):
        s = StoreProductSerializer(
            almondega, data={'promo_price': '30.75', 'promo_weekday': 2}, partial=True,
        )

        assert s.is_valid(), s.errors
        s.save()
        almondega.refresh_from_db()
        assert almondega.promo_price == Decimal('30.75')
        assert almondega.promo_weekday == 2

    def test_da_para_TIRAR_a_promocao(self, almondega):
        """Sem isso a promoção entra e não sai — e o preço fica errado pra sempre."""
        almondega.promo_price = Decimal('30.75')
        almondega.promo_weekday = 2
        almondega.save()

        s = StoreProductSerializer(
            almondega, data={'promo_price': None, 'promo_weekday': None}, partial=True,
        )
        assert s.is_valid(), s.errors
        s.save()

        almondega.refresh_from_db()
        assert almondega.preco_vigente() == Decimal('44.90')

    def test_dia_invalido_e_recusado(self, almondega):
        """Dia 9 da semana não existe; aceitar deixaria a promo morta e calada."""
        s = StoreProductSerializer(almondega, data={'promo_weekday': 9}, partial=True)

        assert not s.is_valid()
