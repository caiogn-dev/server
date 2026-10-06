"""Pergunta sobre promoção tem resposta mesmo quando a IA cai.

MEDIDO (06/10, conversas de 14 dias): "Bom dia, qual a promoção do dia?",
"Oi Caio! Hoje tem promoção de quê?" e "Terça tem promoção de salada?"
receberam "Como posso te ajudar? 👇". A promoção só existia no contexto da IA,
e a IA (NVIDIA) respondia 503 nesses momentos. A loja tem a resposta no banco.
"""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model

from apps.automation.services.resposta_de_promocao import responder_promocao
from apps.stores.models import Store, StoreProduct

# 06/10/2026 é terça-feira (weekday 1).
TERCA = datetime(2026, 10, 6, 10, 0, tzinfo=ZoneInfo('America/Araguaina'))


@pytest.fixture
def loja(db):
    dono = get_user_model().objects.create_user('dono-promo', 'p@t.com', 'x')
    loja = Store.objects.create(owner=dono, name='Cê Promo', slug='ce-promo', status='active')
    StoreProduct.objects.create(store=loja, name='Basic Lombo', slug='lombo', price=Decimal('40.99'),
                                promo_price=Decimal('30.75'), promo_weekday=1, is_active=True)
    StoreProduct.objects.create(store=loja, name='Almôndega Premium', slug='almondega', price=Decimal('44.99'),
                                promo_price=Decimal('30.75'), promo_weekday=2, is_active=True)
    return loja


def test_promocao_de_hoje(loja):
    texto = responder_promocao(loja, 'Bom dia, qual a promoção do dia?', TERCA)
    assert 'Basic Lombo' in texto and '30,75' in texto
    assert 'Almôndega' not in texto


def test_amanha(loja):
    texto = responder_promocao(loja, 'amanhã tem promo?', TERCA)
    assert 'Almôndega Premium' in texto


def test_dia_da_semana_citado(loja):
    texto = responder_promocao(loja, 'Quarta tem promoção de salada?', TERCA)
    assert 'Almôndega Premium' in texto


def test_dia_sem_promocao_diz_isso_e_mostra_os_outros_dias(loja):
    texto = responder_promocao(loja, 'domingo tem oferta?', TERCA)
    assert 'domingo' in texto.lower()
    assert 'Basic Lombo' in texto or 'Almôndega' in texto


def test_mensagem_que_nao_e_sobre_promocao(loja):
    assert responder_promocao(loja, 'Vieram com cebola', TERCA) is None
