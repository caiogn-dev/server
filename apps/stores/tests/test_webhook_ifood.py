"""Webhook do iFood (app centralizado) — /webhooks/v1/ifood/.

Regras da documentação (events/webhook-overview, webhook-signature, presence):
- X-IFood-Signature = HMAC-SHA256 hex do body BRUTO com o client_secret do app;
  assinatura inválida → 401 (o iFood testa isso na homologação);
- responder 202 em até 5 s; processar em fila;
- KEEPALIVE a cada 30 s: modo por app (202 = todos online) ou por merchant
  (devolver {"merchantIds": [...]} só com quem está online);
- entrega at-least-once, fora de ordem e sem ACK: idempotência pelo `id`.
"""
import hashlib
import hmac
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.stores.models import Store, StoreIfoodIntegration
from apps.stores.services import webhook_ifood

User = get_user_model()

CREDENCIAIS = {
    'IFOOD_CLIENT_ID': 'app-pedidos', 'IFOOD_CLIENT_SECRET': 'segredo-p',
    'IFOOD_ENTREGAS_CLIENT_ID': 'app-entregas', 'IFOOD_ENTREGAS_CLIENT_SECRET': 'segredo-e',
    'IFOOD_HOMOLOGACAO_CLIENT_ID': '', 'IFOOD_HOMOLOGACAO_CLIENT_SECRET': '',
}
MERCHANT = '4ea4f892-62f1-4037-a95f-1a903a55be70'
OUTRO = 'cad65e8f-6fc6-438a-b159-e64a902a6b9a'
URL = '/webhooks/v1/ifood/'


def _assinar(segredo: str, corpo: bytes) -> str:
    return hmac.new(segredo.encode('utf-8'), corpo, hashlib.sha256).hexdigest()


@override_settings(**CREDENCIAIS)
class AssinaturaTest(TestCase):
    def test_exemplo_da_documentacao(self):
        corpo = (b'{"code":"PLC","createdAt":"2023-02-20T18:19:03.20162269Z","fullCode":"PLACED",'
                 b'"id":"a38ba215-f949-4b2c-982a-0582a9d0c10e","merchantId":"cad65e8f-6fc6-438a-b159-'
                 b'e64a902a6b9a","orderId":"2c97e104-35ed-4c18-85d7-854a40b6b9e3"}')
        with override_settings(IFOOD_CLIENT_SECRET='dummysecret'):
            self.assertEqual(
                webhook_ifood.app_da_assinatura(
                    corpo, '6f9ed23a7b505a3b6907c5f6eb2ad1b056fbf35a643d365a9a072ed7aabca153'),
                'pedidos')

    def test_segredo_do_app_de_entregas(self):
        corpo = b'{"code":"KEEPALIVE"}'
        self.assertEqual(webhook_ifood.app_da_assinatura(corpo, _assinar('segredo-e', corpo)), 'entregas')

    def test_assinatura_errada_ou_ausente(self):
        corpo = b'{"code":"KEEPALIVE"}'
        self.assertIsNone(webhook_ifood.app_da_assinatura(corpo, 'invalid_signature_here'))
        self.assertIsNone(webhook_ifood.app_da_assinatura(corpo, ''))
        self.assertIsNone(webhook_ifood.app_da_assinatura(corpo, _assinar('outro', corpo)))


