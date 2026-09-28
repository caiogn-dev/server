"""Recuperador: quem falou com o bot, não pediu e sumiu recebe um texto na janela."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.automation.mensageiro import recuperador
from apps.automation.models import CompanyProfile, CustomerSession
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreOrder
from apps.stores.tests.factories import make_product
from apps.whatsapp.models import WhatsAppAccount


def _loja(**perguntou):
    dono = get_user_model().objects.create_user(username='dono-rec', password='x')
    loja = Store.objects.create(name='Loja Rec', slug='loja-rec', owner=dono, status='active')
    conta = WhatsAppAccount.objects.create(
        name='Conta Rec', phone_number_id='pn-rec', waba_id='wa-rec', phone_number='+5563900000601',
        display_phone_number='+5563900000601', access_token_encrypted='x', webhook_verify_token='x', owner=dono,
    )
    loja.whatsapp_account = conta
    loja.metadata = {'recuperador': {'perguntou': {'ativo': True, 'apos_horas': 3, **perguntou}}}
    loja.save()
    return loja, conta


def _conversa(conta, tel, nome, ha_horas, modo='auto'):
    conv = Conversation.objects.create(account=conta, phone_number=tel, contact_name=nome, mode=modo)
    Conversation.objects.filter(pk=conv.pk).update(last_customer_message_at=timezone.now() - timedelta(hours=ha_horas))
    conv.refresh_from_db()
    return conv


@pytest.mark.django_db
def test_manda_so_para_quem_perguntou_e_sumiu_uma_vez():
    loja, conta = _loja()
    perfil = CompanyProfile.objects.get(store=loja)
    hoje = make_product(loja, name='Queridinha', price=Decimal('36.99'))
    hoje.promo_price = Decimal('28.99'); hoje.promo_weekday = timezone.localtime().weekday(); hoje.save()

    alvo = _conversa(conta, '5563999990601', 'Ana Paula', 4)          # perguntou há 4 h: recebe
    _conversa(conta, '5563999990602', 'Bia', 1)                        # ainda dentro do prazo: não
    _conversa(conta, '5563999990603', 'Ca', 4, modo='human')           # em modo humano: não
    pediu = _conversa(conta, '5563999990604', 'Du', 4)                 # pediu depois: não
    StoreOrder.objects.create(store=loja, customer_phone=pediu.phone_number, customer_name='Du', source='whatsapp',
                              subtotal=Decimal('10'), total=Decimal('10'), payment_status='paid', status='confirmed')
    carrinho = _conversa(conta, '5563999990605', 'Ed', 4)             # tem carrinho: é do lembrete de carrinho
    CustomerSession.objects.create(company=perfil, phone_number=carrinho.phone_number, status='active', cart_items_count=1)
    _conversa(conta, '5563999990606', 'Fa', 12)                        # velha demais: não

    with patch('apps.automation.mensageiro.canal.enviar_texto', return_value=object()) as enviar:
        enviados = recuperador.seguir_quem_so_perguntou(loja)

    assert enviados == 1
    args, kwargs = enviar.call_args
    assert args[1] == alvo.phone_number
    assert 'Oi, Ana!' in args[2] and 'Queridinha de ~R$ 36,99~ por *R$ 28,99*' in args[2]
    assert kwargs['evento'] == 'recuperador_perguntou'
    alvo.refresh_from_db()
    assert alvo.context['recuperador_perguntou_em']

    # segunda passada: não repete
    with patch('apps.automation.mensageiro.canal.enviar_texto', return_value=object()) as enviar2:
        assert recuperador.seguir_quem_so_perguntou(loja) == 0
    enviar2.assert_not_called()


@pytest.mark.django_db
def test_desligado_nao_manda_e_texto_e_configuravel():
    loja, conta = _loja(ativo=False)
    _conversa(conta, '5563999990611', 'Ana', 4)
    with patch('apps.automation.mensageiro.canal.enviar_texto') as enviar:
        assert recuperador.seguir_quem_so_perguntou(loja) == 0
    enviar.assert_not_called()

    loja.metadata['recuperador']['perguntou'] = {'ativo': True, 'apos_horas': 3, 'texto': 'E aí {nome}, vamos fechar?{oferta}'}
    loja.save()
    with patch('apps.automation.mensageiro.canal.enviar_texto', return_value=object()) as enviar:
        assert recuperador.seguir_quem_so_perguntou(loja) == 1
    assert enviar.call_args.args[2] == 'E aí Ana, vamos fechar?'  # sem promoção hoje: sem linha da oferta


@pytest.mark.django_db
def test_config_padrao_e_limites():
    dono = get_user_model().objects.create_user(username='dono-rec2', password='x')
    loja = Store.objects.create(name='L', slug='loja-rec2', owner=dono, status='active', metadata={'recuperador': {'perguntou': {'apos_horas': 99}}})
    cfg = recuperador.config(loja)
    assert cfg['perguntou']['ativo'] is False and cfg['perguntou']['apos_horas'] == 20
    assert cfg['carrinho']['incluir_oferta'] is True
