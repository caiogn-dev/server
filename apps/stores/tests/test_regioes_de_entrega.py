"""Regiões de entrega fora da cidade — Agrião em Paraíso e Porto Nacional (06/10).

Decisões do dono:
- tudo sai de Palmas; frete fixo Porto R$ 25, Paraíso R$ 30;
- entrega no DIA SEGUINTE (pediu segunda, sai terça); domingo não sai;
- o lojista escolhe quais categorias valem em cada região;
- só pagamento antecipado (PIX/cartão online) — sem maquininha nem dinheiro;
- pedido mínimo configurável (começa sem).

E dois defeitos que barrariam isso hoje:
- o checkout recusava por distância (máx. 16 km) ANTES de olhar a zona fixa;
- o checkout casava zona fixa por `enabled`/`max_km`, ignorando as palavras-chave
  que a cotação usa — cotação e cobrança podiam discordar.
"""
from datetime import date, datetime
from decimal import Decimal
from unittest import mock
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model

from apps.stores.models import Store, StoreCart, StoreCartItem, StoreCategory, StoreProduct
from apps.stores.services import regioes_de_entrega as regioes

TZ = ZoneInfo('America/Araguaina')


def _regras(**extra):
    zona = {'name': 'Paraíso do Tocantins', 'fee': 30, 'keywords': ['paraiso do tocantins'],
            'entrega_dia_seguinte': True, 'dias_sem_entrega': [6], 'so_pagamento_antecipado': True, **extra}
    return regioes.RegrasDaRegiao.da_zona(zona)


class TestDataDeEntrega:
    @pytest.mark.parametrize('pedido, entrega', [
        (datetime(2026, 10, 5, 22, 0, tzinfo=TZ), date(2026, 10, 6)),   # segunda 22h → terça
        (datetime(2026, 10, 10, 9, 0, tzinfo=TZ), date(2026, 10, 12)),  # sábado → segunda (domingo não sai)
        (datetime(2026, 10, 11, 9, 0, tzinfo=TZ), date(2026, 10, 12)),  # domingo → segunda
    ])
    def test_dia_seguinte_pulando_domingo(self, pedido, entrega):
        assert _regras().data_de_entrega(pedido) == entrega

    def test_regiao_sem_regra_de_dia_seguinte_nao_agenda(self):
        assert _regras(entrega_dia_seguinte=False).data_de_entrega(datetime(2026, 10, 5, 22, tzinfo=TZ)) is None


class TestValidacao:
    def test_categoria_fora_da_regiao_e_recusada_com_o_nome_do_item(self):
        r = _regras(categorias=['congelados'])
        erros = r.erros(itens=[('Salada Caesar', 'saladas'), ('Escondidinho', 'congelados')],
                        subtotal=Decimal('50'), forma_de_pagamento='pix')
        assert any('Salada Caesar' in e for e in erros)
        assert not any('Escondidinho' in e for e in erros)

    def test_sem_lista_de_categorias_vale_tudo(self):
        assert _regras().erros(itens=[('Salada', 'saladas')], subtotal=Decimal('50'), forma_de_pagamento='pix') == []

    def test_pedido_minimo(self):
        erros = _regras(pedido_minimo=80).erros(itens=[], subtotal=Decimal('50'), forma_de_pagamento='pix')
        assert any('80,00' in e for e in erros)

    @pytest.mark.parametrize('forma', ['cash', 'card_on_delivery'])
    def test_pagamento_na_entrega_e_recusado(self, forma):
        assert _regras().erros(itens=[], subtotal=Decimal('50'), forma_de_pagamento=forma)

    def test_pix_e_cartao_online_passam(self):
        for forma in ('pix', 'credit_card'):
            assert _regras().erros(itens=[], subtotal=Decimal('50'), forma_de_pagamento=forma) == []


# ── integração ──────────────────────────────────────────────────────────────

