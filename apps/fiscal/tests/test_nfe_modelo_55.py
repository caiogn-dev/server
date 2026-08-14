"""Fiscal: NF-e (modelo 55) para venda a empresa.

NFC-e (modelo 65) serve consumidor final no balcão: aceita "consumidor não
identificado" e não pede endereço. NF-e é outro documento — o destinatário
precisa existir por inteiro (CNPJ, razão social, endereço com município e UF)
e a SEFAZ recusa se faltar campo.

Por isso a regra aqui é: descobrir o que falta ANTES de emitir e dizer o que
é, em vez de mandar pra SEFAZ e traduzir código de rejeição depois.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.fiscal.models import FiscalDocument
from apps.fiscal.providers.base import EmitResult, FiscalNotConfigured
from apps.fiscal.services import build_nfe_payload, get_fiscal_config
from apps.stores.models import Store, StoreCategory, StoreOrder, StoreOrderItem, StoreProduct

User = get_user_model()

FISCAL_CFG = {
    'provider': 'focus',
    'ambiente': 'homologacao',
    'focus_token': 'tok-teste',
    'cnpj': '11444777000161',
    'serie': '1',
    'habilitado': True,
    'uf': 'TO',
}

CNPJ_CLIENTE = '11222333000181'
CPF_CLIENTE = '52998224725'

ENDERECO = {
    'street': 'Quadra 501 Sul Avenida Joaquim Teotônio Segurado',
    'number': '403',
    'neighborhood': 'Plano Diretor Sul',
    'city': 'Palmas',
    'state': 'TO',
    'zip_code': '77016002',
    'complement': 'Sala 2',
}


class NfePayloadTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner-nfe', email='owner-nfe@test.com', password='x',
        )
        self.store = Store.objects.create(
            name='Loja NFe', slug='loja-nfe', owner=self.owner, status='active',
            metadata={'fiscal': dict(FISCAL_CFG)},
        )
        category = StoreCategory.objects.create(store=self.store, name='Geral', slug='geral')
        self.product = StoreProduct.objects.create(
            store=self.store, name='Coffee break', price=500, track_stock=False,
            category=category, sku='CB1',
        )
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='Construtora Alfa LTDA',
            customer_phone='63999990000', customer_email='financeiro@alfa.com',
            subtotal=Decimal('500.00'), delivery_fee=Decimal('0.00'), total=Decimal('500.00'),
            payment_method='pix', delivery_method='delivery',
            status='pending', payment_status='paid',
            delivery_address=dict(ENDERECO),
            metadata={'cpf_nota': CNPJ_CLIENTE},
        )
        StoreOrderItem.objects.create(
            order=self.order, product=self.product, product_name='Coffee break',
            sku='CB1', unit_price=500, quantity=1, subtotal=500,
        )

    def _payload(self):
        return build_nfe_payload(self.order, get_fiscal_config(self.store))

    def test_destinatario_completo_vai_no_payload(self):
        payload = self._payload()
        self.assertEqual(payload['cnpj_destinatario'], CNPJ_CLIENTE)
        self.assertEqual(payload['nome_destinatario'], 'Construtora Alfa LTDA')
        self.assertEqual(payload['logradouro_destinatario'], ENDERECO['street'])
        self.assertEqual(payload['numero_destinatario'], '403')
        self.assertEqual(payload['bairro_destinatario'], 'Plano Diretor Sul')
        self.assertEqual(payload['municipio_destinatario'], 'Palmas')
        self.assertEqual(payload['uf_destinatario'], 'TO')
        self.assertEqual(payload['cep_destinatario'], '77016002')

    def test_venda_no_estado_usa_cfop_5102(self):
        self.assertEqual(self._payload()['itens'][0]['cfop'], '5102')

    def test_venda_para_fora_do_estado_usa_cfop_6102(self):
        """CFOP errado é rejeição na SEFAZ — a diferença é só o estado do
        destinatário, então o sistema decide, não o operador."""
        self.order.delivery_address = {**ENDERECO, 'state': 'GO', 'city': 'Goiânia'}
        self.order.save(update_fields=['delivery_address'])
        payload = self._payload()
        self.assertEqual(payload['itens'][0]['cfop'], '6102')
        self.assertEqual(payload['local_destino'], 2)

    def test_sem_endereco_diz_o_que_falta_em_vez_de_emitir(self):
        self.order.delivery_address = {}
        self.order.save(update_fields=['delivery_address'])
        with self.assertRaises(FiscalNotConfigured) as ctx:
            self._payload()
        mensagem = str(ctx.exception)
        self.assertIn('endereço', mensagem.lower())

    def test_sem_documento_do_destinatario_recusa(self):
        """NF-e não tem 'consumidor não identificado' — sem CNPJ/CPF não existe
        nota modelo 55."""
        self.order.metadata = {}
        self.order.save(update_fields=['metadata'])
        with self.assertRaises(FiscalNotConfigured):
            self._payload()

    def test_cpf_tambem_serve_de_destinatario(self):
        self.order.metadata = {'cpf_nota': CPF_CLIENTE}
        self.order.save(update_fields=['metadata'])
        payload = self._payload()
        self.assertEqual(payload['cpf_destinatario'], CPF_CLIENTE)
        self.assertNotIn('cnpj_destinatario', payload)

    def test_inscricao_estadual_do_cliente_entra_quando_informada(self):
        self.order.metadata = {'cpf_nota': CNPJ_CLIENTE, 'ie_nota': '29.123.456-7'}
        self.order.save(update_fields=['metadata'])
        payload = self._payload()
        self.assertEqual(payload['inscricao_estadual_destinatario'], '291234567')
        self.assertEqual(payload['indicador_inscricao_estadual_destinatario'], '1')

    def test_sem_ie_o_destinatario_e_nao_contribuinte(self):
        self.assertEqual(self._payload()['indicador_inscricao_estadual_destinatario'], '9')

    def test_frete_e_desconto_continuam_fechando_a_conta(self):
        self.order.delivery_fee = Decimal('30.00')
        self.order.discount = Decimal('20.00')
        self.order.total = Decimal('510.00')
        self.order.save(update_fields=['delivery_fee', 'discount', 'total'])
        payload = self._payload()
        soma = sum(i['valor_bruto'] for i in payload['itens'])
        pago = sum(p['valor_pagamento'] for p in payload['formas_pagamento'])
        self.assertAlmostEqual(soma + payload['frete'] - payload['valor_desconto'], pago, places=2)


class EmitirNfePelaApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner-nfe-api', email='owner-nfe-api@test.com', password='x',
        )
        self.store = Store.objects.create(
            name='Loja NFe API', slug='loja-nfe-api', owner=self.owner, status='active',
            metadata={'fiscal': dict(FISCAL_CFG)},
        )
        category = StoreCategory.objects.create(store=self.store, name='Geral', slug='geral')
        product = StoreProduct.objects.create(
            store=self.store, name='Coffee break', price=500, track_stock=False,
            category=category, sku='CB1',
        )
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='Construtora Alfa LTDA',
            customer_phone='63999990000', customer_email='financeiro@alfa.com',
            subtotal=Decimal('500.00'), total=Decimal('500.00'),
            payment_method='pix', delivery_method='delivery',
            status='pending', payment_status='paid',
            delivery_address=dict(ENDERECO),
            metadata={'cpf_nota': CNPJ_CLIENTE},
        )
        StoreOrderItem.objects.create(
            order=self.order, product=product, product_name='Coffee break',
            sku='CB1', unit_price=500, quantity=1, subtotal=500,
        )
        self.client.force_authenticate(self.owner)
        self.url = f'/api/v1/stores/{self.store.slug}/orders/{self.order.id}/emit_nfce/'

    @patch('apps.fiscal.services.FocusProvider.emit_nfe')
    def test_emitir_modelo_55_grava_documento_como_nfe(self, mock_emit):
        mock_emit.return_value = EmitResult(
            status='authorized', chave_acesso='5' * 44, numero='7', serie='1',
        )
        resp = self.client.post(self.url, {'modelo': '55'}, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        doc = FiscalDocument.objects.get(order=self.order)
        self.assertEqual(doc.modelo, '55')
        self.assertEqual(doc.ref, f'nfe-{self.order.id}')
        self.assertEqual(resp.data['modelo'], '55')

    @patch('apps.fiscal.services.FocusProvider.emit_nfe')
    @patch('apps.fiscal.services.FocusProvider.emit_nfce')
    def test_o_mesmo_pedido_pode_ter_nfce_e_nfe_separadas(self, mock_nfce, mock_nfe):
        """Não são a mesma nota: a idempotência é por modelo, senão a segunda
        emissão devolveria a nota errada."""
        mock_nfce.return_value = EmitResult(status='authorized', chave_acesso='6' * 44, numero='1')
        mock_nfe.return_value = EmitResult(status='authorized', chave_acesso='5' * 44, numero='2')
        self.client.post(self.url, {'modelo': '65'}, format='json')
        self.client.post(self.url, {'modelo': '55'}, format='json')
        modelos = set(FiscalDocument.objects.filter(order=self.order).values_list('modelo', flat=True))
        self.assertEqual(modelos, {'65', '55'})
        mock_nfce.assert_called_once()
        mock_nfe.assert_called_once()

    @patch('apps.fiscal.services.FocusProvider.emit_nfe')
    def test_reemitir_o_mesmo_modelo_nao_duplica(self, mock_emit):
        mock_emit.return_value = EmitResult(status='authorized', chave_acesso='5' * 44, numero='7')
        self.client.post(self.url, {'modelo': '55'}, format='json')
        self.client.post(self.url, {'modelo': '55'}, format='json')
        self.assertEqual(FiscalDocument.objects.filter(order=self.order).count(), 1)
        mock_emit.assert_called_once()

    def test_modelo_invalido_e_recusado(self):
        resp = self.client.post(self.url, {'modelo': '99'}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(FiscalDocument.objects.exists())

    def test_nfe_sem_endereco_devolve_400_explicando(self):
        self.order.delivery_address = {}
        self.order.save(update_fields=['delivery_address'])
        resp = self.client.post(self.url, {'modelo': '55'}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('endereço', resp.data['error'].lower())
        self.assertFalse(FiscalDocument.objects.exists())

    def test_consulta_lista_as_notas_do_pedido(self):
        FiscalDocument.objects.create(
            store=self.store, order=self.order, provider='focus', modelo='55',
            status='authorized', ref=f'nfe-{self.order.id}', numero='7',
        )
        resp = self.client.get(
            f'/api/v1/stores/{self.store.slug}/orders/{self.order.id}/nfce/'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([d['modelo'] for d in resp.data['documentos']], ['55'])
