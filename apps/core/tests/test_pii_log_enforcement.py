"""
Garantia de LGPD: nenhum número de telefone nem credencial em claro deve aparecer
em registros de log nos serviços de maior tráfego.

Todos os testes usam SimpleTestCase (sem banco de dados) e unittest.mock para
isolar as camadas de infraestrutura.
"""
from unittest.mock import patch, MagicMock, call
from django.test import SimpleTestCase

from apps.core.pii import mask_phone


# ---------------------------------------------------------------------------
# apps/core/pii — cobertura complementar de edge cases de mask_phone
# ---------------------------------------------------------------------------

class MaskPhoneEdgeCaseTests(SimpleTestCase):
    def test_none_returns_empty(self):
        self.assertEqual(mask_phone(None), '')  # type: ignore[arg-type]

    def test_short_number_fully_masked(self):
        result = mask_phone('99999')
        self.assertNotIn('9', result.replace('*', ''))

    def test_full_br_number_shows_prefix_and_suffix_only(self):
        phone = '5511987654321'
        result = mask_phone(phone)
        self.assertTrue(result.startswith('55'), result)
        self.assertTrue(result.endswith('4321'), result)
        self.assertNotIn('987654', result)

    def test_formatted_phone_stripped(self):
        result = mask_phone('+55 (11) 98765-4321')
        self.assertNotIn('98765', result)

    def test_empty_string_returns_empty(self):
        self.assertEqual(mask_phone(''), '')


# ---------------------------------------------------------------------------
# apps/whatsapp/webhooks/views.py — verify_token não deve aparecer em log
# ---------------------------------------------------------------------------

class WebhookVerifyTokenLogTest(SimpleTestCase):
    """O token de verificação é uma credencial — jamais logar em claro."""

    def test_verify_token_not_in_log_on_failure(self):
        from apps.whatsapp.webhooks.views import WhatsAppWebhookView

        secret_token = 'super-secret-verify-token-12345'
        attacker_token = 'wrong-token-sent-by-attacker'

        with patch('apps.whatsapp.webhooks.views.settings') as mock_settings:
            mock_settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN = secret_token
            view = WhatsAppWebhookView()
            request = MagicMock()
            request.query_params = {
                'hub.mode': 'subscribe',
                'hub.verify_token': attacker_token,
                'hub.challenge': 'abc',
            }

            with self.assertLogs('apps.whatsapp.webhooks.views', level='WARNING') as cm:
                view.get(request)

        for line in cm.output:
            self.assertNotIn(secret_token, line,
                             f"Credencial verify_token vazou no log: {line}")
            self.assertNotIn(attacker_token, line,
                             f"Token do atacante vazou no log: {line}")


# ---------------------------------------------------------------------------
# apps/automation/services/session_manager.py — phone mascarado nos logs
# ---------------------------------------------------------------------------

class SessionManagerLogMaskingTests(SimpleTestCase):
    phone = '5521988776655'

    def _make_manager(self):
        from apps.automation.services.session_manager import SessionManager
        manager = SessionManager.__new__(SessionManager)
        manager.phone_number = self.phone
        manager.account = MagicMock()
        manager._session = None
        return manager

    def _mock_session(self):
        session = MagicMock()
        session.order_id = None  # evita chamada ao StoreOrder.objects.filter
        session.cart_data = {}
        return session

    def test_set_payment_pending_masks_phone(self):
        manager = self._make_manager()
        mock_session = self._mock_session()

        with patch.object(manager, 'get_or_create_session', return_value=mock_session):
            with self.assertLogs('apps.automation.services.session_manager', level='INFO') as cm:
                manager.set_payment_pending(pix_code='abc123', pix_qr_code='', payment_id='')

        for line in cm.output:
            self.assertNotIn(self.phone, line,
                             f"Telefone real vazou em set_payment_pending: {line}")

    def test_set_payment_pending_log_contains_masked(self):
        manager = self._make_manager()
        mock_session = self._mock_session()

        with patch.object(manager, 'get_or_create_session', return_value=mock_session):
            with self.assertLogs('apps.automation.services.session_manager', level='INFO') as cm:
                manager.set_payment_pending(pix_code='abc123')

        masked = mask_phone(self.phone)
        all_logs = ' '.join(cm.output)
        self.assertIn(masked, all_logs,
                      "Telefone mascarado deveria aparecer no log de set_payment_pending")

    def test_confirm_payment_masks_phone(self):
        manager = self._make_manager()
        mock_session = self._mock_session()

        with patch.object(manager, 'get_or_create_session', return_value=mock_session):
            with self.assertLogs('apps.automation.services.session_manager', level='INFO') as cm:
                manager.confirm_payment()

        for line in cm.output:
            self.assertNotIn(self.phone, line,
                             f"Telefone real vazou em confirm_payment: {line}")

    def test_complete_order_masks_phone(self):
        manager = self._make_manager()
        mock_session = self._mock_session()

        with patch.object(manager, 'get_or_create_session', return_value=mock_session):
            with self.assertLogs('apps.automation.services.session_manager', level='INFO') as cm:
                manager.complete_order()

        for line in cm.output:
            self.assertNotIn(self.phone, line,
                             f"Telefone real vazou em complete_order: {line}")


