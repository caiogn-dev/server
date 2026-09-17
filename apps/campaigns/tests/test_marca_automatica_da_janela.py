"""D1: campanha de texto livre nasce marcada como "só janela aberta".

A Meta recusa texto livre fora da janela de 24h (erro 131047). Marcar a
campanha não pode depender de o dono lembrar de uma caixinha na tela — em
produção, 0 de 8 campanhas tinham a marca, e todas saíram para gente fora da
janela. A marca é decisão do sistema: toda campanha SEM template nasce
marcada; campanha COM template (que passa pela aprovação da Meta) nunca é.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.campaigns.services.campaign_service import CampaignService
from apps.campaigns.services.janela import MARCA
from apps.stores.models import Store
from apps.whatsapp.models import MessageTemplate, WhatsAppAccount

User = get_user_model()


class MarcaAutomaticaDaJanelaTest(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dona-marca', password='x')
        self.account = WhatsAppAccount.objects.create(
            name='Conta', phone_number='556300000001', phone_number_id='2',
        )
        Store.objects.create(
            billing_exempt=True, name='Loja Marca', slug='loja-marca', owner=dono,
            store_type='food', status='active', whatsapp_account=self.account,
        )
        self.template = MessageTemplate.objects.create(
            account=self.account, template_id='tpl-1', name='promo',
            category=MessageTemplate.TemplateCategory.MARKETING,
            status=MessageTemplate.TemplateStatus.APPROVED,
        )

    def test_campanha_de_texto_livre_nasce_marcada(self):
        campanha = CampaignService().create_campaign(
            account_id=str(self.account.id), name='Promo', message_content={'text': 'oi'},
        )
        assert campanha.audience_filters[MARCA] is True

    def test_campanha_com_template_nao_e_marcada(self):
        campanha = CampaignService().create_campaign(
            account_id=str(self.account.id), name='Promo', template_id=str(self.template.id),
        )
        assert MARCA not in campanha.audience_filters

    def test_filtros_que_o_dono_escolheu_continuam_valendo(self):
        campanha = CampaignService().create_campaign(
            account_id=str(self.account.id), name='Promo',
            message_content={'text': 'oi'}, audience_filters={'bairro': 'Centro'},
        )
        assert campanha.audience_filters['bairro'] == 'Centro'
        assert campanha.audience_filters[MARCA] is True

    def test_tirar_o_template_na_edicao_marca_a_campanha(self):
        campanha = CampaignService().create_campaign(
            account_id=str(self.account.id), name='Promo', template_id=str(self.template.id),
        )
        CampaignService().update_campaign(str(campanha.id), template_id=None)
        campanha.refresh_from_db()
        assert campanha.audience_filters[MARCA] is True
