"""PATCH /campaigns/{id}/ não aceita template de outra conta WhatsApp.

O create já recusa (CampaignService.create_campaign), mas o PATCH passava pelo
campo `template` do ModelSerializer, com queryset global: o dono da conta A
apontava a campanha para o template da conta B e o envio usava o nome/idioma
do template do vizinho (IDOR cross-tenant de escrita).
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.campaigns.models import Campaign
from apps.whatsapp.models import MessageTemplate, WhatsAppAccount

User = get_user_model()


def _conta(dono, sufixo):
    return WhatsAppAccount.objects.create(
        name=f'Conta {sufixo}', phone_number_id=f'pn-{sufixo}', waba_id=f'wa-{sufixo}',
        phone_number=f'+551134{sufixo}', display_phone_number=f'+551134{sufixo}',
        access_token_encrypted='x', webhook_verify_token='x', owner=dono,
    )


def _template(conta, sufixo):
    return MessageTemplate.objects.create(
        account=conta, template_id=f'tpl-{sufixo}', name=f'promo_{sufixo}',
        category=MessageTemplate.TemplateCategory.MARKETING,
        status=MessageTemplate.TemplateStatus.APPROVED,
    )


class PatchTemplateDeOutraContaTest(APITestCase):
    def setUp(self):
        self.dono_a = User.objects.create_user(username='dono-a-tpl', password='x')
        self.dono_b = User.objects.create_user(username='dono-b-tpl', password='x')
        self.conta_a = _conta(self.dono_a, '11111')
        self.conta_b = _conta(self.dono_b, '22222')
        self.tpl_a = _template(self.conta_a, 'a')
        self.tpl_b = _template(self.conta_b, 'b')
        self.campanha = Campaign.objects.create(
            account=self.conta_a, name='Promo', is_active=True,
            template=self.tpl_a, message_content={},
        )
        self.client.force_authenticate(self.dono_a)
        self.url = f'/api/v1/campaigns/campaigns/{self.campanha.id}/'

    def test_patch_com_template_de_outra_conta_e_recusado(self):
        resp = self.client.patch(self.url, {'template': str(self.tpl_b.id)}, format='json')
        self.assertEqual(resp.status_code, 400, resp.content)
        self.campanha.refresh_from_db()
        self.assertEqual(self.campanha.template_id, self.tpl_a.id)

    def test_patch_com_template_da_mesma_conta_continua_valendo(self):
        outro = _template(self.conta_a, 'a2')
        resp = self.client.patch(self.url, {'template': str(outro.id)}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.campanha.refresh_from_db()
        self.assertEqual(self.campanha.template_id, outro.id)
