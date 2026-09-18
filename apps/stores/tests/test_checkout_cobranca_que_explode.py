"""A cobrança que EXPLODE (não a que recusa) deixa o pedido mentindo.

O caminho da recusa educada já está honesto e coberto: `create_payment`
devolvendo `{'success': False}` mantém 201, marca o pedido
`payment_status=FAILED` e o corpo traz `payment_error`
(ver test_checkout_pix_failure_honest.py).

O que ninguém modelou foi a cobrança que LEVANTA. `create_payment` levanta
`ValueError("Credenciais de pagamento nao configuradas")` quando a loja não
terminou o OAuth do Mercado Pago (checkout_service.py:1643), e levanta o que o
SDK levantar quando a rede cai. Como a chamada mora dentro do mesmo `try` que
envolve `create_order`, o `except ValueError` / `except Exception` da view
responde 400 — e nesse ponto o pedido JÁ existe.

O prejuízo é a assimetria entre as duas portas da MESMA falha:

  | cobrança recusa educadamente | cobrança levanta            |
  |------------------------------|-----------------------------|
  | 201 com order_id e token     | 400 sem nada do pedido      |
  | corpo traz `payment_error`   | corpo traz texto interno    |
  | pedido fica `FAILED`         | pedido fica `PENDING`       |

A última linha é a que dói: `PENDING` sem nenhum `StorePayment` é exatamente a
cobrança fantasma que o incidente de 06/jul fechou — ela voltou pela porta do
`raise`. No painel a loja lê "aguardando pagamento" de uma cobrança que nunca
chegou a existir.

O que este arquivo NÃO acusa (medido, não suposto): o cliente não fica preso e
não duplica a venda. `create_order` já faz `cart.clear()` antes de a cobrança
ser tentada (checkout_service.py:1364), então o segundo clique encontra o
carrinho vazio e cai no resgate `_pedido_recente_do_carrinho`, devolvendo o
mesmo pedido. Os dois últimos testes existem para FIXAR isso — se alguém tirar
o `cart.clear()` de dentro do `create_order`, a duplicação nasce.
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

#: O texto exato que checkout_service.create_payment levanta quando a loja não
#: concluiu o OAuth do Mercado Pago.
SEM_CREDENCIAL = 'Credenciais de pagamento nao configuradas'


class CobrancaQueExplodeTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='o-explode', password='x', email='owner-explode@real.com',
        )
        self.store = Store.objects.create(
            name='Loja Explode', slug='loja-explode', owner=self.owner, status='active',
        )
        self.category = StoreCategory.objects.create(
            store=self.store, name='Cat', slug='cat-explode',
            is_active=True, sort_order=1,
        )
        self.product = StoreProduct.objects.create(
            store=self.store, category=self.category, name='Prato',
            slug='prato-explode', price=Decimal('30.00'),
            status=StoreProduct.ProductStatus.ACTIVE, track_stock=False,
        )
        self.cart_key = 'cart-explode'
        self._encher_o_carrinho()

    def _encher_o_carrinho(self):
        cart, _ = StoreCart.objects.get_or_create(
            store=self.store, session_key=self.cart_key,
        )
        StoreCartItem.objects.create(cart=cart, product=self.product, quantity=1)
        return cart

    def _checkout(self):
        payload = {
            'customer_name': 'Cliente Explode',
            'customer_email': 'cli-explode@real.com',
            'customer_phone': '+5563999990001',
            'delivery_method': 'pickup',
            'payment_method': 'pix',
        }
        return self.client.post(
            f'/api/v1/stores/{self.store.slug}/checkout/',
            payload, format='json', HTTP_X_CART_KEY=self.cart_key,
        )

    def _checkout_com_cobranca_explodindo(self, erro=None):
        erro = erro or ValueError(SEM_CREDENCIAL)
        with patch('apps.stores.services.print_service.enqueue_order_print_job'), \
                patch('apps.stores.services.checkout_service.trigger_order_email_automation'), \
                patch(
                    'apps.stores.api.views.storefront_views.checkout_service.create_payment',
                    side_effect=erro,
                ):
            return self._checkout()

    def test_pedido_criado_nao_vira_400(self):
        """O pedido existe no banco: responder 400 mente sobre o que aconteceu."""
        resp = self._checkout_com_cobranca_explodindo()

        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertTrue(resp.data.get('order_number'))

    def test_corpo_traz_payment_error_como_na_recusa_educada(self):
        """Mesmo contrato do `success: False` — os frontends já leem isto."""
        resp = self._checkout_com_cobranca_explodindo()

        self.assertTrue(resp.data.get('payment_error'))
        self.assertEqual(resp.data.get('payment_status'), 'failed')

    def test_cliente_nao_le_o_erro_interno_de_configuracao(self):
        """"Credenciais de pagamento nao configuradas" é problema da LOJA.

        Para quem está comprando não descreve nada e não oferece saída.
        """
        resp = self._checkout_com_cobranca_explodindo()

        recado = str(resp.data.get('payment_error') or '')
        # Sem esta linha o teste passaria com `payment_error` ausente — ou seja,
        # passaria justamente no estado quebrado que ele deveria acusar.
        self.assertTrue(recado, 'o corpo precisa dizer o que houve com a cobrança')
        self.assertNotIn('Credenciais', recado)

    def test_pedido_fica_failed_no_banco(self):
        """Sem cobrança criada, fingir `pending` é cobrança fantasma."""
        self._checkout_com_cobranca_explodindo()

        pedido = StoreOrder.objects.filter(store=self.store).latest('created_at')
        self.assertEqual(pedido.payment_status, StoreOrder.PaymentStatus.FAILED)

    def test_carrinho_fica_limpo_depois_do_pedido_criado(self):
        """Caracterização: quem limpa é o `cart.clear()` DENTRO do create_order.

        Não é o `clear_cart` da view — esse nunca roda quando a cobrança
        levanta. É daqui que sai a idempotência do retry.
        """
        self._checkout_com_cobranca_explodindo()

        cart = StoreCart.objects.get(store=self.store, session_key=self.cart_key)
        self.assertEqual(cart.items.count(), 0)

    def test_retry_nao_cria_um_segundo_pedido(self):
        """Caracterização: dois cliques em finalizar = uma venda, não duas.

        Só vale enquanto o carrinho for esvaziado na criação do pedido; é o
        que faz o 2º clique cair no resgate `_pedido_recente_do_carrinho`.
        """
        self._checkout_com_cobranca_explodindo()
        self._checkout_com_cobranca_explodindo()

        self.assertEqual(StoreOrder.objects.filter(store=self.store).count(), 1)

    def test_queda_de_rede_segue_a_mesma_regra(self):
        """O `except Exception` genérico tem o mesmo buraco do `except ValueError`."""
        resp = self._checkout_com_cobranca_explodindo(
            erro=ConnectionError('mercadopago fora do ar'),
        )

        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(StoreOrder.objects.filter(store=self.store).count(), 1)
