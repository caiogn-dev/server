"""Antifraude MP — enriquecimento das preferences (Checkout Pro).

Contexto: 100% das tentativas de cartão em julho/2026 foram recusadas com
`cc_rejected_high_risk` porque as preferences (link de pagamento e cartão
redirect) chegavam no MP sem NENHUM dado do pagador — e o link avulso ainda
pré-preenchia o payer com o e-mail do DONO da loja (auto-pagamento = red flag).

Regras cobertas aqui:
- link avulso sem payer informado → preference SEM bloco `payer` (o Checkout
  Pro coleta os dados reais do comprador); NUNCA o e-mail do dono.
- link avulso com payer informado (inclusive CPF) → payer com identification.
- link sobre pedido → payer completo (email/nome/telefone), itens reais,
  statement_descriptor e metadata.
- cartão redirect (preference) → mesmo enriquecimento.
- pedido com desconto/taxa (soma dos itens ≠ valor cobrado) → item único
  (a preference cobra a SOMA dos itens; não pode divergir do amount_due).
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder, StoreOrderItem

User = get_user_model()


def _mp_pref_mock(pref_id='PREF1', init_point='https://mp.example/checkout/PREF1'):
    sdk = MagicMock()
    sdk.preference().create.return_value = {
        'status': 201,
        'response': {
            'id': pref_id,
            'init_point': init_point,
            'sandbox_init_point': init_point + '?sb=1',
        },
    }
    return sdk


def _pref_sent(mock_sdk):
    """Payload da preference efetivamente enviado ao SDK."""
    return mock_sdk.return_value.preference().create.call_args[0][0]


CREDS = {'access_token': 'TOKEN', 'provider': 'mercadopago'}


class LinkAvulsoPayerTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='o-pref', password='x', email='dono@loja.com',
        )
        self.store = Store.objects.create(
            name='Loja Pref', slug='loja-pref', owner=self.owner, status='active',
        )

    @patch('apps.stores.services.checkout_service.CheckoutService.get_payment_credentials',
           return_value=CREDS)
    @patch('mercadopago.SDK')
    def test_avulso_sem_payer_nao_manda_bloco_payer(self, mock_sdk, _creds):
        from apps.stores.services.checkout_service import CheckoutService
        mock_sdk.return_value = _mp_pref_mock()

        result = CheckoutService.create_payment(
            None, 'link', {}, amount=Decimal('187.99'),
            store=self.store, description='ANDRESSA',
        )

        self.assertTrue(result['success'], result)
        pref = _pref_sent(mock_sdk)
        self.assertNotIn('payer', pref)
        self.assertNotIn('dono@loja.com', str(pref))

    @patch('apps.stores.services.checkout_service.CheckoutService.get_payment_credentials',
           return_value=CREDS)
    @patch('mercadopago.SDK')
    def test_avulso_com_payer_e_cpf(self, mock_sdk, _creds):
        from apps.stores.services.checkout_service import CheckoutService
        mock_sdk.return_value = _mp_pref_mock()

        result = CheckoutService.create_payment(
            None, 'link',
            {'payer_email': 'andressa@real.com', 'payer_name': 'Andressa Silva',
             'payer_document': '123.456.789-09'},
            amount=Decimal('187.99'), store=self.store, description='ANDRESSA',
        )

        self.assertTrue(result['success'], result)
        payer = _pref_sent(mock_sdk)['payer']
        self.assertEqual(payer['email'], 'andressa@real.com')
        self.assertEqual(payer['name'], 'Andressa')
        self.assertEqual(payer['surname'], 'Silva')
        self.assertEqual(payer['identification'], {'type': 'CPF', 'number': '12345678909'})

    @patch('apps.stores.services.checkout_service.CheckoutService.get_payment_credentials',
           return_value=CREDS)
    @patch('mercadopago.SDK')
    def test_avulso_tem_statement_descriptor_e_metadata(self, mock_sdk, _creds):
        from apps.stores.services.checkout_service import CheckoutService
        mock_sdk.return_value = _mp_pref_mock()

        CheckoutService.create_payment(
            None, 'link', {}, amount=Decimal('50.00'), store=self.store,
        )

        pref = _pref_sent(mock_sdk)
        self.assertEqual(pref['statement_descriptor'], 'CARDAPIDEX')
        self.assertEqual(pref['metadata']['store_slug'], 'loja-pref')


class PreferenceComPedidoTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='o-pref2', password='x', email='dono2@loja.com',
        )
        self.store = Store.objects.create(
            name='Loja Pref 2', slug='loja-pref-2', owner=self.owner, status='active',
        )
        self.order = StoreOrder.objects.create(
            store=self.store,
            customer_name='Andressa Silva',
            customer_phone='5563999990000',
            customer_email='andressa@real.com',
            subtotal=Decimal('180.00'), total=Decimal('180.00'),
            delivery_address={'zip_code': '77000-000', 'street': 'Rua A',
                              'number': '10', 'city': 'Palmas', 'state': 'TO'},
        )
        StoreOrderItem.objects.create(
            order=self.order, product_name='Marmita G',
            unit_price=Decimal('60.00'), quantity=2, subtotal=Decimal('120.00'),
        )
        StoreOrderItem.objects.create(
            order=self.order, product_name='Suco',
            unit_price=Decimal('60.00'), quantity=1, subtotal=Decimal('60.00'),
        )

    @patch('apps.stores.services.checkout_service.CheckoutService.get_payment_credentials',
           return_value=CREDS)
    @patch('mercadopago.SDK')
    def test_link_de_pedido_manda_payer_completo_e_itens_reais(self, mock_sdk, _creds):
        from apps.stores.services.checkout_service import CheckoutService
        mock_sdk.return_value = _mp_pref_mock()

        result = CheckoutService.create_payment(self.order, 'link')

        self.assertTrue(result['success'], result)
        pref = _pref_sent(mock_sdk)

        payer = pref['payer']
        self.assertEqual(payer['email'], 'andressa@real.com')
        self.assertEqual(payer['name'], 'Andressa')
        self.assertEqual(payer['surname'], 'Silva')
        self.assertEqual(payer['phone'], {'area_code': '63', 'number': '999990000'})
        self.assertEqual(payer['address']['zip_code'], '77000000')

        titles = [i['title'] for i in pref['items']]
        self.assertIn('Marmita G', titles)
        self.assertIn('Suco', titles)
        soma = sum(Decimal(str(i['unit_price'])) * i['quantity'] for i in pref['items'])
        self.assertEqual(soma, Decimal('180.00'))
        for item in pref['items']:
            self.assertEqual(item['currency_id'], 'BRL')

        self.assertEqual(pref['statement_descriptor'], 'CARDAPIDEX')
        self.assertEqual(pref['metadata']['order_id'], str(self.order.id))

    @patch('apps.stores.services.checkout_service.CheckoutService.get_payment_credentials',
           return_value=CREDS)
    @patch('mercadopago.SDK')
    def test_pedido_com_taxa_de_entrega_usa_item_unico_no_valor_cobrado(self, mock_sdk, _creds):
        """A preference cobra a SOMA dos itens; com taxa/desconto a soma dos
        itens reais diverge do amount_due → cai pro item único (valor certo)."""
        from apps.stores.services.checkout_service import CheckoutService
        mock_sdk.return_value = _mp_pref_mock()
        self.order.delivery_fee = Decimal('10.00')
        self.order.total = Decimal('190.00')
        self.order.save(update_fields=['delivery_fee', 'total'])

        CheckoutService.create_payment(self.order, 'link')

        pref = _pref_sent(mock_sdk)
        self.assertEqual(len(pref['items']), 1)
        self.assertEqual(Decimal(str(pref['items'][0]['unit_price'])), Decimal('190.00'))

    @patch('apps.stores.services.checkout_service.CheckoutService.get_payment_credentials',
           return_value=CREDS)
    @patch('mercadopago.SDK')
    def test_cartao_redirect_tambem_enriquece(self, mock_sdk, _creds):
        from apps.stores.services.checkout_service import CheckoutService
        mock_sdk.return_value = _mp_pref_mock()

        result = CheckoutService.create_payment(
            self.order, 'card', {'allow_redirect': True},
        )

        self.assertTrue(result['success'], result)
        pref = _pref_sent(mock_sdk)
        payer = pref['payer']
        self.assertEqual(payer['email'], 'andressa@real.com')
        self.assertEqual(payer['surname'], 'Silva')
        self.assertEqual(payer['phone'], {'area_code': '63', 'number': '999990000'})
        self.assertEqual(pref['statement_descriptor'], 'CARDAPIDEX')
        titles = [i['title'] for i in pref['items']]
        self.assertIn('Marmita G', titles)
