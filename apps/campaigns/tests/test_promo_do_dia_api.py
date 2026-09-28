"""A tela "Promoção do dia" lê config, prévia, modelos e histórico; e dispara agora."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.stores.models import Store
from apps.stores.tests.factories import make_product
from apps.whatsapp.models import WhatsAppAccount
from apps.conversations.models import Conversation

BASE = '/api/v1/campaigns/promo-do-dia/'


@pytest.fixture
def loja_e_cliente(db):
    dono = get_user_model().objects.create_user(username='dono-pda', password='x')
    loja = Store.objects.create(name='Loja PDA', slug='loja-pda', owner=dono, status='active')
    conta = WhatsAppAccount.objects.create(
        name='C', phone_number_id='pn-pda', waba_id='wa-pda', phone_number='+5563900000701',
        display_phone_number='+5563900000701', access_token_encrypted='x', webhook_verify_token='x', owner=dono,
    )
    loja.whatsapp_account = conta
    loja.save()
    Conversation.objects.create(account=conta, phone_number='5563999990701', contact_name='Ana')
    for wd in range(7):
        p = make_product(loja, name=f'Salada {wd}', price=Decimal('40'))
        p.promo_price = Decimal('30'); p.promo_weekday = wd; p.save()
    c = APIClient()
    c.force_authenticate(dono)
    return loja, c


@pytest.mark.django_db
def test_get_e_disparar(loja_e_cliente):
    loja, cliente = loja_e_cliente
    r = cliente.get(f'{BASE}?store={loja.slug}')
    assert r.status_code == 200, r.content
    d = r.json()
    assert d['config']['ativo'] is False and d['config']['para'] == 'amanha'
    assert d['previa']['ofertas'][0]['preco'] == 'R$ 30,00'
    assert d['historico'] == [] and d['tem_whatsapp'] is True

    r = cliente.post(f'{BASE}?store={loja.slug}', {'acao': 'disparar'}, format='json')
    assert r.status_code == 200, r.content
    assert r.json()['motivo'] == 'janela'
    assert len(cliente.get(f'{BASE}?store={loja.slug}').json()['historico']) == 1


@pytest.mark.django_db
def test_loja_alheia_404(loja_e_cliente, db):
    loja, _ = loja_e_cliente
    outro = get_user_model().objects.create_user(username='outro-pda', password='x')
    c = APIClient()
    c.force_authenticate(outro)
    assert c.get(f'{BASE}?store={loja.slug}').status_code == 404
