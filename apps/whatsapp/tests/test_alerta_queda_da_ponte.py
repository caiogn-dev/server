"""Quando a ponte COEX cai, alguém precisa SER AVISADO.

08-10/ago/2026: a Cê Saladas ficou 2 dias sem enviar nem receber. O sistema
sabia — todo envio voltava (#133010) — mas o único registro era `logger.error`,
e log ninguém lê em tempo real. O dono descobriu porque estranhou o silêncio.

Contrato:

- queda dispara alerta com o nome da loja e o motivo que a Meta mandou;
- reconexão avisa também (o dono precisa saber que voltou, senão fica refazendo
  o QR à toa);
- a Meta REENTREGA webhook: o mesmo evento não pode virar 5 alertas;
- e o alerta é o último passo, não o primeiro: se o canal de aviso falhar, o
  webhook tem que terminar de processar assim mesmo. Alerta quebrado não pode
  virar loja muda.
"""
from unittest.mock import patch

from django.test import TestCase

from apps.automation.models import CompanyProfile
from apps.stores.tests.factories import make_store
from apps.whatsapp.models import WhatsAppAccount
from apps.whatsapp.services.webhook_service import WebhookService


def vincular(account, store):
    """Liga a conta de WhatsApp à loja.

    Loja e conta criam CADA UMA o seu CompanyProfile por signal, e o profile é
    1:1 com AS DUAS pontas (`store` e `account` são unique). Em produção sobra
    um profile só, com os dois campos preenchidos — aqui é preciso descartar o
    órfão antes de juntar, senão bate na unique.
    """
    CompanyProfile.objects.filter(store=store).exclude(account=account).delete()
    perfil = CompanyProfile.objects.get(account=account)
    perfil.store = store
    perfil.save(update_fields=['store'])
    return perfil


def payload(event='PARTNER_REMOVED', **extra):
    return {
        'entry': [{
            'id': 'WABA_ALERTA',
            'changes': [{'field': 'account_update', 'value': {
                'phone_number': '+55 63 9138-6719',
                'event': event,
                **extra,
            }}],
        }],
    }


class AlertaQuedaDaPonteTest(TestCase):
    def setUp(self):
        self.account = WhatsAppAccount.objects.create(
            name='Cê Saladas', phone_number_id='PH_ALERTA', waba_id='WABA_ALERTA',
            phone_number='+55 63 9138-6719', display_phone_number='556391386719',
            status=WhatsAppAccount.AccountStatus.ACTIVE,
        )
        self.store = make_store(name='Cê Saladas')
        vincular(self.account, self.store)
        self.service = WebhookService()

    def test_queda_dispara_alerta_com_loja_e_motivo(self):
        with patch('apps.whatsapp.services.alerta_coex.enviar_alerta') as enviar:
            self.service.process_webhook(
                payload(disconnection_info={'reason': 'DEVICE_CHANGED', 'source': 'CLIENT'}),
                headers={},
            )

        enviar.assert_called_once()
        kwargs = enviar.call_args.kwargs
        self.assertEqual(kwargs['account'].id, self.account.id)
        self.assertTrue(kwargs['caiu'])
        self.assertEqual(kwargs['reason'], 'DEVICE_CHANGED')

    def test_reconexao_avisa_que_voltou(self):
        self.service.process_webhook(payload(), headers={})

        with patch('apps.whatsapp.services.alerta_coex.enviar_alerta') as enviar:
            self.service.process_webhook(payload(event='PARTNER_ADDED'), headers={})

        enviar.assert_called_once()
        self.assertFalse(enviar.call_args.kwargs['caiu'])

    def test_webhook_repetido_nao_alerta_de_novo(self):
        """A Meta reentrega o mesmo evento — 5 alertas iguais treinam a ignorar."""
        self.service.process_webhook(payload(), headers={})

        with patch('apps.whatsapp.services.alerta_coex.enviar_alerta') as enviar:
            self.service.process_webhook(payload(), headers={})
            self.service.process_webhook(payload(), headers={})

        enviar.assert_not_called()

    def test_alerta_que_explode_nao_derruba_o_webhook(self):
        """Canal de aviso quebrado não pode custar o processamento da mensagem."""
        with patch(
            'apps.whatsapp.services.alerta_coex.enviar_alerta',
            side_effect=RuntimeError('Resend fora do ar'),
        ):
            eventos = self.service.process_webhook(payload(), headers={})

        self.assertEqual(len(eventos), 1)
        self.account.refresh_from_db()
        self.assertEqual(self.account.status, WhatsAppAccount.AccountStatus.INACTIVE)


class DestinatariosDoAlertaTest(TestCase):
    """Para quem o alerta vai."""

    def setUp(self):
        self.account = WhatsAppAccount.objects.create(
            name='Cê Saladas', phone_number_id='PH_DEST', waba_id='WABA_DEST',
        )
        self.store = make_store(name='Cê Saladas')
        self.store.owner.email = 'dono@exemplo.com'
        self.store.owner.save(update_fields=['email'])
        vincular(self.account, self.store)

    def test_email_do_dono_da_loja_entra_na_lista(self):
        from apps.whatsapp.services.alerta_coex import destinatarios

        self.assertIn('dono@exemplo.com', destinatarios(self.account))

    def test_conta_sem_loja_nao_explode(self):
        from apps.whatsapp.services.alerta_coex import destinatarios

        orfa = WhatsAppAccount.objects.create(
            name='Órfã', phone_number_id='PH_ORFA', waba_id='WABA_ORFA',
        )
        self.assertEqual(destinatarios(orfa), [])
