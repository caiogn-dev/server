"""D1 pela rota REST real: PATCH em /campaigns/{id}/ também recalcula a marca.

`CampaignViewSet` é um ModelViewSet padrão; sem sobrescrever `perform_update`,
o `serializer.save()` grava direto no model e NUNCA passa por
`CampaignService.update_campaign` — a marca `somente_janela_aberta` ficava
congelada no valor de quando a campanha nasceu, e o painel edita campanha por
essa rota (PATCH/PUT), não chamando o service em Python.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.campaigns.models import Campaign
from apps.campaigns.services.janela import MARCA
from apps.whatsapp.models import MessageTemplate, WhatsAppAccount

User = get_user_model()


class MarcaRecalculaNoPatchDaApiTest(APITestCase):
    def setUp(self):
        self.dono = User.objects.create_user(username='dona-patch', password='x')
        self.account = WhatsAppAccount.objects.create(
            name='Conta Patch', phone_number_id='pn-patch', waba_id='wa-patch',
            phone_number='+5511344440', display_phone_number='+5511344440',
            access_token_encrypted='x', webhook_verify_token='x', owner=self.dono,
        )
        self.template = MessageTemplate.objects.create(
            account=self.account, template_id='tpl-patch', name='promo',
            category=MessageTemplate.TemplateCategory.MARKETING,
            status=MessageTemplate.TemplateStatus.APPROVED,
        )
        self.client.force_authenticate(self.dono)

    def _url(self, campanha):
        return f'/api/v1/campaigns/campaigns/{campanha.id}/'

    def test_patch_tirando_o_template_marca_a_campanha(self):
        campanha = Campaign.objects.create(
            account=self.account, name='Promo', is_active=True,
            template=self.template, message_content={},
        )
        resp = self.client.patch(self._url(campanha), {'template': None}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        campanha.refresh_from_db()
        self.assertIsNone(campanha.template_id)
        self.assertIs(campanha.audience_filters[MARCA], True)
        self.assertIs(resp.data['audience_filters'][MARCA], True)

    def test_patch_pondo_template_tira_a_marca(self):
        campanha = Campaign.objects.create(
            account=self.account, name='Promo', is_active=True,
            message_content={'text': 'oi'}, audience_filters={MARCA: True},
        )
        resp = self.client.patch(
            self._url(campanha), {'template': str(self.template.id)}, format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        campanha.refresh_from_db()
        self.assertEqual(str(campanha.template_id), str(self.template.id))
        self.assertNotIn(MARCA, campanha.audience_filters)
        self.assertNotIn(MARCA, resp.data['audience_filters'])

    def test_patch_que_so_muda_o_nome_nao_mexe_na_marca(self):
        campanha = Campaign.objects.create(
            account=self.account, name='Promo', is_active=True,
            message_content={'text': 'oi'}, audience_filters={MARCA: True, 'bairro': 'Centro'},
        )
        resp = self.client.patch(self._url(campanha), {'name': 'Promo 2'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        campanha.refresh_from_db()
        self.assertEqual(campanha.name, 'Promo 2')
        self.assertIs(campanha.audience_filters[MARCA], True)
        self.assertEqual(campanha.audience_filters['bairro'], 'Centro')
