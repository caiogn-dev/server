"""O que a IA precisa saber da LOJA além do cardápio — e não sabia.

28/09/2026, Cê Saladas: 7 promoções por dia da semana cadastradas, e hoje
(segunda) a Magnifico Camarão está em promoção. A IA recebia só o preço final
e respondeu "no momento não temos promoção do dia". Cliente: "2 dessa
promoção" → "qual promoção?". Frete grátis até 4 km com mínimo de R$ 60,
zonas fixas (Taquaralto R$ 40), vale Vólus, cashback 2%, 10 saladas = 1
grátis, horário — tudo cadastrado, nada chegava ao modelo.
"""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from apps.agents.graph.nodes import _catalog_summary
from apps.agents.services.contexto_comercial import (
    condicoes_de_entrega,
    contexto_comercial,
    fidelidade,
    formas_de_pagamento,
    promocoes,
)
from apps.stores.models import StoreCategory
from apps.stores.tests.factories import make_product, make_store

BRT = ZoneInfo('America/Sao_Paulo')
SEGUNDA = datetime(2026, 9, 28, 12, 0, tzinfo=BRT)  # weekday 0


def _loja_com_promos():
    store = make_store()
    camarao = make_product(store, name='Magnifico Camarão', price=Decimal('48.99'))
    camarao.promo_price = Decimal('36.74'); camarao.promo_weekday = 0; camarao.save()
    lombo = make_product(store, name='Basic Lombo', price=Decimal('40.99'))
    lombo.promo_price = Decimal('30.75'); lombo.promo_weekday = 1; lombo.save()
    combo = make_product(store, name='Combo Tilápia', price=Decimal('150.00'))
    combo.compare_at_price = Decimal('187.96'); combo.save()
    make_product(store, name='Coca-Cola', price=Decimal('7.00'))
    return store


@pytest.mark.django_db
class TestPromocoes:
    def test_promocao_de_hoje_com_preco_normal_e_a_semana(self):
        texto = promocoes(_loja_com_promos(), SEGUNDA)
        assert 'PROMOÇÃO DE HOJE' in texto and 'segunda' in texto.lower()
        assert 'Magnifico Camarão' in texto and '36,74' in texto and '48,99' in texto
        # a semana inteira, para "e amanhã?" / "qual dia tem lombo?"
        assert 'Terça' in texto and 'Basic Lombo' in texto and '30,75' in texto
        # oferta permanente (de/por)
        assert 'Combo Tilápia' in texto and '187,96' in texto

    def test_sem_promocao_hoje_diz_isso_e_manda_nao_inventar(self):
        store = make_store()
        p = make_product(store, name='Lombo', price=Decimal('40'))
        p.promo_price = Decimal('30'); p.promo_weekday = 1; p.save()
        texto = promocoes(store, SEGUNDA)
        assert 'Nenhuma promoção do dia hoje' in texto
        assert 'Terça' in texto
        assert 'não invente' in texto.lower()

    def test_loja_sem_promocao_nenhuma(self):
        texto = promocoes(make_store(), SEGUNDA)
        assert 'Nenhuma promoção' in texto

    def test_cardapio_marca_o_item_em_promocao(self):
        texto = _catalog_summary(_loja_com_promos())
        linha = next(l for l in texto.splitlines() if 'Magnifico Camarão' in l)
        assert '36.74' in linha and 'PROMOÇÃO DE HOJE' in linha and '48.99' in linha
        linha = next(l for l in texto.splitlines() if 'Combo Tilápia' in l)
        assert 'de R$ 187.96' in linha
        assert 'PROMOÇÃO' not in next(l for l in texto.splitlines() if 'Coca-Cola' in l)


@pytest.mark.django_db
class TestEntregaPagamentoFidelidade:
    def test_entrega_le_as_regras_reais_da_loja(self):
        store = make_store(address='Q. 112 Sul, Rua Sr 01, 2 - Palmas')
        store.metadata = {
            'frete_gratis': {'ativo': True, 'ate_km': 4, 'pedido_minimo': 60},
            'fixed_price_zones': [{'name': 'Taquaralto', 'fee': 40}, {'name': 'Residencial Polinésia', 'fee': 25}],
            'delivery_max_distance': 50,
        }
        store.save()
        texto = condicoes_de_entrega(store)
        assert 'grátis' in texto.lower() and '4 km' in texto and '60' in texto
        assert 'Taquaralto' in texto and '40' in texto and 'Polinésia' in texto
        assert '50 km' in texto
        assert 'Q. 112 Sul' in texto  # retirada

    def test_entrega_sem_nada_configurado_nao_inventa(self):
        texto = condicoes_de_entrega(make_store())
        assert 'grátis' not in texto.lower()
        assert 'km' not in texto

    def test_pagamento_lista_o_que_o_checkout_oferece(self):
        store = make_store()  # sem gateway: só "pagar na entrega/retirada"
        texto = formas_de_pagamento(store)
        assert 'na entrega' in texto.lower() or 'retirada' in texto.lower()
        assert 'PIX' not in texto  # sem gateway não há PIX online — não prometer

    def test_fidelidade_cashback_e_carteira(self):
        store = make_store()
        cat = StoreCategory.objects.create(store=store, name='Saladas Especiais')
        store.metadata = {
            'cashback_enabled': True, 'cashback_percent': 2,
            'loyalty_enabled': True, 'loyalty_salads_required': 10,
            'loyalty_qualifying_categories': [str(cat.id)],
            'carteira_tiers': [
                {'nome': 'Leve', 'paga': '139.00', 'credito': '152.00'},
                {'nome': 'Teste do dono', 'paga': '1.00', 'credito': '2.00'},
            ],
        }
        store.save()
        texto = fidelidade(store)
        assert '2%' in texto
        assert '10' in texto and 'grátis' in texto and 'Saladas Especiais' in texto
        assert 'Leve' in texto and '139' in texto and '152' in texto
        assert 'Teste do dono' not in texto

    def test_fidelidade_desligada_fica_vazia(self):
        assert fidelidade(make_store()) == ''

    def test_contexto_junta_tudo_com_horario(self):
        store = _loja_com_promos()
        store.operating_hours = {
            d: {'open': '08:00', 'close': '17:00', 'is_open': d not in ('saturday', 'sunday')}
            for d in ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')
        }
        store.save()
        texto = contexto_comercial(store, SEGUNDA)
        assert 'PROMOÇÃO DE HOJE' in texto
        assert 'ABERTA' in texto and 'Sábado: FECHADO' in texto
        assert 'PAGAMENTO' in texto
