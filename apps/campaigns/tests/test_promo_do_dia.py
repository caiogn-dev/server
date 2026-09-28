"""Promoção do dia automática: a campanha nasce sozinha na hora da loja, com o card do dia."""
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model

from apps.campaigns.models import Campaign
from apps.campaigns.services import promo_do_dia
from apps.conversations.models import Conversation
from apps.stores.models import Store
from apps.stores.tests.factories import make_product
from apps.whatsapp.models import MessageTemplate, WhatsAppAccount

BRT = ZoneInfo('America/Sao_Paulo')
SEGUNDA_18H = datetime(2026, 9, 28, 18, 5, tzinfo=BRT)


def _loja(sufixo='pd1', **cfg):
    dono = get_user_model().objects.create_user(username=f'dono-{sufixo}', password='x')
    loja = Store.objects.create(name=f'Loja {sufixo}', slug=f'loja-{sufixo}', owner=dono, status='active')
    conta = WhatsAppAccount.objects.create(
        name=f'Conta {sufixo}', phone_number_id=f'pn-{sufixo}', waba_id=f'wa-{sufixo}',
        phone_number=f'+55639{sufixo}', display_phone_number=f'+55639{sufixo}',
        access_token_encrypted='x', webhook_verify_token='x', owner=dono,
    )
    loja.whatsapp_account = conta
    loja.metadata = {promo_do_dia.CHAVE: {'ativo': True, 'hora': '18:00', **cfg}}
    loja.save()
    # quem já falou com a loja = contato
    Conversation.objects.create(account=conta, phone_number='5563999990501', contact_name='Ana')
    Conversation.objects.create(account=conta, phone_number='5563999990502', contact_name='')
    terca = make_product(loja, name='Basic Lombo', price=Decimal('40.99'))
    terca.promo_price = Decimal('30.75'); terca.promo_weekday = 1; terca.save()
    segunda = make_product(loja, name='Magnifico Camarão', price=Decimal('48.99'))
    segunda.promo_price = Decimal('36.74'); segunda.promo_weekday = 0; segunda.save()
    return loja, conta


@pytest.mark.django_db
class TestMontar:
    def test_amanha_usa_a_promocao_de_terca_e_o_card_de_terca(self):
        loja, _ = _loja(cards={'1': 'https://x/terca.png', '0': 'https://x/segunda.png'})
        plano = promo_do_dia.montar(loja, SEGUNDA_18H)
        assert plano['dia'] == '2026-09-29' and plano['weekday'] == 1
        assert plano['card'] == 'https://x/terca.png'
        assert plano['ofertas'] == [{'nome': 'Basic Lombo', 'preco': 'R$ 30,75', 'de': 'R$ 40,99'}]
        assert 'Amanhã (terça)' in plano['texto'] and 'Basic Lombo' in plano['texto'] and '{nome}' in plano['texto']

    def test_hoje_usa_a_de_segunda(self):
        loja, _ = _loja(para='hoje')
        plano = promo_do_dia.montar(loja, SEGUNDA_18H)
        assert plano['ofertas'][0]['nome'] == 'Magnifico Camarão' and 'Hoje (segunda)' in plano['texto']

    def test_dia_sem_promocao_nao_monta(self):
        loja, _ = _loja()
        quinta = datetime(2026, 10, 1, 18, 5, tzinfo=BRT)  # sexta não tem promo
        assert promo_do_dia.montar(loja, quinta) is None


