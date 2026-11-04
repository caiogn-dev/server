"""OrderReceiptView compara o token do pedido em tempo constante e rejeita token vazio."""
from unittest import mock

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from apps.stores.api import webhooks
from apps.stores.api.webhooks import OrderReceiptView


def _order(token):
    order = mock.MagicMock()
    order.access_token = token
    return order


class OrderReceiptTokenTest(SimpleTestCase):
    def _get(self, order, token):
        request = APIRequestFactory().get('/x/receipt/', {'token': token})
        qs = mock.MagicMock()
        qs.select_related.return_value.prefetch_related.return_value.get.return_value = order
        with mock.patch.object(webhooks.StoreOrder, 'objects', qs), \
                mock.patch(
                    'apps.stores.services.receipt_service.generate_order_receipt_pdf',
                    return_value=b'%PDF-1.4',
                ):
            return OrderReceiptView.as_view()(request, order_id='00000000-0000-0000-0000-000000000001')

    def test_token_correto_gera_pdf(self):
        self.assertEqual(self._get(_order('abc123'), 'abc123').status_code, 200)

    def test_token_errado_403(self):
        self.assertEqual(self._get(_order('abc123'), 'abc124').status_code, 403)

    def test_token_nao_ascii_403_sem_500(self):
        self.assertEqual(self._get(_order('abc123'), '\u00e9').status_code, 403)

    def test_pedido_sem_token_nao_aceita_nada(self):
        self.assertEqual(self._get(_order(''), 'x').status_code, 403)
        self.assertEqual(self._get(_order(None), 'x').status_code, 403)

    def test_comparacao_em_tempo_constante(self):
        with mock.patch.object(webhooks.hmac, 'compare_digest', wraps=webhooks.hmac.compare_digest) as cd:
            self._get(_order('abc123'), 'abc123')
        cd.assert_called_once()