# ---------------------------------------------------------------------------
# apps/campaigns/services/campaign_service.py — phone do destinatário mascarado
# ---------------------------------------------------------------------------

class CampaignServiceLogMaskingTests(SimpleTestCase):
    phone = '5511977665544'

    def _run_batch(self, fail=False):
        """Executa process_campaign_batch com mocks, capturando logs."""
        from apps.campaigns.services.campaign_service import CampaignService

        recipient = MagicMock()
        recipient.phone_number = self.phone
        recipient.variables = {}
        recipient.whatsapp_message_id = None

        # Mock do queryset — list(qs[:n]) precisa de __getitem__ retornando lista
        mock_qs = MagicMock()
        mock_qs.__getitem__ = MagicMock(return_value=[recipient])

        campaign = MagicMock()
        campaign.template = MagicMock()
        campaign.template.name = 'test_tpl'
        campaign.template.language = 'pt_BR'
        campaign.message_content = 'Olá!'
        campaign.account.id = 'acc-uuid-123'
        campaign.messages_sent = 0
        campaign.messages_failed = 0

        svc = CampaignService.__new__(CampaignService)

        with patch('apps.campaigns.services.campaign_service.Campaign') as MockCampaign:
            MockCampaign.CampaignStatus.RUNNING = 'RUNNING'
            MockCampaign.CampaignStatus.COMPLETED = 'COMPLETED'
            campaign.status = 'RUNNING'
            MockCampaign.objects.get.return_value = campaign
            campaign.recipients.filter.return_value = mock_qs

            with patch('apps.campaigns.services.campaign_service.CampaignRecipient') as MockRec:
                MockRec.RecipientStatus.PENDING = 'PENDING'
                MockRec.RecipientStatus.SENT = 'SENT'
                MockRec.RecipientStatus.FAILED = 'FAILED'

                with patch('apps.campaigns.services.campaign_service.MessageService') as MockMS:
                    if fail:
                        MockMS.return_value.send_template_message.side_effect = \
                            Exception('API timeout')
                    else:
                        mock_msg = MagicMock()
                        mock_msg.whatsapp_message_id = 'wamid.TEST'
                        MockMS.return_value.send_template_message.return_value = mock_msg

                    with self.assertLogs(
                        'apps.campaigns.services.campaign_service', level='DEBUG'
                    ) as cm:
                        svc.process_campaign_batch(campaign_id='1', batch_size=10)

        return cm.output

    def test_success_log_does_not_expose_raw_phone(self):
        logs = self._run_batch(fail=False)
        for line in logs:
            self.assertNotIn(self.phone, line,
                             f"Telefone real vazou no log de sucesso de campanha: {line}")

    def test_error_log_does_not_expose_raw_phone(self):
        logs = self._run_batch(fail=True)
        for line in logs:
            self.assertNotIn(self.phone, line,
                             f"Telefone real vazou no log de erro de campanha: {line}")

    def test_success_log_contains_masked_phone(self):
        logs = self._run_batch(fail=False)
        masked = mask_phone(self.phone)
        all_logs = ' '.join(logs)
        self.assertIn(masked, all_logs,
                      "Telefone mascarado deveria aparecer no log de sucesso de campanha")