@pytest.mark.django_db
class TestDisparar:
    def test_modo_janela_cria_campanha_gratis_agendada_para_hoje_com_card(self):
        loja, conta = _loja(cards={'1': 'https://x/terca.png'})
        campanha, motivo = promo_do_dia.disparar(loja, SEGUNDA_18H)
        assert motivo == 'janela'
        assert campanha.status == Campaign.CampaignStatus.SCHEDULED
        assert campanha.audience_filters.get('somente_janela_aberta') is True
        assert campanha.message_content['media_url'] == 'https://x/terca.png'
        assert campanha.message_content['media_type'] == 'image'
        assert 'Basic Lombo' in campanha.message_content['text']
        assert campanha.recipients.count() == 2
        assert campanha.metadata['promo_do_dia'] == '2026-09-29'
        # de novo no mesmo dia: não duplica
        assert promo_do_dia.disparar(loja, SEGUNDA_18H) == (None, 'ja_saiu')

    def test_modo_modelo_preenche_card_e_variaveis_e_inicia(self):
        loja, conta = _loja(modo='modelo', modelo='oferta_do_dia', cards={'1': 'https://x/terca.png'})
        tpl = MessageTemplate.objects.create(
            account=conta, template_id='t1', name='oferta_do_dia', language='pt_BR', category='marketing',
            status='approved', components=[
                {'type': 'HEADER', 'format': 'IMAGE'},
                {'type': 'BODY', 'text': 'Oi, {{nome_cliente}}! • {{produto_1}} — {{preco_1}} • {{produto_2}} — {{preco_2}}'},
            ],
        )
        with patch('apps.campaigns.services.campaign_service.CampaignService.start_campaign') as iniciar:
            campanha, motivo = promo_do_dia.disparar(loja, SEGUNDA_18H)
        assert motivo == 'modelo'
        iniciar.assert_called_once_with(str(campanha.id))
        assert campanha.template_id == tpl.id
        comps = campanha.message_content['components']
        assert comps[0]['parameters'][0]['image']['link'] == 'https://x/terca.png'
        assert [p['variable'] for p in comps[1]['parameters']] == ['nome_cliente', 'produto_1', 'preco_1', 'produto_2', 'preco_2']
        ana = campanha.recipients.get(phone_number__contains='0501')
        assert ana.variables['nome_cliente'] == 'Ana'
        assert ana.variables['produto_1'] == 'Basic Lombo' and ana.variables['preco_1'] == 'R$ 30,75'
        assert ana.variables['produto_2'] == ''  # só uma oferta amanhã: não inventa a segunda

    def test_modo_modelo_sem_card_cai_para_texto_na_janela(self):
        loja, conta = _loja(modo='modelo', modelo='oferta_do_dia')
        MessageTemplate.objects.create(
            account=conta, template_id='t2', name='oferta_do_dia', language='pt_BR', category='marketing',
            status='approved', components=[{'type': 'HEADER', 'format': 'IMAGE'}, {'type': 'BODY', 'text': 'x {{nome_cliente}}'}],
        )
        campanha, motivo = promo_do_dia.disparar(loja, SEGUNDA_18H)
        assert motivo == 'janela' and campanha.template_id is None

    def test_desligado_e_sem_promocao(self):
        loja, _ = _loja(ativo=False)
        assert promo_do_dia.disparar(loja, SEGUNDA_18H) == (None, 'desligado')
        campanha, motivo = promo_do_dia.disparar(loja, SEGUNDA_18H, forcar=True)
        assert motivo == 'janela'


@pytest.mark.django_db
class TestBeat:
    def test_so_dispara_na_hora_da_loja_e_uma_vez(self):
        loja, _ = _loja(hora='18:00')
        cedo = datetime(2026, 9, 28, 17, 50, tzinfo=BRT)
        assert promo_do_dia.rodar_para_todas(cedo) == []
        saida = promo_do_dia.rodar_para_todas(SEGUNDA_18H)
        assert [(s, m) for s, m, _ in saida] == [(loja.slug, 'janela')]
        assert [(s, m) for s, m, _ in promo_do_dia.rodar_para_todas(SEGUNDA_18H)] == [(loja.slug, 'ja_saiu')]
        tarde = datetime(2026, 9, 28, 21, 30, tzinfo=BRT)  # passou a tolerância de 3 h
        assert promo_do_dia.rodar_para_todas(tarde) == []
