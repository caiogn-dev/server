"""Fiscal: emissão de NFC-e via provider plugável (Focus mockado)."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.fiscal.models import FiscalDocument
from apps.fiscal.providers.base import EmitResult, FiscalNotConfigured
from apps.fiscal.services import build_nfce_payload, get_fiscal_config
from apps.stores.models import Store, StoreCategory, StoreOrder, StoreOrderItem, StoreProduct

User = get_user_model()

FISCAL_CFG = {
    'provider': 'focus',
    'ambiente': 'homologacao',
    'focus_token': 'tok-teste',
    'cnpj': '12.345.678/0001-90',
    'serie': '1',
    'habilitado': True,
}


class EmitNfceTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner-fiscal', email='owner-fiscal@test.com', password='x',
        )
        self.store = Store.objects.create(
            name='Loja Fiscal', slug='loja-fiscal', owner=self.owner, status='active',
            metadata={'fiscal': dict(FISCAL_CFG)},
        )
        category = StoreCategory.objects.create(store=self.store, name='Geral', slug='geral')
        self.product = StoreProduct.objects.create(
            store=self.store, name='Marmita', price=20, track_stock=False,
            category=category, sku='MAR1',
        )
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='Cliente Balcão', customer_phone='00000000000',
            customer_email='x@local.invalid', subtotal=40, total=40,
            payment_method='pix', delivery_method='pickup',
            status='pending', payment_status='paid',
        )
        StoreOrderItem.objects.create(
            order=self.order, product=self.product, product_name='Marmita',
            sku='MAR1', unit_price=20, quantity=2, subtotal=40,
        )
        self.client.force_authenticate(self.owner)
        self.url = f'/api/v1/stores/{self.store.slug}/orders/{self.order.id}/emit_nfce/'

    def test_payload_tem_itens_pagamento_e_cnpj_limpo(self):
        payload = build_nfce_payload(self.order, get_fiscal_config(self.store))
        self.assertEqual(payload['cnpj_emitente'], '12345678000190')
        self.assertEqual(len(payload['itens']), 1)
        item = payload['itens'][0]
        self.assertEqual(item['quantidade_comercial'], 2.0)
        self.assertEqual(item['valor_unitario_comercial'], 20.0)
        self.assertEqual(item['codigo_ncm'], '21069090')
        self.assertEqual(payload['formas_pagamento'][0], {
            'forma_pagamento': '17', 'valor_pagamento': 40.0,
        })
        # consumidor não identificado → sem destinatário
        self.assertNotIn('nome_destinatario', payload)

    @patch('apps.fiscal.services.FocusProvider.emit_nfce')
    def test_emitir_autorizada_cria_documento(self, mock_emit):
        mock_emit.return_value = EmitResult(
            status='authorized', chave_acesso='1' * 44, numero='123', serie='1',
            danfe_url='https://focus/danfe.pdf', qrcode_url='https://sefaz/qr',
            raw={'status': 'autorizado'},
        )
        resp = self.client.post(self.url, {}, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data['status'], 'authorized')
        doc = FiscalDocument.objects.get(order=self.order)
        self.assertEqual(doc.chave_acesso, '1' * 44)
        self.assertEqual(doc.ref, f'nfce-{self.order.id}')
        # idempotência: segunda chamada devolve o mesmo doc sem re-emitir
        resp2 = self.client.post(self.url, {}, format='json')
        self.assertEqual(FiscalDocument.objects.filter(order=self.order).count(), 1)
        self.assertEqual(resp2.data['id'], str(doc.id))
        mock_emit.assert_called_once()

    def test_loja_sem_config_fiscal_da_400(self):
        self.store.metadata = {}
        self.store.save(update_fields=['metadata'])
        resp = self.client.post(self.url, {}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('config fiscal', resp.data['error'])
        self.assertFalse(FiscalDocument.objects.exists())

    def test_provider_sefaz_ainda_nao_ativado_da_400_claro(self):
        self.store.metadata = {'fiscal': {**FISCAL_CFG, 'provider': 'sefaz'}}
        self.store.save(update_fields=['metadata'])
        resp = self.client.post(self.url, {}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('certificado A1', resp.data['error'])
        self.assertFalse(FiscalDocument.objects.exists())

    def test_emissao_desligada_na_loja_bloqueia_o_endpoint(self):
        """A chave 'Emitir nota fiscal nesta loja' tem que valer: config
        preenchida mas desligada não pode emitir nada."""
        self.store.metadata = {'fiscal': {**FISCAL_CFG, 'habilitado': False}}
        self.store.save(update_fields=['metadata'])
        resp = self.client.post(self.url, {}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(FiscalDocument.objects.exists())

    def test_cliente_vinculado_vai_como_destinatario(self):
        self.order.customer_name = 'João da Silva'
        self.order.save(update_fields=['customer_name'])
        payload = build_nfce_payload(self.order, get_fiscal_config(self.store))
        self.assertEqual(payload['nome_destinatario'], 'João da Silva')
