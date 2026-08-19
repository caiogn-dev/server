"""Clicar "tentar de novo" não pode responder "carrinho vazio".

Quando o pagamento falha, o pedido JÁ FOI criado e o carrinho JÁ FOI limpo. O
cliente vê "pagamento falhou", clica de novo e o checkout responde
400 "Cart is empty" — uma mensagem que não descreve nada do que aconteceu e
não oferece saída. Foi o que a Sheslley viu 5 vezes seguidas em 19/08,
enquanto o pedido dela estava lá, criado, no painel da loja.

O carrinho passa a ficar registrado no pedido (metadata['cart_key']), e o
checkout com carrinho vazio devolve o pedido daquele carrinho em vez do erro —
o cliente cai na tela de pagamento do pedido que já existe, sem duplicar venda.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.stores.models import Store, StoreOrder


class RetryDoCheckoutTests(TestCase):
    def setUp(self):
        User = get_user_model()
        owner = User.objects.create_user(username='dono_rt', email='d@rt.com', password='x')
        self.store = Store.objects.create(
            name='Loja RT', slug='loja-rt', owner=owner, status='active',
        )
        self.cart_key = 'cart_11111111-2222-3333-4444-555555555555'
        self.pedido = StoreOrder.objects.create(
            store=self.store, customer_name='Sheslley Costa',
            customer_email='s@t.com', customer_phone='63992509193',
            subtotal=Decimal('39.33'), total=Decimal('39.33'),
            payment_status=StoreOrder.PaymentStatus.FAILED,
            metadata={'cart_key': self.cart_key},
        )

    def _checkout(self, cart_key):
        return self.client.post(
            f'/api/v1/stores/{self.store.slug}/checkout/?cart_key={cart_key}',
            data={
                'customer_name': 'Sheslley Costa',
                'customer_phone': '63992509193',
                'customer_email': 's@t.com',
                'delivery_method': 'pickup',
                'payment_method': 'pix',
            },
            content_type='application/json',
        )

    def test_retry_devolve_o_pedido_existente_em_vez_de_carrinho_vazio(self):
        resp = self._checkout(self.cart_key)
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        corpo = resp.json()
        self.assertEqual(corpo['order_number'], self.pedido.order_number)
        self.assertTrue(corpo.get('pedido_ja_existia'))

    def test_resposta_traz_o_token_para_o_cliente_abrir_o_pedido(self):
        corpo = self._checkout(self.cart_key).json()
        self.assertEqual(corpo['access_token'], self.pedido.access_token)

    def test_carrinho_vazio_sem_pedido_nenhum_continua_400(self):
        """Sem pedido para devolver, o erro honesto continua sendo erro."""
        resp = self._checkout('cart_00000000-0000-0000-0000-000000000000')
        self.assertEqual(resp.status_code, 400)

    def test_pedido_antigo_nao_e_reaproveitado(self):
        """Carrinho reusado dias depois é compra nova, não retry."""
        StoreOrder.objects.filter(pk=self.pedido.pk).update(
            created_at=timezone.now() - timezone.timedelta(days=2),
        )
        resp = self._checkout(self.cart_key)
        self.assertEqual(resp.status_code, 400)
