"""Aviso de status com o texto que o dono vê no painel — e coerente com retirada.

19/10/2026, Maria Vitória (CE-2610194335, RETIRADA): recebeu "Estamos preparando
seu pedido. Em breve estará a caminho!" — frase de entrega num pedido que ela
ia buscar. O dono olhou "Modelos de mensagem" no painel e via outra coisa:

    👨‍🍳 Seu pedido está sendo preparado!
    Olá {{nome}},
    Pedido #{{pedido}} em preparação.
    ⏱️ Falta aproximadamente {{tempo}} minutos!

A tela era uma lista fixa do painel, sem ligação com o que sai. O que sai é a
AutoMessage da loja. Agora o texto padrão é o do painel, com dado real: nome,
número, tempo de preparo fotografado no pedido. Linha sem dado some inteira
(sem "Falta aproximadamente  minutos").
"""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

from apps.automation.models import AutoMessage, CompanyProfile
from apps.automation.services.automation_service import AutomationService
from apps.automation.textos_de_aviso import renderizar_aviso
from apps.stores.models import Store, StoreOrder
from apps.whatsapp.models import WhatsAppAccount
from apps.whatsapp.tasks import automation_tasks

TEXTO = 'apps.whatsapp.services.whatsapp_api_service.WhatsAppAPIService.send_text_message'
JANELA = 'apps.automation.mensageiro.janela.aberta'
OK = {'messages': [{'id': 'wamid.aviso-painel'}]}


@pytest.fixture(autouse=True)
def _limpo():
    cache.clear()
    with patch('apps.whatsapp.services.whatsapp_api_service.WhatsAppAPIService.__init__', return_value=None):
        yield
    cache.clear()


@pytest.fixture
def loja(db):
    dono = get_user_model().objects.create_user(username='dono-aviso-painel', password='x')
    conta = WhatsAppAccount.objects.create(
        name='Conta Painel', phone_number_id='pn-painel', waba_id='wa-painel',
        phone_number='+5563900000091', display_phone_number='+5563900000091',
        access_token_encrypted='x', webhook_verify_token='x', owner=dono,
        status=WhatsAppAccount.AccountStatus.ACTIVE,
    )
    loja = Store.objects.create(
        owner=dono, name='Cê Saladas', slug='loja-aviso-painel',
        whatsapp_account=conta, default_prep_minutes=40,
    )
    perfil, _ = CompanyProfile.objects.get_or_create(store=loja)
    perfil.account = conta
    perfil.save()
    AutoMessage.objects.filter(company=perfil).delete()
    AutomationService().ensure_auto_messages(perfil)
    return loja


def _pedido(loja, **extra):
    dados = dict(
        store=loja, total=Decimal('76.43'), subtotal=Decimal('76.43'),
        status='confirmed', payment_status='paid', payment_method='pix',
        customer_name='Maria Vitória Matsubara', customer_phone='63981039494',
        delivery_method='pickup',
    )
    dados.update(extra)
    return StoreOrder.objects.create(**dados)


def _texto_enviado(pedido, status):
    with patch(JANELA, return_value=True), patch(TEXTO, return_value=OK) as envio:
        automation_tasks.notify_order_status_change.apply(args=[str(pedido.id), status])
    envio.assert_called_once()
    return envio.call_args.kwargs.get('text') or envio.call_args.args[1]


@pytest.mark.django_db
def test_preparo_de_retirada_sai_com_o_texto_do_painel(loja):
    pedido = _pedido(loja, prep_minutes=40)
    texto = _texto_enviado(pedido, 'preparing')

    assert 'Seu pedido está sendo preparado!' in texto
    assert 'Olá Maria,' in texto
    assert f'Pedido #{pedido.order_number} em preparação.' in texto
    assert 'Falta aproximadamente 40 minutos!' in texto
    assert 'caminho' not in texto
    assert '{' not in texto


@pytest.mark.django_db
def test_preparo_sem_tempo_tira_a_linha_do_tempo(loja):
    loja.default_prep_minutes = 0
    loja.save(update_fields=['default_prep_minutes'])
    pedido = _pedido(loja, prep_minutes=0)
    texto = _texto_enviado(pedido, 'preparing')

    assert 'Falta aproximadamente' not in texto
    assert '{' not in texto
    assert texto.endswith('em preparação.')


@pytest.mark.django_db
def test_confirmado_mostra_total_e_tempo(loja):
    pedido = _pedido(loja)
    texto = _texto_enviado(pedido, 'confirmed')

    assert 'Pedido Confirmado!' in texto
    assert f'recebemos seu pedido #{pedido.order_number}' in texto
    assert 'R$ 76,43' in texto
    assert '40 min' in texto


@pytest.mark.django_db
def test_saiu_para_entrega_mostra_o_endereco(loja):
    pedido = _pedido(
        loja, delivery_method='delivery',
        delivery_address={'street': 'Quadra 110 Norte Alameda 8', 'number': '29', 'city': 'Palmas'},
    )
    texto = _texto_enviado(pedido, 'out_for_delivery')

    assert 'Seu pedido saiu para entrega!' in texto
    assert 'Quadra 110 Norte Alameda 8, 29' in texto


@pytest.mark.django_db
def test_entregue_de_retirada_nao_fala_em_entrega(loja):
    pedido = _pedido(loja)
    texto = _texto_enviado(pedido, 'delivered')

    assert 'retirado' in texto
    assert 'entregue' not in texto.lower()


def test_linha_com_variavel_vazia_some_e_nao_sobra_buraco():
    texto = renderizar_aviso(
        'Olá {primeiro_nome},\n\nPedido #{order_number}.\n⏱️ Falta {tempo} min!\n\nAté já.',
        {'primeiro_nome': 'Ana', 'order_number': 'CE-1', 'tempo': ''},
    )
    assert texto == 'Olá Ana,\n\nPedido #CE-1.\n\nAté já.'


def test_variavel_desconhecida_fica_como_esta():
    """Texto que o dono escreveu com chave que não existe não perde a linha."""
    assert renderizar_aviso('Oi {apelido}', {}) == 'Oi {apelido}'
