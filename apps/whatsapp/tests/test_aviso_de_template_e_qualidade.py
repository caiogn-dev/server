"""A Meta avisa quando um template é aprovado/recusado e quando o número perde qualidade.

19/09: o app não assinava `message_template_status_update` nem
`phone_number_quality_update`, e o webhook descartava qualquer campo que não
fosse `messages`/eco/`account_update`. O painel mostrava template "pendente"
para sempre, e uma queda de qualidade do número (que corta o limite de envio)
passava calada — justo quando 16 avisos em 30 dias foram barrados por
"saúde do ecossistema" (131049).
"""
from django.test import TestCase

from apps.whatsapp.models import MessageTemplate, WhatsAppAccount
from apps.whatsapp.models.webhook import WebhookEvent
from apps.whatsapp.services.webhook_service import WebhookService

WABA = 'WABA_AVISOS'


def _payload(field, value):
    return {'entry': [{'id': WABA, 'changes': [{'field': field, 'value': value}]}]}


class AvisoDeTemplateTest(TestCase):
    def setUp(self):
        self.account = WhatsAppAccount.objects.create(
            name='Loja', phone_number_id='PH_AV', waba_id=WABA,
            phone_number='+5563900000099', display_phone_number='5563900000099',
            status=WhatsAppAccount.AccountStatus.ACTIVE,
        )
        self.template = MessageTemplate.objects.create(
            account=self.account, template_id='777', name='status_do_pedido',
            language='pt_BR', category='utility',
        )
        self.service = WebhookService()

    def _aviso(self, event, **extra):
        self.service.process_webhook(_payload('message_template_status_update', {
            'event': event, 'message_template_id': 777,
            'message_template_name': 'status_do_pedido',
            'message_template_language': 'pt_BR', **extra,
        }), headers={})
        self.template.refresh_from_db()

    def test_aprovado_vira_aprovado(self):
        self._aviso('APPROVED')

        self.assertEqual(self.template.status, MessageTemplate.TemplateStatus.APPROVED)
        self.assertTrue(self.template.is_active)

    def test_recusado_vira_recusado(self):
        self._aviso('REJECTED', reason='INVALID_FORMAT')

        self.assertEqual(self.template.status, MessageTemplate.TemplateStatus.REJECTED)

    def test_pausado_ou_desativado_sai_de_uso(self):
        self._aviso('PAUSED')

        self.assertFalse(self.template.is_active)

    def test_aviso_fica_gravado(self):
        self._aviso('APPROVED')

        evento = WebhookEvent.objects.get(account=self.account)
        self.assertEqual(evento.payload['field'], 'message_template_status_update')
        self.assertEqual(evento.payload['event'], 'APPROVED')

    def test_template_que_nao_conhecemos_nao_quebra(self):
        self.service.process_webhook(_payload('message_template_status_update', {
            'event': 'APPROVED', 'message_template_id': 999,
            'message_template_name': 'outro', 'message_template_language': 'pt_BR',
        }), headers={})

        self.template.refresh_from_db()
        self.assertEqual(self.template.status, MessageTemplate.TemplateStatus.PENDING)


class AvisoDeQualidadeTest(TestCase):
    def setUp(self):
        self.account = WhatsAppAccount.objects.create(
            name='Loja', phone_number_id='PH_Q', waba_id=WABA,
            phone_number='+5563900000098', display_phone_number='5563900000098',
            status=WhatsAppAccount.AccountStatus.ACTIVE,
        )

    def test_queda_de_qualidade_fica_na_conta(self):
        WebhookService().process_webhook(_payload('phone_number_quality_update', {
            'display_phone_number': '5563900000098', 'event': 'DOWNGRADE',
            'current_limit': 'TIER_250',
        }), headers={})

        self.account.refresh_from_db()
        qualidade = self.account.metadata['qualidade']
        self.assertEqual(qualidade['evento'], 'DOWNGRADE')
        self.assertEqual(qualidade['limite'], 'TIER_250')
        self.assertTrue(qualidade['em'])
        self.assertEqual(self.account.status, WhatsAppAccount.AccountStatus.ACTIVE)

    def test_campo_desconhecido_segue_ignorado(self):
        WebhookService().process_webhook(_payload('algo_novo', {'x': 1}), headers={})

        self.assertFalse(WebhookEvent.objects.exists())