@pytest.fixture
def loja(db):
    dono = get_user_model().objects.create_user(username='dono-reg', password='x')
    return Store.objects.create(
        owner=dono, name='Agrião Reg', slug='agriao-reg', status='active',
        latitude=Decimal('-10.21'), longitude=Decimal('-48.33'),
        metadata={'delivery_max_km': 16, 'fixed_price_zones': [
            {'name': 'Paraíso do Tocantins', 'fee': 30, 'keywords': ['paraiso do tocantins'],
             'entrega_dia_seguinte': True, 'dias_sem_entrega': [6], 'so_pagamento_antecipado': True,
             'categorias': []},
        ]},
    )


def _em_paraiso():
    """Cliente a 60 km cujo reverse geocode diz Paraíso do Tocantins."""
    from apps.stores.services.unified_delivery_service import UnifiedDeliveryService
    from apps.stores.services.geo import geo_service
    return [
        mock.patch.object(UnifiedDeliveryService, '_resolve_coordinates',
                          return_value={'success': True, 'lat': -10.17, 'lng': -48.88, 'formatted_address': 'Centro, Paraíso do Tocantins - TO'}),
        mock.patch.object(UnifiedDeliveryService, '_calculate_distance_and_duration',
                          return_value={'success': True, 'distance_km': 61.0, 'duration_minutes': 55}),
        mock.patch.object(geo_service, 'reverse_geocode',
                          return_value={'formatted_address': 'Av. Bernardo Sayão, Centro, Paraíso do Tocantins - TO', 'city': 'Paraíso do Tocantins'}),
    ]


@pytest.mark.django_db
class TestCotacaoNoCheckout:
    def test_regiao_a_60_km_cota_frete_fixo_em_vez_de_recusar_por_distancia(self, loja):
        from apps.stores.services.unified_delivery_service import UnifiedDeliveryService
        patches = _em_paraiso()
        with patches[0], patches[1], patches[2]:
            r = UnifiedDeliveryService.calculate_delivery_fee(loja, lat=-10.17, lng=-48.88)
        assert r['success'], r
        assert Decimal(str(r['fee'])) == Decimal('30')
        assert r['regiao']['nome'] == 'Paraíso do Tocantins'
        assert r['regiao']['so_pagamento_antecipado'] is True


@pytest.mark.django_db
class TestCheckout:
    def _sacola(self, loja, categoria_slug='congelados'):
        cat = StoreCategory.objects.create(store=loja, name=categoria_slug.title(), slug=categoria_slug)
        p = StoreProduct.objects.create(store=loja, category=cat, name='Escondidinho', slug=f'esc-{categoria_slug}',
                                        price=Decimal('23.00'), status='active', track_stock=False)
        cart = StoreCart.objects.create(store=loja, session_key=f'sess-{categoria_slug}')
        StoreCartItem.objects.create(cart=cart, product=p, quantity=3)
        return cart, cat

    def _pedir(self, loja, cart, forma='pix', fee_do_cliente=None):
        from apps.stores.services.checkout_service import CheckoutService
        entrega = {'method': 'delivery', 'address': {
            'street': 'Av. Bernardo Sayão', 'number': '535', 'neighborhood': 'Centro',
            'city': 'Paraíso do Tocantins', 'state': 'TO', 'lat': -10.17, 'lng': -48.88,
        }}
        if fee_do_cliente is not None:
            entrega['fee'] = fee_do_cliente
        patches = _em_paraiso()
        agora = datetime(2026, 10, 10, 9, 0, tzinfo=TZ)  # sábado
        with patches[0], patches[1], patches[2], mock.patch('django.utils.timezone.now', return_value=agora):
            return CheckoutService.create_order(
                cart=cart, customer_data={'name': 'Cliente Paraíso', 'phone': '5563999990000', 'email': ''},
                delivery_data=entrega, payment_method=forma,
            )

    def test_pedido_valido_ganha_data_de_entrega_e_o_frete_da_regiao(self, loja):
        cart, _ = self._sacola(loja)
        pedido = self._pedir(loja, cart, fee_do_cliente=5)
        assert pedido.delivery_fee == Decimal('30.00')       # o cliente não escolhe o frete
        assert pedido.scheduled_date == date(2026, 10, 12)    # sábado → segunda

    def test_categoria_fora_da_regiao_recusa_com_mensagem(self, loja):
        cart, cat = self._sacola(loja, 'saladas')
        meta = dict(loja.metadata)
        meta['fixed_price_zones'][0]['categorias'] = ['id-que-nao-e-saladas']
        loja.metadata = meta
        loja.save(update_fields=['metadata'])
        with pytest.raises(regioes.RegiaoRecusou) as erro:
            self._pedir(loja, cart)
        assert 'Escondidinho' in str(erro.value)

    def test_dinheiro_e_recusado(self, loja):
        cart, _ = self._sacola(loja)
        with pytest.raises(regioes.RegiaoRecusou):
            self._pedir(loja, cart, forma='cash')


