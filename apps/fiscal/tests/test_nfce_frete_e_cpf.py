"""Fiscal: o total da nota tem que fechar com o total pago, e o CPF do
consumidor só entra se for válido.

Por que estes dois juntos: são as duas formas de a SEFAZ rejeitar a nota
inteira por dado que o sistema já tinha em mãos.
  - frete fora do payload  → soma dos itens ≠ valor pago (rejeição 531/610)
  - CPF com dígito errado  → rejeição 237, venda fica sem nota nenhuma
Em ambos os casos a regra é a mesma: nunca trocar "nota certa" por "nota
nenhuma".
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.fiscal.models import FiscalDocument
from apps.fiscal.providers.base import EmitResult
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

CPF_VALIDO = '52998224725'
CPF_DIGITO_ERRADO = '52998224724'
CNPJ_VALIDO = '11444777000161'


class PayloadFechaComTotalTests(APITestCase):
    """Itens + frete − desconto tem que bater com o que foi pago."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner-frete', email='owner-frete@test.com', password='x',
        )
        self.store = Store.objects.create(
            name='Loja Frete', slug='loja-frete', owner=self.owner, status='active',
            metadata={'fiscal': dict(FISCAL_CFG)},
        )
        category = StoreCategory.objects.create(store=self.store, name='Geral', slug='geral')
        self.product = StoreProduct.objects.create(
            store=self.store, name='Salada', price=20, track_stock=False,
            category=category, sku='SAL1',
        )
        # Pedido de delivery real: 2×20 de item + 9 de frete = 49 pagos
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='Cliente Balcão', customer_phone='00000000000',
            customer_email='x@local.invalid',
            subtotal=Decimal('40.00'), delivery_fee=Decimal('9.00'), total=Decimal('49.00'),
            payment_method='pix', delivery_method='delivery',
            status='pending', payment_status='paid',
        )
        StoreOrderItem.objects.create(
            order=self.order, product=self.product, product_name='Salada',
            sku='SAL1', unit_price=20, quantity=2, subtotal=40,
        )

    def _payload(self):
        return build_nfce_payload(self.order, get_fiscal_config(self.store))

    def test_frete_entra_no_payload(self):
        self.assertEqual(self._payload()['frete'], 9.0)

    def test_soma_dos_itens_mais_frete_bate_com_o_pagamento(self):
        payload = self._payload()
        soma_itens = sum(i['valor_bruto'] for i in payload['itens'])
        pago = sum(p['valor_pagamento'] for p in payload['formas_pagamento'])
        self.assertAlmostEqual(
            soma_itens + payload.get('frete', 0.0) - payload.get('valor_desconto', 0.0),
            pago, places=2,
        )

    def test_retirada_no_balcao_nao_manda_frete(self):
        self.order.delivery_fee = Decimal('0.00')
        self.order.total = Decimal('40.00')
        self.order.delivery_method = 'pickup'
        self.order.save(update_fields=['delivery_fee', 'total', 'delivery_method'])
        self.assertNotIn('frete', self._payload())

    def test_desconto_mantem_a_conta_fechada(self):
        self.order.discount = Decimal('5.00')
        self.order.total = Decimal('44.00')
        self.order.save(update_fields=['discount', 'total'])
        payload = self._payload()
        soma_itens = sum(i['valor_bruto'] for i in payload['itens'])
        pago = sum(p['valor_pagamento'] for p in payload['formas_pagamento'])
        self.assertEqual(payload['valor_desconto'], 5.0)
        self.assertAlmostEqual(soma_itens + payload['frete'] - payload['valor_desconto'], pago, places=2)


