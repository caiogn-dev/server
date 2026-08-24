"""Frete grátis por raio, com pedido mínimo.

A promoção mora no metadata da loja e é aplicada DEPOIS que a taxa foi
calculada, para não duplicar a matemática de `calculate_dynamic_fee`.

O ponto delicado é o pedido mínimo: quem monta o cardápio não conhece o
carrinho. Se a vitrine zerasse o frete sem saber o subtotal, o cliente veria
"Frete grátis" e levaria um susto no checkout. Por isso, sem subtotal a
cotação só ANUNCIA a promoção; quem zera é quem conhece o valor do pedido.
"""
from decimal import Decimal

from django.test import SimpleTestCase
from django.utils import timezone

from apps.stores.services.frete_promocional import (
    aplicar_frete_gratis,
    promocao_de_frete,
)


class LojaFalsa:
    def __init__(self, metadata):
        self.metadata = metadata


def _promo(**overrides):
    base = {'ativo': True, 'ate_km': 4, 'pedido_minimo': 60}
    base.update(overrides)
    return LojaFalsa({'frete_gratis': base})


def _cotacao(fee=9.0, distancia=3.0):
    return {
        'fee': fee,
        'delivery_fee': fee,
        'is_valid': True,
        'available': True,
        'distance_km': distancia,
        'zone_name': 'Próximo',
    }


class PromocaoDeFreteTests(SimpleTestCase):
    def test_loja_sem_metadata_nao_tem_promocao(self):
        self.assertIsNone(promocao_de_frete(LojaFalsa(None)))

    def test_promocao_desligada_nao_vale(self):
        self.assertIsNone(promocao_de_frete(_promo(ativo=False)))

    def test_promocao_sem_raio_nao_vale(self):
        self.assertIsNone(promocao_de_frete(_promo(ate_km=0)))

    def test_promocao_ligada_devolve_raio_e_minimo(self):
        promo = promocao_de_frete(_promo())
        self.assertEqual(promo['ate_km'], Decimal('4'))
        self.assertEqual(promo['pedido_minimo'], Decimal('60'))

    def test_promocao_agendada_para_o_futuro_ainda_nao_vale(self):
        amanha = (timezone.now() + timezone.timedelta(days=1)).isoformat()
        self.assertIsNone(promocao_de_frete(_promo(inicio=amanha)))

    def test_promocao_expirada_nao_vale(self):
        ontem = (timezone.now() - timezone.timedelta(days=1)).isoformat()
        self.assertIsNone(promocao_de_frete(_promo(fim=ontem)))

    def test_promocao_dentro_da_janela_vale(self):
        ontem = (timezone.now() - timezone.timedelta(days=1)).isoformat()
        amanha = (timezone.now() + timezone.timedelta(days=1)).isoformat()
        self.assertIsNotNone(promocao_de_frete(_promo(inicio=ontem, fim=amanha)))

    def test_data_invalida_nao_derruba_a_cotacao(self):
        # metadata é digitado por humano; data torta não pode quebrar o frete
        self.assertIsNotNone(promocao_de_frete(_promo(inicio='ontem de manhã')))


