"""Desconexão da ponte de coexistência (campo account_update).

Em 08/ago/2026 a Cê Saladas parou de enviar E receber por 2 dias e ninguém soube:
toda saída falhava com (#133010) Account not registered. A Meta AVISA quando a
ponte COEX cai — webhook `account_update` com event=PARTNER_REMOVED e um
`disconnection_info` dizendo o motivo — mas process_webhook descartava qualquer
change cujo field != 'messages', então em 3.083 webhooks gravados havia ZERO
ocorrência. Contrato:

- account_update é GRAVADO como WebhookEvent (não pode mais ser descartado);
- PARTNER_REMOVED marca a conta como inactive e carimba metadata para o painel;
- account_reconnected (religou) volta a conta para active e limpa o carimbo;
- payloads de outros campos continuam ignorados, e 'messages' segue intacto.
"""
from django.test import TestCase

from apps.whatsapp.models import WhatsAppAccount
from apps.whatsapp.models.webhook import WebhookEvent
from apps.whatsapp.services.webhook_service import WebhookService


def account_update_payload(event='PARTNER_REMOVED', waba_id='WABA_COEX', **extra):
    value = {
        'phone_number': '+55 63 9138-6719',
        'event': event,
        **extra,
    }
    return {
        'entry': [{
            'id': waba_id,
            'changes': [{'field': 'account_update', 'value': value}],
        }],
    }


class AccountUpdateDesconexaoTest(TestCase):
    def setUp(self):
        self.account = WhatsAppAccount.objects.create(
            name='Cê Saladas',
            phone_number_id='PH_COEX',
            waba_id='WABA_COEX',
            phone_number='+55 63 9138-6719',
            display_phone_number='556391386719',
            status=WhatsAppAccount.AccountStatus.ACTIVE,
        )
        self.service = WebhookService()

    def test_partner_removed_vira_webhook_event(self):
        """O aviso da Meta precisa sobreviver — antes era descartado na linha do field."""
        self.service.process_webhook(account_update_payload(), headers={})

        evento = WebhookEvent.objects.get(
            event_type=WebhookEvent.EventType.ACCOUNT_UPDATE,
        )
        self.assertEqual(evento.account_id, self.account.id)
        self.assertEqual(evento.payload['event'], 'PARTNER_REMOVED')

    def test_partner_removed_desativa_a_conta_e_carimba_o_motivo(self):
        """Sem isso o painel segue dizendo que está tudo certo enquanto nada sai."""
        self.service.process_webhook(
            account_update_payload(
                disconnection_info={'reason': 'DEVICE_CHANGED', 'source': 'CLIENT'},
            ),
            headers={},
        )

        self.account.refresh_from_db()
        self.assertEqual(self.account.status, WhatsAppAccount.AccountStatus.INACTIVE)
        coex = self.account.metadata['coex']
        self.assertFalse(coex['connected'])
        self.assertEqual(coex['reason'], 'DEVICE_CHANGED')
        self.assertIsNotNone(coex['disconnected_at'])

    def test_reconexao_devolve_a_conta_para_active(self):
        """Quando o dono refaz o QR no app, o sistema tem que voltar sozinho."""
        self.service.process_webhook(account_update_payload(), headers={})

        self.service.process_webhook(
            account_update_payload(event='PARTNER_ADDED'), headers={},
        )

        self.account.refresh_from_db()
        self.assertEqual(self.account.status, WhatsAppAccount.AccountStatus.ACTIVE)
        self.assertTrue(self.account.metadata['coex']['connected'])
        self.assertIsNone(self.account.metadata['coex']['reason'])

    def test_account_update_de_conta_desconhecida_nao_explode(self):
        """Webhook de conta que não é nossa não pode derrubar o processamento.

        Só conta como desconhecida quando NEM a WABA NEM o telefone batem —
        _resolve_account resolve por telefone de propósito (a WABA pode mudar).
        """
        eventos = self.service.process_webhook(
            account_update_payload(waba_id='WABA_DE_OUTRO', phone_number='+55 11 90000-0000'),
            headers={},
        )

        self.assertEqual(eventos, [])
        self.account.refresh_from_db()
        self.assertEqual(self.account.status, WhatsAppAccount.AccountStatus.ACTIVE)

    def test_campo_irrelevante_continua_ignorado(self):
        """A correção não pode virar uma porta aberta para todo campo do webhook."""
        eventos = self.service.process_webhook(
            {'entry': [{'id': 'WABA_COEX', 'changes': [
                {'field': 'business_capability_update', 'value': {'max_daily_conversation_per_phone': 1000}},
            ]}]},
            headers={},
        )

        self.assertEqual(eventos, [])
        self.assertEqual(WebhookEvent.objects.count(), 0)
