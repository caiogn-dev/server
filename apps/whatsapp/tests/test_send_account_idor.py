"""Regressão de segurança: IDOR nas actions send_* do WhatsApp.

As actions send_text/template/image/... recebiam account_id do request e
mandavam mensagem SEM checar ownership — qualquer autenticado enviava
mensagens (gastando janela/credito) de QUALQUER conta WhatsApp pelo UUID.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()


class WhatsAppSendIDORTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='wa-owner', email='wa-o@t.com', password='x')
        self.attacker = User.objects.create_user(username='wa-att', email='wa-a@t.com', password='x')
        self.victim_account = WhatsAppAccount.objects.create(
            name='victim-wa', phone_number_id='pn-wv', waba_id='wa-wv',
            phone_number='+5511444441', display_phone_number='+5511444441',
            access_token_encrypted='x', webhook_verify_token='x', owner=self.owner,
        )

    def test_attacker_cannot_send_text_from_victim_account(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.post(
            '/api/v1/whatsapp/messages/send_text/',
            {'account_id': str(self.victim_account.id), 'to': '+5511999998888', 'text': 'oi'},
            format='json',
        )
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_attacker_cannot_send_image_from_victim_account(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.post(
            '/api/v1/whatsapp/messages/send_image/',
            {'account_id': str(self.victim_account.id), 'to': '+5511999998888',
             'image_url': 'https://example.com/y.jpg'},
            format='json',
        )
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_owner_passes_account_check(self):
        self.client.force_authenticate(self.owner)
        with patch('apps.whatsapp.api.views.MessageService') as MS, \
             patch('apps.whatsapp.api.views.MessageSerializer') as MSer:
            MS.return_value.send_text_message.return_value = object()
            MSer.return_value.data = {'ok': True}
            resp = self.client.post(
                '/api/v1/whatsapp/messages/send_text/',
                {'account_id': str(self.victim_account.id), 'to': '+5511999998888', 'text': 'oi'},
                format='json',
            )
        self.assertEqual(resp.status_code, 201, resp.content)
        MS.return_value.send_text_message.assert_called_once()
