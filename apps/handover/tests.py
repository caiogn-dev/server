"""Regressão de segurança: IDOR cross-tenant no Handover Protocol.

Antes do fix, `HandoverViewSet.get_conversation` fazia
`get_object_or_404(Conversation, pk=pk)` sem nenhum escopo de tenant — qualquer
usuário autenticado podia ler o status e TRANSFERIR (bot/human) o handover de
QUALQUER conversa só sabendo o UUID. A classe `IsStoreMember` existia mas nunca
era usada. Estes testes provam que um usuário sem acesso à conta recebe 404.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.conversations.models import Conversation
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()


class HandoverCrossTenantIDORTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', email='o@t.com', password='x')
        self.attacker = User.objects.create_user(username='attacker', email='a@t.com', password='x')

        self.account = WhatsAppAccount.objects.create(
            name='acc-owner', phone_number_id='pn-1', waba_id='wa-1',
            phone_number='+5511000001', display_phone_number='+5511000001',
            access_token_encrypted='x', webhook_verify_token='x',
            owner=self.owner,
        )
        self.conversation = Conversation.objects.create(
            account=self.account, phone_number='+5511999990001', contact_name='Cliente',
            wa_id='wa-c1', profile_picture_url='', agent_session_id='',
        )
        self.base = f'/api/v1/handover/conversations/{self.conversation.id}/handover'

    def test_owner_can_read_status(self):
        self.client.force_authenticate(self.owner)
        resp = self.client.get(f'{self.base}/status/')
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_attacker_cannot_read_status(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.get(f'{self.base}/status/')
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_attacker_cannot_transfer_to_human(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.post(f'{self.base}/human/', {}, format='json')
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_attacker_cannot_transfer_to_bot(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.post(f'{self.base}/bot/', {}, format='json')
        self.assertEqual(resp.status_code, 404, resp.content)
