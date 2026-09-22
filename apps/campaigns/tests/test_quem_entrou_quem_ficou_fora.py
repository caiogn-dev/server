"""Quem recebeu a campanha, quem ficou de fora — e por quê, em português.

Campanha de 18/09 (texto livre, só janela aberta): 380 contatos, 28
receberam, 352 pulados. O relatório do painel mostrava só "28
destinatários" e explicava falhas com um chute ("quase sempre número
inválido ou fora da janela"). No banco:
  - os 352 pulados NÃO tinham motivo gravado;
  - as falhas traziam o erro cru da Meta em inglês (131049 "maintain healthy
    ecosystem" = limite de promoções da Meta; 130472 = número em teste).
E os pedidos de saída ("Parar promoções") não tinham rota nenhuma: o card
"Pediram para parar" mostrava 0 com 11 pessoas fora da lista.
"""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.campaigns.models import Campaign, CampaignRecipient
from apps.campaigns.services.campaign_service import CampaignService
from apps.campaigns.services.janela import MARCA, recortar_para_a_janela
from apps.campaigns.services.motivos import explicar
from apps.campaigns.services.optout import registrar_saida
from apps.conversations.models import Conversation
from apps.whatsapp.models import WhatsAppAccount

PULADO = CampaignRecipient.RecipientStatus.SKIPPED


def _conta(dono, sufixo='71'):
    return WhatsAppAccount.objects.create(
        name=f'Conta {sufixo}', phone_number_id=f'pn-q{sufixo}', waba_id=f'wa-q{sufixo}',
        phone_number=f'+55639000000{sufixo}', display_phone_number=f'+55639000000{sufixo}',
        access_token_encrypted='x', webhook_verify_token='x', owner=dono,
    )


@pytest.fixture
def dono(db):
    return get_user_model().objects.create_user(username='dono-quem', password='x')


@pytest.fixture
def conta(dono):
    return _conta(dono)


def _campanha(conta, so_janela=True, status=Campaign.CampaignStatus.DRAFT):
    return Campaign.objects.create(
        account=conta, name='Oferta', message_content={'text': 'oi'},
        audience_filters={MARCA: True} if so_janela else {}, status=status,
    )


def _dest(campanha, tel, status=CampaignRecipient.RecipientStatus.PENDING, **kw):
    return CampaignRecipient.objects.create(campaign=campanha, phone_number=tel, status=status, **kw)


@pytest.mark.django_db
class TestMotivoGravadoNoPulo:
    def test_fora_da_janela_no_inicio(self, conta):
        c = _campanha(conta)
        r = _dest(c, '5563999990301')  # nunca falou com a loja: janela fechada

        recortar_para_a_janela(c)

        r.refresh_from_db()
        assert r.status == PULADO
        assert r.error_code == 'fora_da_janela'

    def test_pediu_para_parar_no_envio(self, conta):
        c = _campanha(conta, so_janela=False, status=Campaign.CampaignStatus.RUNNING)
        r = _dest(c, '5563999990302')
        registrar_saida(conta, '5563999990302', 'Parar promoções', 'button')

        CampaignService().process_campaign_batch(str(c.id))

        r.refresh_from_db()
        assert r.status == PULADO
        assert r.error_code == 'pediu_para_parar'

    def test_janela_fechou_durante_o_envio(self, conta):
        c = _campanha(conta, status=Campaign.CampaignStatus.RUNNING)
        r = _dest(c, '5563999990303')

        CampaignService().process_campaign_batch(str(c.id))

        r.refresh_from_db()
        assert r.status == PULADO
        assert r.error_code == 'janela_fechou_no_envio'


@pytest.mark.django_db
class TestExplicacaoEmPortugues:
    def test_limite_de_promocoes_da_meta(self, conta):
        r = _dest(_campanha(conta), '5563999990304', status=CampaignRecipient.RecipientStatus.FAILED,
                  error_code='131049', error_message='This message was not delivered to maintain healthy ecosystem')
        e = explicar(r)
        assert e['situacao'] == 'falhou'
        assert 'Meta' in e['motivo'] and 'promo' in e['motivo'].lower()
        assert 'ecosystem' not in e['motivo']

    def test_pulado_antigo_sem_motivo_de_quem_pediu_para_parar(self, conta):
        registrar_saida(conta, '5563999990305', 'Parar promoções', 'button')
        r = _dest(_campanha(conta), '5563999990305', status=PULADO)
        assert 'parar' in explicar(r)['motivo'].lower()

    def test_pulado_antigo_sem_motivo_em_campanha_so_janela(self, conta):
        r = _dest(_campanha(conta), '5563999990306', status=PULADO)
        e = explicar(r)
        assert e['situacao'] == 'ficou_de_fora'
        assert '24h' in e['motivo']

    def test_quem_leu(self, conta):
        r = _dest(_campanha(conta), '5563999990307', status=CampaignRecipient.RecipientStatus.READ)
        assert explicar(r)['situacao'] == 'leu'


@pytest.mark.django_db
class TestRotas:
    def _cliente(self, dono):
        c = APIClient()
        c.force_authenticate(dono)
        return c

    def test_destinatarios_com_resumo_e_motivo(self, dono, conta):
        c = _campanha(conta)
        _dest(c, '5563999990311', status=CampaignRecipient.RecipientStatus.READ, contact_name='Ana')
        _dest(c, '5563999990312', status=PULADO, error_code='fora_da_janela', contact_name='Bia')
        _dest(c, '5563999990313', status=CampaignRecipient.RecipientStatus.FAILED,
              error_code='131049', contact_name='Caio')

        r = self._cliente(dono).get(f'/api/v1/campaigns/campaigns/{c.id}/destinatarios/')

        assert r.status_code == 200, r.content
        corpo = r.json()
        assert corpo['resumo']['leu'] == 1
        assert corpo['resumo']['ficou_de_fora'] == 1
        assert corpo['resumo']['falhou'] == 1
        bia = next(p for p in corpo['pessoas'] if p['nome'] == 'Bia')
        assert '24h' in bia['motivo']

    def test_destinatarios_filtra_por_situacao(self, dono, conta):
        c = _campanha(conta)
        _dest(c, '5563999990314', status=CampaignRecipient.RecipientStatus.READ, contact_name='Ana')
        _dest(c, '5563999990315', status=PULADO, error_code='fora_da_janela', contact_name='Bia')

        r = self._cliente(dono).get(
            f'/api/v1/campaigns/campaigns/{c.id}/destinatarios/', {'situacao': 'ficou_de_fora'},
        )

        assert [p['nome'] for p in r.json()['pessoas']] == ['Bia']

    def test_saidas_lista_quem_pediu_para_parar(self, dono, conta):
        registrar_saida(conta, '5563999990321', 'Parar promoções', 'button')
        registrar_saida(conta, '5563999990322', 'PARAR', 'text')

        r = self._cliente(dono).get('/api/v1/campaigns/campaigns/saidas/')

        assert r.status_code == 200, r.content
        assert r.json()['total'] == 2
        assert {s['origem'] for s in r.json()['pessoas']} == {'button', 'text'}

    def test_saidas_de_outra_conta_nao_aparecem(self, dono, conta):
        outro = get_user_model().objects.create_user(username='outro-quem', password='x')
        registrar_saida(_conta(outro, '72'), '5563999990323', 'Parar promoções', 'button')

        assert self._cliente(dono).get('/api/v1/campaigns/campaigns/saidas/').json()['total'] == 0