class AplicarFreteGratisTests(SimpleTestCase):
    def test_sem_promocao_a_cotacao_passa_intacta(self):
        cotacao = _cotacao()
        saida = aplicar_frete_gratis(cotacao, LojaFalsa({}), subtotal=Decimal('100'))
        self.assertEqual(saida['fee'], 9.0)
        self.assertNotIn('frete_gratis', saida)

    def test_dentro_do_raio_com_pedido_minimo_zera_o_frete(self):
        saida = aplicar_frete_gratis(_cotacao(), _promo(), subtotal=Decimal('60'))
        self.assertEqual(saida['fee'], 0.0)
        self.assertEqual(saida['delivery_fee'], 0.0)

    def test_frete_original_fica_registrado_para_o_recibo(self):
        saida = aplicar_frete_gratis(_cotacao(fee=12.0), _promo(), subtotal=Decimal('80'))
        self.assertEqual(saida['frete_gratis']['frete_original'], 12.0)

    def test_fora_do_raio_nao_zera(self):
        saida = aplicar_frete_gratis(_cotacao(distancia=6.0), _promo(), subtotal=Decimal('90'))
        self.assertEqual(saida['fee'], 9.0)
        self.assertFalse(saida['frete_gratis']['aplicado'])

    def test_pedido_abaixo_do_minimo_nao_zera(self):
        saida = aplicar_frete_gratis(_cotacao(), _promo(), subtotal=Decimal('45'))
        self.assertEqual(saida['fee'], 9.0)
        self.assertFalse(saida['frete_gratis']['aplicado'])

    def test_pedido_abaixo_do_minimo_diz_quanto_falta(self):
        saida = aplicar_frete_gratis(_cotacao(), _promo(), subtotal=Decimal('45'))
        self.assertEqual(saida['frete_gratis']['faltam'], 15.0)

    def test_sem_subtotal_anuncia_mas_nao_zera(self):
        # o cardápio não conhece o carrinho: prometer aqui seria mentir no checkout
        saida = aplicar_frete_gratis(_cotacao(), _promo(), subtotal=None)
        self.assertEqual(saida['fee'], 9.0)
        self.assertFalse(saida['frete_gratis']['aplicado'])
        self.assertEqual(saida['frete_gratis']['pedido_minimo'], 60.0)

    def test_sem_pedido_minimo_zera_direto(self):
        saida = aplicar_frete_gratis(_cotacao(), _promo(pedido_minimo=0), subtotal=None)
        self.assertEqual(saida['fee'], 0.0)

    def test_cotacao_indisponivel_nao_vira_frete_gratis(self):
        fora = {'fee': None, 'delivery_fee': None, 'available': False, 'distance_km': 20.0}
        saida = aplicar_frete_gratis(fora, _promo(ate_km=30), subtotal=Decimal('200'))
        self.assertIsNone(saida['fee'])

    def test_sem_distancia_conhecida_nao_zera(self):
        # taxa base sem endereço: não dá para afirmar que está dentro do raio
        saida = aplicar_frete_gratis(_cotacao(distancia=None), _promo(), subtotal=Decimal('90'))
        self.assertEqual(saida['fee'], 9.0)

    def test_frete_ja_zerado_nao_e_anunciado_como_promocao(self):
        saida = aplicar_frete_gratis(_cotacao(fee=0.0), _promo(), subtotal=Decimal('90'))
        self.assertFalse(saida['frete_gratis']['aplicado'])

    def test_limite_do_raio_e_inclusivo(self):
        saida = aplicar_frete_gratis(_cotacao(distancia=4.0), _promo(), subtotal=Decimal('90'))
        self.assertEqual(saida['fee'], 0.0)


class CotacaoComPromocaoTests(SimpleTestCase):
    """A promoção tem que sair pela fonte única, não por um cálculo paralelo."""

    def _loja(self, **promo):
        from apps.stores.models import Store
        base = {'ativo': True, 'ate_km': 4, 'pedido_minimo': 60}
        base.update(promo)
        return Store(
            name='Cê Saladas',
            slug='ce-saladas',
            default_delivery_fee=Decimal('9.00'),
            metadata={'frete_gratis': base},
        )

    def test_cotacao_dinamica_zera_dentro_do_raio_com_minimo_atingido(self):
        from apps.stores.services.delivery_quote_service import DeliveryQuoteService

        cotacao = DeliveryQuoteService.calculate_dynamic_fee(
            self._loja(), distance_km=Decimal('3'), subtotal=Decimal('70')
        )
        self.assertEqual(cotacao['fee'], 0.0)
        self.assertTrue(cotacao['frete_gratis']['aplicado'])

    def test_cotacao_sem_subtotal_nao_promete_frete_gratis(self):
        from apps.stores.services.delivery_quote_service import DeliveryQuoteService

        cotacao = DeliveryQuoteService.calculate_dynamic_fee(
            self._loja(), distance_km=Decimal('3')
        )
        self.assertEqual(cotacao['fee'], 9.0)
        self.assertFalse(cotacao['frete_gratis']['aplicado'])

    def test_cotacao_acima_do_raio_mantem_a_taxa_por_km(self):
        from apps.stores.services.delivery_quote_service import DeliveryQuoteService

        cotacao = DeliveryQuoteService.calculate_dynamic_fee(
            self._loja(), distance_km=Decimal('6'), subtotal=Decimal('200')
        )
        self.assertEqual(cotacao['fee'], 11.0)

    def test_loja_sem_promocao_segue_com_a_taxa_de_sempre(self):
        from apps.stores.models import Store
        from apps.stores.services.delivery_quote_service import DeliveryQuoteService

        loja = Store(name='X', slug='x', default_delivery_fee=Decimal('9.00'), metadata={})
        cotacao = DeliveryQuoteService.calculate_dynamic_fee(
            loja, distance_km=Decimal('3'), subtotal=Decimal('200')
        )
        self.assertEqual(cotacao['fee'], 9.0)
        self.assertNotIn('frete_gratis', cotacao)