class CpfDoConsumidorTests(APITestCase):
    """CPF é opcional; inválido nunca pode derrubar a nota."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner-cpf', email='owner-cpf@test.com', password='x',
        )
        self.store = Store.objects.create(
            name='Loja CPF', slug='loja-cpf', owner=self.owner, status='active',
            metadata={'fiscal': dict(FISCAL_CFG)},
        )
        category = StoreCategory.objects.create(store=self.store, name='Geral', slug='geral')
        product = StoreProduct.objects.create(
            store=self.store, name='Salada', price=20, track_stock=False,
            category=category, sku='SAL1',
        )
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='Cliente Balcão', customer_phone='00000000000',
            customer_email='x@local.invalid', subtotal=20, total=20,
            payment_method='cash', delivery_method='pickup',
            status='pending', payment_status='paid',
        )
        StoreOrderItem.objects.create(
            order=self.order, product=product, product_name='Salada',
            sku='SAL1', unit_price=20, quantity=1, subtotal=20,
        )
        self.client.force_authenticate(self.owner)
        self.url = f'/api/v1/stores/{self.store.slug}/orders/{self.order.id}/emit_nfce/'

    def _payload(self):
        return build_nfce_payload(self.order, get_fiscal_config(self.store))

    def test_sem_cpf_sai_como_consumidor_nao_identificado(self):
        payload = self._payload()
        self.assertNotIn('cpf_destinatario', payload)
        self.assertNotIn('cnpj_destinatario', payload)

    def test_cpf_valido_vai_limpo_no_payload(self):
        self.order.metadata = {'cpf_nota': '529.982.247-25'}
        self.order.save(update_fields=['metadata'])
        self.assertEqual(self._payload()['cpf_destinatario'], CPF_VALIDO)

    def test_cpf_com_digito_errado_nao_vai_mas_a_nota_sai(self):
        self.order.metadata = {'cpf_nota': CPF_DIGITO_ERRADO}
        self.order.save(update_fields=['metadata'])
        payload = self._payload()
        self.assertNotIn('cpf_destinatario', payload)
        self.assertEqual(payload['formas_pagamento'][0]['valor_pagamento'], 20.0)

    def test_cpf_de_digitos_repetidos_e_recusado(self):
        self.order.metadata = {'cpf_nota': '111.111.111-11'}
        self.order.save(update_fields=['metadata'])
        self.assertNotIn('cpf_destinatario', self._payload())

    def test_cnpj_do_consumidor_tambem_e_aceito(self):
        self.order.metadata = {'cpf_nota': CNPJ_VALIDO}
        self.order.save(update_fields=['metadata'])
        payload = self._payload()
        self.assertEqual(payload['cnpj_destinatario'], CNPJ_VALIDO)
        self.assertNotIn('cpf_destinatario', payload)

    @patch('apps.fiscal.services.FocusProvider.emit_nfce')
    def test_endpoint_aceita_cpf_no_corpo_e_guarda_no_pedido(self, mock_emit):
        mock_emit.return_value = EmitResult(status='authorized', chave_acesso='1' * 44, numero='9')
        resp = self.client.post(self.url, {'cpf': '529.982.247-25'}, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.order.refresh_from_db()
        self.assertEqual(self.order.metadata['cpf_nota'], CPF_VALIDO)
        self.assertEqual(mock_emit.call_args.kwargs['payload']['cpf_destinatario'], CPF_VALIDO)

    def test_usa_o_cpf_que_o_cliente_ja_digitou_no_checkout(self):
        """O checkout tem campo de CPF opcional e guarda em metadata.customer.
        Quem preencheu ali já pediu CPF na nota — não faz sentido perguntar de
        novo no balcão."""
        self.order.metadata = {'customer': {'cpf': CPF_VALIDO}}
        self.order.save(update_fields=['metadata'])
        self.assertEqual(self._payload()['cpf_destinatario'], CPF_VALIDO)

    def test_cpf_informado_no_balcao_vence_o_do_checkout(self):
        self.order.metadata = {'cpf_nota': CPF_VALIDO, 'customer': {'cpf': '11144477735'}}
        self.order.save(update_fields=['metadata'])
        self.assertEqual(self._payload()['cpf_destinatario'], CPF_VALIDO)

    def test_endpoint_recusa_cpf_invalido_antes_de_emitir(self):
        """Digitou errado no PDV: avisa na hora em vez de emitir nota sem CPF —
        aqui o operador ainda pode corrigir."""
        resp = self.client.post(self.url, {'cpf': CPF_DIGITO_ERRADO}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('CPF', resp.data['error'])
        self.assertFalse(FiscalDocument.objects.exists())
