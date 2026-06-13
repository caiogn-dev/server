"""Detecção dinâmica de impressoras: agent envia a lista no heartbeat e obedece o painel."""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StorePrintAgent

User = get_user_model()


class PrintAgentPrintersTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner-printers', email='owner-printers@test.com', password='x',
        )
        self.store = Store.objects.create(
            name='Loja Print', slug='loja-print', owner=self.owner, status='active',
        )
        raw, prefix, hashed = StorePrintAgent.generate_api_key()
        self.raw_key = raw
        self.agent = StorePrintAgent.objects.create(
            store=self.store, name='Caixa', slug='caixa-print',
            printer_name='EPSON TM-T20',
            api_key_prefix=prefix, api_key_hash=hashed,
        )

    def _heartbeat(self, payload):
        return self.client.post(
            '/api/v1/stores/print/agent/heartbeat/',
            payload,
            format='json',
            HTTP_X_PRINT_AGENT_KEY=self.raw_key,
        )

    def test_heartbeat_salva_lista_de_impressoras_detectadas(self):
        resp = self._heartbeat({
            'host_name': 'CAIXA-PC',
            'available_printers': ['EPSON TM-T20 Receipt', 'Microsoft Print to PDF'],
        })
        self.assertEqual(resp.status_code, 200, resp.content)
        self.agent.refresh_from_db()
        self.assertEqual(
            self.agent.available_printers,
            ['EPSON TM-T20 Receipt', 'Microsoft Print to PDF'],
        )

    def test_heartbeat_devolve_printer_name_configurado_no_painel(self):
        resp = self._heartbeat({'available_printers': []})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['printer_name'], 'EPSON TM-T20')

    def test_heartbeat_sem_lista_nao_apaga_a_anterior(self):
        self._heartbeat({'available_printers': ['Epson X']})
        self._heartbeat({'host_name': 'CAIXA-PC'})
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.available_printers, ['Epson X'])

    def test_lojista_ve_impressoras_no_serializer(self):
        self._heartbeat({'available_printers': ['Epson X', 'PDF']})
        self.client.force_authenticate(self.owner)
        resp = self.client.get(f'/api/v1/stores/stores/{self.store.slug}/print-agents/')
        self.assertEqual(resp.status_code, 200, resp.content)
        results = resp.data.get('results', resp.data)
        self.assertEqual(results[0]['available_printers'], ['Epson X', 'PDF'])