@override_settings(**CREDENCIAIS)
class EndpointTest(TestCase):
    def setUp(self):
        cache.clear()
        dono = User.objects.create_user(username='dona-webhook', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-webhook', owner=dono,
            store_type='food', status='active',
        )
        StoreIfoodIntegration.objects.create(store=self.store, merchant_id=MERCHANT, conectado=True)

    def _post(self, dados, segredo='segredo-p', assinatura=None):
        corpo = json.dumps(dados).encode() if not isinstance(dados, bytes) else dados
        return self.client.post(URL, data=corpo, content_type='application/json',
                                HTTP_X_IFOOD_SIGNATURE=assinatura or _assinar(segredo, corpo))

    def test_assinatura_invalida_e_401_e_nao_processa(self):
        with patch('apps.stores.tasks.evento_do_webhook_ifood.delay') as fila:
            r = self._post({'code': 'PLC', 'id': '1'}, assinatura='invalid_signature_here')
        self.assertEqual(r.status_code, 401)
        fila.assert_not_called()

    def test_keepalive_por_app_responde_202(self):
        r = self._post({'code': 'KEEPALIVE', 'fullCode': 'KEEPALIVE', 'id': 'k1'})
        self.assertEqual(r.status_code, 202)

    def test_keepalive_por_merchant_devolve_so_quem_esta_conectado(self):
        r = self._post({'code': 'KEEPALIVE', 'id': 'k2', 'merchantIds': [MERCHANT.upper(), OUTRO]})
        self.assertEqual(r.status_code, 202)
        self.assertEqual(r.json(), {'merchantIds': [MERCHANT.upper()]})

    def test_keepalive_do_app_de_entregas_nao_abre_loja(self):
        # App só de logística não é PDV: online por ele abriria a loja no iFood.
        r = self._post({'code': 'KEEPALIVE', 'id': 'k3', 'merchantIds': [MERCHANT]}, segredo='segredo-e')
        self.assertEqual(r.status_code, 202)
        self.assertEqual(r.json(), {'merchantIds': []})

    def test_evento_vai_para_a_fila_com_o_app(self):
        evento = {'code': 'PLC', 'fullCode': 'PLACED', 'id': 'e1', 'merchantId': MERCHANT, 'orderId': 'o1'}
        with patch('apps.stores.tasks.evento_do_webhook_ifood.delay') as fila:
            r = self._post(evento)
        self.assertEqual(r.status_code, 202)
        fila.assert_called_once_with('pedidos', evento)

    def test_lista_de_eventos_tambem_e_aceita(self):
        eventos = [{'code': 'CFM', 'id': 'e2', 'merchantId': MERCHANT},
                   {'code': 'CAN', 'id': 'e3', 'merchantId': MERCHANT}]
        with patch('apps.stores.tasks.evento_do_webhook_ifood.delay') as fila:
            r = self._post(eventos)
        self.assertEqual(r.status_code, 202)
        self.assertEqual(fila.call_count, 2)

    def test_body_que_nao_e_json_e_400(self):
        r = self._post(b'nao-e-json')
        self.assertEqual(r.status_code, 400)

    def test_get_nao_existe(self):
        self.assertEqual(self.client.get(URL).status_code, 405)


@override_settings(**CREDENCIAIS)
class ProcessarEventoTest(TestCase):
    def setUp(self):
        cache.clear()
        dono = User.objects.create_user(username='dona-evento', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-evento', owner=dono,
            store_type='food', status='active',
        )
        StoreIfoodIntegration.objects.create(store=self.store, merchant_id=MERCHANT, conectado=True)

    def test_evento_de_pedido_aplica_na_loja_do_merchant(self):
        evento = {'code': 'PLC', 'id': 'e10', 'merchantId': MERCHANT, 'orderId': 'o10'}
        with patch('apps.stores.services.pedidos_do_ifood.aplicar_evento', return_value=True) as aplicar:
            webhook_ifood.processar('pedidos', evento)
        aplicar.assert_called_once()
        self.assertEqual(aplicar.call_args.args[0], self.store)

    def test_evento_repetido_nao_aplica_de_novo(self):
        evento = {'code': 'PLC', 'id': 'e11', 'merchantId': MERCHANT, 'orderId': 'o11'}
        with patch('apps.stores.services.pedidos_do_ifood.aplicar_evento', return_value=True) as aplicar:
            webhook_ifood.processar('pedidos', evento)
            webhook_ifood.processar('pedidos', evento)
        self.assertEqual(aplicar.call_count, 1)

    def test_merchant_desconhecido_e_ignorado(self):
        evento = {'code': 'PLC', 'id': 'e12', 'merchantId': OUTRO, 'orderId': 'o12'}
        with patch('apps.stores.services.pedidos_do_ifood.aplicar_evento') as aplicar:
            webhook_ifood.processar('pedidos', evento)
        aplicar.assert_not_called()

    def test_evento_do_app_de_entregas_vai_para_a_entrega(self):
        evento = {'code': 'ADR', 'fullCode': 'ASSIGN_DRIVER', 'id': 'e13', 'merchantId': MERCHANT, 'orderId': 'd1'}
        with patch('apps.stores.services.entrega_ifood.aplicar_evento', return_value=True) as aplicar:
            webhook_ifood.processar('entregas', evento)
        aplicar.assert_called_once_with(evento)

    def test_falha_nao_marca_como_visto_para_tentar_de_novo(self):
        evento = {'code': 'PLC', 'id': 'e14', 'merchantId': MERCHANT, 'orderId': 'o14'}
        with patch('apps.stores.services.pedidos_do_ifood.aplicar_evento', side_effect=RuntimeError('x')):
            with self.assertRaises(RuntimeError):
                webhook_ifood.processar('pedidos', evento)
        with patch('apps.stores.services.pedidos_do_ifood.aplicar_evento', return_value=True) as aplicar:
            webhook_ifood.processar('pedidos', evento)
        aplicar.assert_called_once()
