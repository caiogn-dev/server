"""O `except Exception` que envolve o checkout inteiro — os dois não-casos.

Ontem (17/set) a cobrança que LEVANTA ganhou porta própria
(`_cobranca_que_explodiu`). Sobraram duas falhas que ainda caem no `except`
genérico da view:

1. **Falha DEPOIS do pedido e da cobrança existirem.** A resposta é montada
   com `get_loyalty_status`, que lê o programa de fidelidade da loja. Se ela
   levanta, o cliente lê "Erro ao processar checkout." — com o pedido no painel
   e o PIX gerado no Mercado Pago. Ele não vê o código, não paga, e a loja vê
   um pedido "aguardando pagamento" que o cliente acha que não existe.
   O bloco de fidelidade da resposta é enfeite: não pode derrubar a venda.

2. **Bug de código DENTRO do `create_order`** (AttributeError, KeyError…).
   Respondia 400 — "o erro é seu" — e logava só a mensagem, sem traceback: no
   GlitchTip aparecia uma linha sem pilha, indistinguível de cliente digitando
   errado. Recusa de regra de negócio continua 400 (`ValueError`, com a
   mensagem acionável); defeito nosso passa a ser 500 com traceback. O corpo
   continua `{'error': ...}` — a tela (erroDoCheckout.js) lê `data.error` em
   qualquer status, então quem compra vê a mesma frase.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import (
    Store,
    StoreCart,
    StoreCartItem,
    StoreCategory,
    StoreOrder,
    StoreProduct,
)

User = get_user_model()

PIX_OK = {
    'success': True,
    'status': 'pending',
    'payment_id': '999001',
    'payment_method': 'pix',
    'pix_code': '00020126PIXCOPIAECOLA',
    'pix_qr_code': 'base64qr',
}


class FalhaDepoisDoPedidoTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='o-depois', password='x', email='owner-depois@real.com',
        )
        self.store = Store.objects.create(
            name='Loja Depois', slug='loja-depois', owner=self.owner, status='active',
        )
        category = StoreCategory.objects.create(
            store=self.store, name='Cat', slug='cat-depois', is_active=True, sort_order=1,
        )
        self.product = StoreProduct.objects.create(
            store=self.store, category=category, name='Prato',
            slug='prato-depois', price=Decimal('30.00'),
            status=StoreProduct.ProductStatus.ACTIVE, track_stock=False,
        )
        self.cart_key = 'cart-depois'
        cart, _ = StoreCart.objects.get_or_create(store=self.store, session_key=self.cart_key)
        StoreCartItem.objects.create(cart=cart, product=self.product, quantity=1)

    def _checkout(self):
        return self.client.post(
            f'/api/v1/stores/{self.store.slug}/checkout/',
            {
                'customer_name': 'Cliente Depois',
                'customer_email': 'cli-depois@real.com',
                'customer_phone': '+5563999990002',
                'delivery_method': 'pickup',
                'payment_method': 'pix',
            },
            format='json', HTTP_X_CART_KEY=self.cart_key,
        )

    def _patches_de_efeito_colateral(self):
        return (
            patch('apps.stores.services.print_service.enqueue_order_print_job'),
            patch('apps.stores.services.checkout_service.trigger_order_email_automation'),
        )

    # --- 1. falha depois do pedido ------------------------------------------

    def _checkout_com_fidelidade_quebrada(self):
        p1, p2 = self._patches_de_efeito_colateral()
        with p1, p2, patch(
            'apps.stores.api.views.storefront_views.checkout_service.create_payment',
            return_value=PIX_OK,
        ), patch(
            'apps.stores.api.views.storefront_views.checkout_service.get_loyalty_status',
            side_effect=RuntimeError('programa de fidelidade com dado torto'),
        ):
            return self._checkout()

    def test_fidelidade_quebrada_nao_esconde_o_pix_gerado(self):
        resp = self._checkout_com_fidelidade_quebrada()

        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data['pix_code'], PIX_OK['pix_code'])
        pedido = StoreOrder.objects.get(store=self.store)
        self.assertEqual(resp.data['order_id'], str(pedido.id))
        self.assertTrue(resp.data['access_token'])

    def test_fidelidade_quebrada_responde_bloco_vazio_e_loga_a_causa(self):
        with self.assertLogs('apps.stores.api.views.storefront_views', 'ERROR') as logs:
            resp = self._checkout_com_fidelidade_quebrada()

        self.assertEqual(resp.data['loyalty'], None)
        self.assertTrue(
            any(r.exc_info for r in logs.records),
            'a causa precisa ir para o log com traceback',
        )

    # --- 2. bug de código dentro do create_order ----------------------------

    def _checkout_com_create_order(self, erro):
        p1, p2 = self._patches_de_efeito_colateral()
        with p1, p2, patch(
            'apps.stores.api.views.storefront_views.checkout_service.create_order',
            side_effect=erro,
        ):
            return self._checkout()

    def test_bug_de_codigo_e_500_e_nao_culpa_de_quem_compra(self):
        resp = self._checkout_com_create_order(AttributeError("'NoneType' has no attribute 'x'"))

        self.assertEqual(resp.status_code, 500)
        # A tela lê data.error em qualquer status: a frase continua legível.
        self.assertTrue(resp.data['error'])
        self.assertNotIn('NoneType', resp.data['error'])

    def test_bug_de_codigo_vai_para_o_log_com_traceback(self):
        with self.assertLogs('apps.stores.api.views.storefront_views', 'ERROR') as logs:
            self._checkout_com_create_order(KeyError('campo_sumido'))

        self.assertTrue(any(r.exc_info for r in logs.records))

    def test_recusa_de_regra_de_negocio_continua_400_com_a_mensagem(self):
        resp = self._checkout_com_create_order(ValueError('Cupom BEMVINDO10 expirou'))

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error'], 'Cupom BEMVINDO10 expirou')
