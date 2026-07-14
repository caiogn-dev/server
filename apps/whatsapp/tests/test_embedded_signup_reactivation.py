"""Embedded Signup deve REATIVAR conta existente do mesmo número.

O onboard usa get_or_create por phone_number_id e seta status=ACTIVE, mas não
mexia em is_active. O roteamento de mensagens recebidas (webhook_service)
filtra is_active=True — reconectar um número cuja conta antiga estava
desativada deixava as mensagens sendo descartadas mesmo com onboarding OK.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.whatsapp.models import WhatsAppAccount
from apps.whatsapp.services.embedded_signup_service import EmbeddedSignupService

User = get_user_model()


class EmbeddedSignupReactivationTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='dono', email='dono@loja.com', password='x'
        )

    def _onboard(self):
        svc = EmbeddedSignupService()
        with patch.object(svc, 'exchange_code', return_value='tok-123'), \
             patch.object(svc, 'fetch_phone', return_value={
                 'display_phone_number': '+55 63 99117-2166',
                 'verified_name': 'Pastita',
             }), \
             patch.object(svc, 'subscribe_app', return_value={'success': True}):
            return svc.onboard(
                code='code-abc', waba_id='WABA1', phone_number_id='PHONE1',
                owner=self.owner,
            )

    def test_onboard_reactivates_existing_inactive_account(self):
        WhatsAppAccount.objects.create(
            name='Pastita', phone_number_id='PHONE1', waba_id='WABA1',
            is_active=False, status=WhatsAppAccount.AccountStatus.INACTIVE,
        )

        acc = self._onboard()

        acc.refresh_from_db()
        self.assertTrue(acc.is_active, 'Reconexão deve reativar a conta')
        self.assertEqual(acc.status, WhatsAppAccount.AccountStatus.ACTIVE)
        self.assertEqual(WhatsAppAccount.objects.filter(phone_number_id='PHONE1').count(), 1)

    def test_onboard_creates_active_account(self):
        acc = self._onboard()
        acc.refresh_from_db()
        self.assertTrue(acc.is_active)
        self.assertEqual(acc.status, WhatsAppAccount.AccountStatus.ACTIVE)
