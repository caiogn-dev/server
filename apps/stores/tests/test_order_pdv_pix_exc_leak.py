"""POST /orders/ (PDV/admin) — mensagem de exceção PIX não deve vazar na resposta.

Bug (P1): quando CheckoutService.create_payment() lança uma exceção inesperada
(timeout, erro de serialização, falha de rede etc.) durante a criação de pedido
via PDV, o campo `payment_error` na resposta 201 continha `str(exc)` — ou seja,
detalhes internos do backend (stack frames, URLs de API, tokens, mensagens do
MercadoPago) ficavam expostos para o cliente da dashboard.

Contrato correto:
- 201 mantido (o pedido foi criado com sucesso)
- `payment_error` recebe mensagem genérica e segura
- Nenhum detalhe técnico da exceção vaza no corpo JSON
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreProduct

User = get_user_model()

_INTERNAL_MESSAGE = 'Connection to MP timed out: secret_access_token=tok_abc123'


class PdvPixExceptionLeakTest(APITestCase):
    """Garante que str(exc) não vaza em payment_error na rota PDV."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='o-pdvleak', email='pdvleak@real.com', password='x'
        )
        self.store = Store.objects.create(
            billing_exempt=True,
            name='Loja PDV Leak', slug='loja-pdvleak', owner=self.owner, status='active',
        )
        self.product = StoreProduct.objects.create(
            store=self.store, name='Produto PDV', slug='prod-pdvleak',
            price=50, is_active=True, track_stock=False,
        )
        token = Token.objects.create(user=self.owner)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def _post_pix_order(self):
        return self.client.post(
            f'/api/v1/stores/{self.store.slug}/orders/',
            {
                'customer_name': 'Cliente PDV',
                'customer_phone': '63999990000',
                'payment_method': 'pix',
                'delivery_method': 'pickup',
                'items': [{'product_id': str(self.product.id), 'quantity': 1}],
            },
            format='json',
        )

    @patch('apps.stores.api.views.order_views.broadcast_order_event')
    def test_excecao_pix_nao_vaza_mensagem_interna(self, _broadcast):
        """str(exc) não deve aparecer no corpo da resposta."""
        with patch(
            'apps.stores.services.checkout_service.CheckoutService.create_payment',
            side_effect=RuntimeError(_INTERNAL_MESSAGE),
        ):
            resp = self._post_pix_order()

        self.assertEqual(resp.status_code, 201, resp.content)
        payment_error = resp.data.get('payment_error', '')
        self.assertNotIn(_INTERNAL_MESSAGE, payment_error,
                         'Mensagem interna da exceção não deve aparecer na resposta')
        self.assertNotIn('secret_access_token', payment_error,
                         'Detalhes técnicos não devem vazar na resposta')
        # Deve conter alguma mensagem genérica para o frontend exibir
        self.assertTrue(payment_error,
                        'payment_error deve ser não-vazio para o frontend tratar')

    @patch('apps.stores.api.views.order_views.broadcast_order_event')
    def test_excecao_pix_retorna_mensagem_segura(self, _broadcast):
        """payment_error deve ser mensagem genérica e segura."""
        with patch(
            'apps.stores.services.checkout_service.CheckoutService.create_payment',
            side_effect=RuntimeError(_INTERNAL_MESSAGE),
        ):
            resp = self._post_pix_order()

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(
            resp.data.get('payment_error'),
            'Falha ao gerar pagamento PIX',
        )
