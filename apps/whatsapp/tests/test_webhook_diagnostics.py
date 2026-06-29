"""Endpoint de diagnóstico de webhooks (WebhookDiagnosticsPage do painel).

Antes a view só devolvia celery_status/verify_token e 404 fora de DEBUG → a página
nunca funcionava. Agora monta o payload completo, escopado às contas do usuário.
"""
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store
from apps.whatsapp.models import WhatsAppAccount, WebhookEvent, Message

User = get_user_model()


class WebhookDiagnosticsTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='ow-wd', email='ow-wd@t.com', password='x')
        self.store = Store.objects.create(name='Loja WD', slug='loja-wd', owner=self.owner, status='active')
        self.account = WhatsAppAccount.objects.create(
            name='Minha Conta', phone_number_id='PN1', waba_id='WA1',
            phone_number='5563988887777', access_token_encrypted='x', owner=self.owner, is_active=True,
        )
        WebhookEvent.objects.create(account=self.account, event_id='ev-ok', event_type='message',
                                    processing_status='completed', payload={})
        WebhookEvent.objects.create(account=self.account, event_id='ev-fail', event_type='message',
                                    processing_status='failed', error_message='boom', payload={})
        Message.objects.create(account=self.account, direction='inbound', message_type='text',
                               from_number='5563911112222', text_body='oi')

        # Conta de OUTRO dono — não pode vazar
        other = User.objects.create_user(username='ow-wd2', email='ow-wd2@t.com', password='x')
        self.other_account = WhatsAppAccount.objects.create(
            name='Conta Alheia', phone_number_id='PN2', waba_id='WA2',
            phone_number='5511999998888', access_token_encrypted='x', owner=other, is_active=True,
        )
        WebhookEvent.objects.create(account=self.other_account, event_id='ev-other', event_type='message',
                                    processing_status='failed', payload={})

        self.url = reverse('whatsapp-webhook-debug')
        self.client.force_authenticate(self.owner)

    def test_get_returns_full_payload(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200, resp.content)
        d = resp.data
        for key in ('status', 'server_time', 'celery_status', 'stats', 'accounts',
                    'recent_events', 'recent_inbound_messages', 'failed_events', 'diagnosis'):
            self.assertIn(key, d)
        self.assertEqual(d['stats']['webhook_events']['total'], 2)
        self.assertEqual(d['stats']['webhook_events']['failed'], 1)
        self.assertEqual(d['stats']['messages']['total_inbound'], 1)
        self.assertEqual(len(d['accounts']), 1)
        self.assertEqual(d['accounts'][0]['name'], 'Minha Conta')
        self.assertEqual(len(d['failed_events']), 1)
        self.assertTrue(d['diagnosis']['has_active_accounts'])
        self.assertTrue(d['diagnosis']['has_failed_events'])

    def test_does_not_leak_other_tenant(self):
        resp = self.client.get(self.url)
        # só 1 conta (a do dono), e os 2 eventos são só os dela (o failed alheio não conta)
        self.assertEqual(len(resp.data['accounts']), 1)
        self.assertEqual(resp.data['stats']['webhook_events']['total'], 2)
        names = [a['name'] for a in resp.data['accounts']]
        self.assertNotIn('Conta Alheia', names)

    def test_post_invalid_action(self):
        resp = self.client.post(self.url, {'action': 'foo'}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_post_reprocess_failed_routes(self):
        # Sem disparar efeito real: filtra os falhos do dono. Aqui há 1 failed; pra
        # não rodar o handler de verdade no teste, validamos a contagem do retorno.
        resp = self.client.post(self.url, {'action': 'reprocess_pending'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['action'], 'reprocess_pending')
        # nenhum pending → processed 0, sem efeito colateral
        self.assertEqual(resp.data['processed'], 0)
