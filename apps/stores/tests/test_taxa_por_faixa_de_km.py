"""A taxa de entrega é uma fórmula, não 16 linhas digitadas à mão.

Cada loja tinha 16 `StoreDeliveryZone` — faixas de 1 km de 0 a 17km+, todas com
a mesma cor, os mesmos 30 min, `fee_per_km` e `min_fee` vazios. Dezesseis
formulários para expressar três números:

    R$ 7 até 2 km  ·  +R$ 1/km até 12 km  ·  +R$ 2/km depois

Manter isso à mão é caro e erra: mudar o preço-base obriga a reeditar 16 linhas
em cada loja, e a escada de produção já tinha uma irregularidade (a faixa 3-5km
cobre 2 km enquanto todas as outras cobrem 1 km).

`calculate_dynamic_fee` já era a fonte única da matemática, mas só sabia UM
`fee_per_km` — não conseguia representar o segundo degrau, e por isso as zonas
do banco continuavam sendo necessárias. Este é o degrau que faltava.

Contrato: `delivery_far_km` e `delivery_fee_per_km_far` são OPCIONAIS. Sem eles
o comportamento é exatamente o de antes — nenhuma loja muda de preço por causa
desta mudança.
"""
from decimal import Decimal

import pytest

from apps.stores.services.delivery_quote_service import DeliveryQuoteService
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    """Loja com a escada real de produção expressa como fórmula."""
    s = make_store(name='Cê Saladas')
    s.metadata = {
        'delivery_base_fee': '7.00',
        'delivery_flat_km': '2.0',
        'delivery_fee_per_km': '1.00',
        'delivery_far_km': '12.0',
        'delivery_fee_per_km_far': '2.00',
        'delivery_max_km': '17.0',
    }
    s.save(update_fields=['metadata'])
    return s


def taxa(loja, km):
    return DeliveryQuoteService.calculate_dynamic_fee(loja, Decimal(str(km)))['fee']


@pytest.mark.django_db
class TestOSegundoDegrau:
    def test_dentro_do_raio_plano_cobra_a_base(self, loja):
        assert taxa(loja, 0.5) == 7.00
        assert taxa(loja, 2) == 7.00

    def test_entre_plano_e_longe_soma_o_primeiro_por_km(self, loja):
        # 7 + (5-2)*1
        assert taxa(loja, 5) == 10.00
        # 7 + (12-2)*1
        assert taxa(loja, 12) == 17.00

    def test_depois_do_ponto_longe_soma_o_segundo_por_km(self, loja):
        """O trecho caro NÃO recomeça do zero: ele continua de onde o barato parou.

        Cobrar `base + distância*2` a partir dos 12 km daria um salto de R$ 12
        num único metro. A conta é acumulativa por trecho.
        """
        # 7 + (12-2)*1 + (13-12)*2
        assert taxa(loja, 13) == 19.00
        # 7 + 10*1 + (17-12)*2
        assert taxa(loja, 17) == 27.00

    def test_nao_ha_salto_no_ponto_de_virada(self, loja):
        """Um metro a mais não pode custar reais a mais."""
        antes = taxa(loja, 11.99)
        depois = taxa(loja, 12.01)
        assert abs(depois - antes) < 0.10


@pytest.mark.django_db
class TestOQueNaoPodeMudar:
    def test_sem_configurar_o_degrau_o_calculo_e_o_de_antes(self, db):
        """Loja que não declara `delivery_far_km` não muda de preço.

        Esta é a garantia que permite subir a mudança sem migrar ninguém.
        """
        s = make_store(name='Pastita')
        s.metadata = {
            'delivery_base_fee': '9.00',
            'delivery_flat_km': '4.0',
            'delivery_fee_per_km': '1.00',
        }
        s.save(update_fields=['metadata'])

        assert taxa(s, 4) == 9.00
        # 9 + (10-4)*1 — linear até o fim, como antes
        assert taxa(s, 10) == 15.00

    def test_fora_do_raio_continua_indisponivel(self, loja):
        r = DeliveryQuoteService.calculate_dynamic_fee(loja, Decimal('20'))
        assert r['fee'] is None
        assert r['is_valid'] is False
        assert r['available'] is False

    def test_teto_de_taxa_limita_o_trecho_caro(self, loja):
        loja.metadata = {**loja.metadata, 'delivery_max_fee': '20.00'}
        loja.save(update_fields=['metadata'])

        # 7 + 10 + 5*2 = 27, limitado a 20
        assert taxa(loja, 17) == 20.00

    def test_sem_distancia_devolve_a_base(self, loja):
        r = DeliveryQuoteService.calculate_dynamic_fee(loja, None)
        assert r['fee'] == 7.00
        assert r['is_valid'] is True
