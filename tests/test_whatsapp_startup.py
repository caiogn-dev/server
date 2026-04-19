from types import SimpleNamespace

from django.test import TestCase, override_settings

from apps.whatsapp.models import WhatsAppAccount
from apps.whatsapp.startup import ensure_default_whatsapp_account


@override_settings(
    DEFAULT_WHATSAPP_ACCOUNT_AUTO_CREATE=False,
    DEFAULT_WHATSAPP_ACCOUNT_ID='',
    DEFAULT_WHATSAPP_ACCOUNT_NAME='Pastita WhatsApp Business',
    DEFAULT_WHATSAPP_ACCOUNT_PHONE_NUMBER='',
    DEFAULT_WHATSAPP_ACCOUNT_DISPLAY_NUMBER='',
    DEFAULT_WHATSAPP_ACCOUNT_PHONE_NUMBER_ID='941408229062882',
    DEFAULT_WHATSAPP_ACCOUNT_WABA_ID='',
    DEFAULT_WHATSAPP_ACCOUNT_ACCESS_TOKEN='new-env-token',
    DEFAULT_WHATSAPP_ACCOUNT_OWNER_EMAIL='',
    DEFAULT_WHATSAPP_ACCOUNT_STATUS='active',
    WHATSAPP_WEBHOOK_VERIFY_TOKEN='verify-token',
)
class EnsureDefaultWhatsAppAccountStartupTests(TestCase):
    def test_syncs_existing_account_even_when_auto_create_is_disabled(self):
        account = WhatsAppAccount.objects.create(
            name='Existing Account',
            phone_number_id='941408229062882',
            waba_id='',
            phone_number='',
            display_phone_number='',
            status=WhatsAppAccount.AccountStatus.ACTIVE,
            webhook_verify_token='old-verify-token',
            access_token_encrypted='placeholder',
        )
        account.access_token = 'old-db-token'
        account.save(update_fields=['access_token_encrypted', 'token_version', 'updated_at'])

        ensure_default_whatsapp_account(SimpleNamespace(name='apps.whatsapp'))

        account.refresh_from_db()

        self.assertEqual(account.access_token, 'new-env-token')
        self.assertTrue(account.is_active)
        self.assertEqual(account.metadata.get('auto_created'), True)