# ── busca de endereço ───────────────────────────────────────────────────────
# Dono (06/10): "está difícil achar o endereço de Paraíso". A busca só pedia ao
# Google endereços num raio ESTRITO de 30 km da loja; Paraíso fica a ~60 km.

class TestRaioDaBusca:
    def _loja(self, zonas):
        return Store(metadata={'fixed_price_zones': zonas} if zonas is not None else {})

    def test_loja_sem_regiao_continua_com_30_km(self):
        assert regioes.raio_da_busca_km(self._loja(None)) == 30

    def test_loja_com_regiao_de_frete_fixo_busca_mais_longe(self):
        loja = self._loja([{'name': 'Paraíso do Tocantins', 'fee': 30}])
        assert regioes.raio_da_busca_km(loja) >= 80

    def test_zona_de_acrescimo_nao_amplia(self):
        loja = self._loja([{'name': 'Alphaville', 'surcharge_on_km': True, 'surcharge': 5}])
        assert regioes.raio_da_busca_km(loja) == 30


@pytest.mark.django_db
def test_autosuggest_da_loja_usa_o_raio_da_regiao(loja, client):
    from apps.stores.services.geo import geo_service
    with mock.patch.object(geo_service.provider, 'autosuggest', return_value=[]) as busca:
        resp = client.get(f'/api/v1/stores/{loja.slug}/autosuggest/?q=bernardo sayao paraiso')
    assert resp.status_code == 200
    assert busca.call_args.kwargs['radius_km'] >= 80


# ── Luzimangues ─────────────────────────────────────────────────────────────
# Distrito de Porto Nacional colado em Palmas (~16 km da loja). O Google devolve
# só "Porto Nacional, TO" para lá — palavra-chave não separa. A distância separa:
# zona com `ate_km` só casa até aquela distância (em linha reta) da loja.

@pytest.mark.django_db
class TestZonaAteKm:
    def _loja(self):
        dono = get_user_model().objects.create_user(username='dono-luzi', password='x')
        return Store.objects.create(
            owner=dono, name='Agrião Luzi', slug='agriao-luzi', status='active',
            latitude=Decimal('-10.1853'), longitude=Decimal('-48.3036'),
            metadata={'fixed_price_zones': [
                {'name': 'Luzimangues', 'fee': 30, 'keywords': ['porto nacional'], 'ate_km': 30},
                {'name': 'Porto Nacional', 'fee': 25, 'keywords': ['porto nacional']},
            ]},
        )

    def _zona(self, loja, lat, lng):
        from apps.stores.services.geo import geo_service
        with mock.patch.object(geo_service, 'reverse_geocode',
                               return_value={'formatted_address': 'Porto Nacional, TO, Brasil', 'city': 'Porto Nacional'}):
            return regioes.zona_do_endereco(loja, lat, lng)

    def test_perto_da_loja_e_luzimangues(self):
        assert self._zona(self._loja(), -10.1865, -48.4518)['name'] == 'Luzimangues'

    def test_longe_da_loja_cai_em_porto(self):
        assert self._zona(self._loja(), -10.7080, -48.4170)['name'] == 'Porto Nacional'
