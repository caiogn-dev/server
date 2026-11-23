"""O "Entregas a partir de" da vitrine é a mesma base que a cotação cobra (23/11).

Dono: painel com "R$ 7 até 3 km" e o topo do cardápio dizendo "a partir de
R$ 8,00". A cotação lê `metadata.delivery_base_fee` (o que o painel grava) e a
vitrine lia `default_delivery_fee` (coluna antiga). Medido: Cê 8×7, Pastita 10×7.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.stores.models import Store
from apps.stores.services.delivery_quote_service import DeliveryQuoteService


@pytest.fixture
def loja(db):
    dono = get_user_model().objects.create_user(username='dono-frete', password='x')
    return Store.objects.create(
        owner=dono, name='Cê Frete', slug='ce-frete', status='active', city='Palmas',
        default_delivery_fee=Decimal('8.00'),
        metadata={'delivery_base_fee': 7, 'delivery_flat_km': 3},
    )


def test_base_vem_do_que_o_painel_grava(loja):
    assert DeliveryQuoteService.taxa_base(loja) == Decimal('7')


def test_sem_metadata_usa_a_coluna(loja):
    loja.metadata = {}
    assert DeliveryQuoteService.taxa_base(loja) == Decimal('8.00')


def test_cotacao_dentro_do_raio_cobra_a_base(loja):
    assert Decimal(str(DeliveryQuoteService.calculate_dynamic_fee(loja, Decimal('2'))['fee'])) == Decimal('7')


def test_app_config_mostra_a_mesma_base(loja):
    r = APIClient().get(f'/api/v1/stores/{loja.slug}/app-config/')
    assert r.json()['delivery']['default_delivery_fee'] == 7.0


def test_loja_publica_mostra_a_mesma_base(loja):
    r = APIClient().get(f'/api/v1/stores/{loja.slug}/')
    assert Decimal(str(r.json()['default_delivery_fee'])) == Decimal('7')


def test_catalogo_mostra_a_mesma_base(loja):
    """O SSR do cardápio monta o topo a partir do /catalog/, não do /stores/<slug>/."""
    from django.core.cache import cache
    cache.delete(f'catalog:{loja.slug}')
    r = APIClient().get(f'/api/v1/stores/{loja.slug}/catalog/')
    assert Decimal(str(r.json()['store']['default_delivery_fee'])) == Decimal('7')
