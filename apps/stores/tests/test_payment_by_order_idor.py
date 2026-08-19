"""Testes de regressão: IDOR em StorePaymentViewSet.by_order [P1].

Problema: `by_order` chamava `service.list_order_payments(order_id)` que faz
`StorePayment.objects.filter(order_id=order_id)` sem escopo de tenant.
Qualquer usuário autenticado podia ver os pagamentos de pedidos de outras lojas
passando `?order_id=<uuid_de_outra_loja>`.

Fix: substituído por `self.get_queryset().filter(order_id=order_id)`, que já
aplica o filtro Q(order__store_id__in=...) | Q(store_id__in=...) da view.
"""
import inspect
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

from django.test import SimpleTestCase


class TestByOrderFonteFix(SimpleTestCase):
    """Análise estática: garante que by_order usa o queryset com escopo de tenant."""

    def _fonte(self):
        from apps.stores.api.payment_views import StorePaymentViewSet
        return inspect.getsource(StorePaymentViewSet.by_order)

    def test_by_order_nao_chama_list_order_payments(self):
        """Antes do fix, by_order chamava service.list_order_payments — vetor IDOR."""
        self.assertNotIn('list_order_payments', self._fonte())

    def test_by_order_usa_get_queryset(self):
        """Fix: by_order deve delegar ao get_queryset() que tem escopo de tenant."""
        self.assertIn('get_queryset()', self._fonte())

    def test_by_order_filtra_por_order_id(self):
        """get_queryset() deve ser encadeado com .filter(order_id=...)."""
        self.assertIn('order_id', self._fonte())

    def test_by_order_nao_instancia_payment_service_para_listar(self):
        """get_payment_service() não deve ser chamado na listagem — era o caminho IDOR."""
        fonte = self._fonte()
        # Aceita que get_payment_service ainda apareça em importação de módulo,
        # mas dentro do método by_order não deve haver chamada de get_payment_service
        linhas = fonte.splitlines()
        # Pula a linha def e conta apenas o corpo do método
        corpo = '\n'.join(linhas[1:])
        self.assertNotIn('get_payment_service', corpo)


class TestByOrderComportamento(SimpleTestCase):
    """Testes comportamentais via mock — sem banco de dados."""

    def _view_com_mock_qs(self, items=None, store_ids=None):
        """Devolve uma instância da view com get_queryset mockado."""
        from apps.stores.api.payment_views import StorePaymentViewSet

        view = StorePaymentViewSet()
        # Simula o queryset já escopado pelo tenant
        qs_mock = MagicMock()
        filtered_mock = MagicMock()
        filtered_mock.__iter__ = MagicMock(return_value=iter(items or []))
        qs_mock.filter.return_value = filtered_mock
        view.get_queryset = MagicMock(return_value=qs_mock)
        return view, qs_mock, filtered_mock

    def test_sem_order_id_retorna_400(self):
        """Quando order_id não é passado, a view deve retornar HTTP 400."""
        from apps.stores.api.payment_views import StorePaymentViewSet
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = factory.get('/payments/by_order/')
        view = StorePaymentViewSet()
        view.request = Request(request)
        view.kwargs = {}
        view.format_kwarg = None
        view.action = 'by_order'

        response = view.by_order(view.request)
        self.assertEqual(response.status_code, 400)

    def test_get_queryset_e_chamado_com_filter_de_order_id(self):
        """Fix: by_order deve passar order_id ao filtro do queryset escopado."""
        from apps.stores.api.payment_views import StorePaymentViewSet
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory

        order_uuid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        factory = APIRequestFactory()
        request = factory.get(f'/payments/by_order/?order_id={order_uuid}')

        view = StorePaymentViewSet()
        qs_mock = MagicMock()
        filtered_qs = MagicMock()
        filtered_qs.__iter__ = MagicMock(return_value=iter([]))
        qs_mock.filter.return_value = filtered_qs
        view.get_queryset = MagicMock(return_value=qs_mock)
        view.request = Request(request)
        view.kwargs = {}
        view.format_kwarg = None
        view.action = 'by_order'

        with patch('apps.stores.api.payment_views.StorePaymentListSerializer') as mock_ser:
            mock_ser.return_value.data = []
            view.by_order(view.request)

        # get_queryset() deve ter sido chamado (escopo de tenant aplicado)
        view.get_queryset.assert_called_once()
        # E o resultado deve ter sido filtrado pelo order_id correto
        qs_mock.filter.assert_called_once_with(order_id=order_uuid)

    def test_atacante_nao_vaza_filter_sem_escopo(self):
        """Antes do fix, filter era chamado em StorePayment.objects diretamente —
        agora deve ser chamado sobre o queryset já escopado pelo get_queryset()."""
        from apps.stores.api.payment_views import StorePaymentViewSet

        # Verifica que o método by_order não faz StorePayment.objects.filter
        fonte = inspect.getsource(StorePaymentViewSet.by_order)
        self.assertNotIn('StorePayment.objects.filter', fonte,
                         "by_order não pode acessar StorePayment.objects diretamente — IDOR")
        self.assertNotIn('StorePayment.objects', fonte,
                         "by_order deve usar self.get_queryset() e nunca StorePayment.objects")
