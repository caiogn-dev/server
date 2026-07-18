"""
Testes de info-disclosure via str(e) em payment_views e storefront_views.

Verifica que handlers `except Exception as e` nunca retornam `str(e)` para o cliente,
usando mensagem genérica em pt-BR e mantendo o detalhe apenas no log interno.

Endpoints cobertos:
  POST /payments/                   → StorePaymentViewSet.create
  POST /payments/{pk}/process/      → StorePaymentViewSet.process
  POST /payments/{pk}/confirm/      → StorePaymentViewSet.confirm
  POST /payments/{pk}/fail/         → StorePaymentViewSet.fail
  POST /payments/{pk}/cancel/       → StorePaymentViewSet.cancel
  POST /payments/{pk}/refund/       → StorePaymentViewSet.refund

  POST /cart/add/                   → StoreCartViewSet.add_item (AllowAny)
  POST /checkout/                   → StoreCheckoutView (AllowAny)
  GET  /delivery-fee/?distance_km=  → StoreDeliveryFeeView (AllowAny)

Todos SimpleTestCase (sem DB) para rodar no container de CI sem PostgreSQL.
"""
from unittest.mock import patch, MagicMock
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory
from rest_framework import status

SENSITIVE = "MP_TOKEN_XYZ:oauth2/access_token=abc123&client_secret=s3cr3t"


# ---------------------------------------------------------------------------
# payment_views.py — StorePaymentViewSet
# ---------------------------------------------------------------------------

class PaymentCreateStrELeakTest(SimpleTestCase):
    def _call(self, exc):
        from apps.stores.api.payment_views import StorePaymentViewSet

        factory = APIRequestFactory()
        request = factory.post("/payments/", {"order_id": "x"}, format="json")
        request.user = MagicMock(is_authenticated=True)

        view = StorePaymentViewSet.as_view({"post": "create"})
        mock_svc = MagicMock()
        mock_svc.create_payment.side_effect = exc

        with patch("apps.stores.api.payment_views.get_payment_service", return_value=mock_svc), \
             patch("apps.stores.api.payment_views.CreatePaymentSerializer") as MockSer:
            inst = MagicMock()
            inst.is_valid.return_value = True
            inst.validated_data = {"order_id": "uuid"}
            MockSer.return_value = inst
            return view(request)

    def test_nao_vaza_mensagem_interna(self):
        self.assertNotIn(SENSITIVE, str(self._call(Exception(SENSITIVE)).data))

    def test_retorna_mensagem_generica(self):
        self.assertIn("Erro ao criar pagamento", str(self._call(Exception(SENSITIVE)).data))

    def test_status_400(self):
        self.assertEqual(self._call(Exception(SENSITIVE)).status_code, status.HTTP_400_BAD_REQUEST)


class PaymentProcessStrELeakTest(SimpleTestCase):
    def _call(self, exc):
        from apps.stores.api.payment_views import StorePaymentViewSet

        factory = APIRequestFactory()
        request = factory.post("/payments/1/process/", {}, format="json")
        request.user = MagicMock(is_authenticated=True)

        view = StorePaymentViewSet.as_view({"post": "process"})
        mock_payment = MagicMock(id="uuid")
        mock_svc = MagicMock()
        mock_svc.process_payment.side_effect = exc

        with patch.object(StorePaymentViewSet, "get_object", return_value=mock_payment), \
             patch("apps.stores.api.payment_views.get_payment_service", return_value=mock_svc), \
             patch("apps.stores.api.payment_views.ProcessPaymentSerializer") as MockSer:
            inst = MagicMock()
            inst.is_valid.return_value = True
            inst.validated_data = {}
            MockSer.return_value = inst
            return view(request, pk="uuid")

    def test_nao_vaza_mensagem_interna(self):
        self.assertNotIn(SENSITIVE, str(self._call(Exception(SENSITIVE)).data))

    def test_retorna_mensagem_generica(self):
        self.assertIn("Erro ao processar pagamento", str(self._call(Exception(SENSITIVE)).data))


class PaymentConfirmStrELeakTest(SimpleTestCase):
    def _call(self, exc):
        from apps.stores.api.payment_views import StorePaymentViewSet

        factory = APIRequestFactory()
        request = factory.post("/payments/1/confirm/", {}, format="json")
        request.user = MagicMock(is_authenticated=True)

        view = StorePaymentViewSet.as_view({"post": "confirm"})
        mock_payment = MagicMock(id="uuid")
        mock_svc = MagicMock()
        mock_svc.confirm_payment.side_effect = exc

        with patch.object(StorePaymentViewSet, "get_object", return_value=mock_payment), \
             patch("apps.stores.api.payment_views.get_payment_service", return_value=mock_svc), \
             patch("apps.stores.api.payment_views.ConfirmPaymentSerializer") as MockSer:
            inst = MagicMock()
            inst.is_valid.return_value = True
            inst.validated_data = {}
            MockSer.return_value = inst
            return view(request, pk="uuid")

    def test_nao_vaza_mensagem_interna(self):
        self.assertNotIn(SENSITIVE, str(self._call(Exception(SENSITIVE)).data))

    def test_retorna_mensagem_generica(self):
        self.assertIn("Erro ao confirmar pagamento", str(self._call(Exception(SENSITIVE)).data))


class PaymentFailStrELeakTest(SimpleTestCase):
    def _call(self, exc):
        from apps.stores.api.payment_views import StorePaymentViewSet

        factory = APIRequestFactory()
        request = factory.post("/payments/1/fail/", {}, format="json")
        request.user = MagicMock(is_authenticated=True)

        view = StorePaymentViewSet.as_view({"post": "fail"})
        mock_payment = MagicMock(id="uuid")
        mock_svc = MagicMock()
        mock_svc.fail_payment.side_effect = exc

        with patch.object(StorePaymentViewSet, "get_object", return_value=mock_payment), \
             patch("apps.stores.api.payment_views.get_payment_service", return_value=mock_svc), \
             patch("apps.stores.api.payment_views.FailPaymentSerializer") as MockSer:
            inst = MagicMock()
            inst.is_valid.return_value = True
            inst.validated_data = {"error_code": "X", "error_message": "Y"}
            MockSer.return_value = inst
            return view(request, pk="uuid")

    def test_nao_vaza_mensagem_interna(self):
        self.assertNotIn(SENSITIVE, str(self._call(Exception(SENSITIVE)).data))

    def test_retorna_mensagem_generica(self):
        self.assertIn("Erro ao registrar falha", str(self._call(Exception(SENSITIVE)).data))


class PaymentCancelStrELeakTest(SimpleTestCase):
    def _call(self, exc):
        from apps.stores.api.payment_views import StorePaymentViewSet

        factory = APIRequestFactory()
        request = factory.post("/payments/1/cancel/", {}, format="json")
        request.user = MagicMock(is_authenticated=True)

        view = StorePaymentViewSet.as_view({"post": "cancel"})
        mock_payment = MagicMock(id="uuid")
        mock_svc = MagicMock()
        mock_svc.cancel_payment.side_effect = exc

        with patch.object(StorePaymentViewSet, "get_object", return_value=mock_payment), \
             patch("apps.stores.api.payment_views.get_payment_service", return_value=mock_svc):
            return view(request, pk="uuid")

    def test_nao_vaza_mensagem_interna(self):
        self.assertNotIn(SENSITIVE, str(self._call(Exception(SENSITIVE)).data))

    def test_retorna_mensagem_generica(self):
        self.assertIn("Erro ao cancelar pagamento", str(self._call(Exception(SENSITIVE)).data))


class PaymentRefundStrELeakTest(SimpleTestCase):
    def _call(self, exc):
        from apps.stores.api.payment_views import StorePaymentViewSet

        factory = APIRequestFactory()
        request = factory.post("/payments/1/refund/", {}, format="json")
        request.user = MagicMock(is_authenticated=True)

        view = StorePaymentViewSet.as_view({"post": "refund"})
        mock_payment = MagicMock(id="uuid")
        mock_svc = MagicMock()
        mock_svc.refund_payment.side_effect = exc

        with patch.object(StorePaymentViewSet, "get_object", return_value=mock_payment), \
             patch("apps.stores.api.payment_views.get_payment_service", return_value=mock_svc), \
             patch("apps.stores.api.payment_views.RefundPaymentSerializer") as MockSer:
            inst = MagicMock()
            inst.is_valid.return_value = True
            inst.validated_data = {}
            MockSer.return_value = inst
            return view(request, pk="uuid")

    def test_nao_vaza_mensagem_interna(self):
        self.assertNotIn(SENSITIVE, str(self._call(Exception(SENSITIVE)).data))

    def test_retorna_mensagem_generica(self):
        self.assertIn("Erro ao realizar estorno", str(self._call(Exception(SENSITIVE)).data))


# ---------------------------------------------------------------------------
# storefront_views.py — AllowAny (sem autenticação)
# ---------------------------------------------------------------------------

class CartAddItemStrELeakTest(SimpleTestCase):
    """POST AllowAny: add_item (product path) não deve vazar mensagem interna."""

    def _call(self, exc):
        from apps.stores.api.views.storefront_views import StoreCartViewSet

        factory = APIRequestFactory()
        # product_id presente → vai pelo branch 'else' (produto, não combo)
        request = factory.post("/cart/add/", {"product_id": "abc", "quantity": 1}, format="json")
        request.user = MagicMock(is_authenticated=False)

        view = StoreCartViewSet.as_view({"post": "add_item"})
        mock_store = MagicMock()
        mock_cart = MagicMock()

        # NÃO mockar StoreCombo — o except StoreCombo.DoesNotExist precisa da
        # classe real para que Python aceite como alvo de except.
        with patch.object(StoreCartViewSet, "get_store", return_value=mock_store), \
             patch.object(StoreCartViewSet, "get_cart", return_value=mock_cart), \
             patch("apps.stores.api.views.storefront_views.cart_service") as mock_cs:
            mock_cs.add_item.side_effect = exc
            return view(request, store_slug="loja-teste")

    def test_nao_vaza_mensagem_interna(self):
        self.assertNotIn(SENSITIVE, str(self._call(Exception(SENSITIVE)).data))

    def test_retorna_mensagem_generica(self):
        self.assertIn("Erro ao adicionar item ao carrinho", str(self._call(Exception(SENSITIVE)).data))

    def test_status_400(self):
        self.assertEqual(self._call(Exception(SENSITIVE)).status_code, status.HTTP_400_BAD_REQUEST)


class CheckoutStrELeakTest(SimpleTestCase):
    """POST AllowAny: checkout não deve vazar mensagem interna quando create_order falha."""

    def _call(self, exc):
        from apps.stores.api.views.storefront_views import StoreCheckoutView

        factory = APIRequestFactory()
        request = factory.post(
            "/checkout/",
            {
                "customer_name": "Teste",
                "customer_phone": "11999999999",
                "delivery_method": "pickup",
                "payment_method": "",
            },
            format="json",
        )
        request.user = MagicMock(is_authenticated=False)

        view = StoreCheckoutView.as_view()

        mock_store = MagicMock()
        mock_store.slug = "loja-teste"

        mock_cart = MagicMock()
        mock_cart.items.exists.return_value = True
        mock_cart.combo_items.exists.return_value = False

        # Patchear todo o caminho até o try/except interno do checkout
        with patch("apps.stores.api.views.storefront_views.get_active_store", return_value=mock_store), \
             patch("apps.stores.api.views.storefront_views.billing_service") as mock_billing, \
             patch("apps.stores.api.views.storefront_views.cart_service") as mock_cs, \
             patch("apps.stores.api.views.storefront_views.CheckoutSerializer") as MockCS, \
             patch("apps.stores.api.views.storefront_views.checkout_service") as mock_checkout_svc, \
             patch("apps.stores.api.views.storefront_views.get_request_cart_key", return_value="sess-key"):
            mock_billing.orders_in_current_month.return_value = 0
            mock_billing.within_order_limit.return_value = True
            mock_cs.get_or_create_cart.return_value = mock_cart

            ser_inst = MagicMock()
            ser_inst.is_valid.return_value = True
            MockCS.return_value = ser_inst

            # create_order está dentro do try block → levanta Exception com msg sensível
            mock_checkout_svc.create_order.side_effect = exc

            return view(request, store_slug="loja-teste")

    def test_nao_vaza_mensagem_interna(self):
        self.assertNotIn(SENSITIVE, str(self._call(Exception(SENSITIVE)).data))

    def test_retorna_mensagem_generica(self):
        self.assertIn("Erro ao processar checkout", str(self._call(Exception(SENSITIVE)).data))

    def test_status_400(self):
        self.assertEqual(self._call(Exception(SENSITIVE)).status_code, status.HTTP_400_BAD_REQUEST)


class DeliveryFeeStrELeakTest(SimpleTestCase):
    """GET AllowAny: delivery-fee (distance_km path) não deve vazar mensagem interna."""

    def _call(self, exc):
        from apps.stores.api.views.storefront_views import StoreDeliveryFeeView

        factory = APIRequestFactory()
        # Usar GET com distance_km — caminho mais simples (sem geocodificação)
        request = factory.get("/delivery-fee/?distance_km=5")
        request.user = MagicMock(is_authenticated=False)

        view = StoreDeliveryFeeView.as_view()
        mock_store = MagicMock()

        with patch("apps.stores.api.views.storefront_views.get_active_store", return_value=mock_store), \
             patch("apps.stores.api.views.storefront_views.delivery_quote_service") as mock_dqs:
            mock_dqs.calculate_for_distance.side_effect = exc
            return view(request, store_slug="loja-teste")

    def test_nao_vaza_mensagem_interna(self):
        self.assertNotIn(SENSITIVE, str(self._call(Exception(SENSITIVE)).data))

    def test_retorna_mensagem_generica(self):
        self.assertIn("Erro ao calcular taxa de entrega", str(self._call(Exception(SENSITIVE)).data))

    def test_status_400(self):
        self.assertEqual(self._call(Exception(SENSITIVE)).status_code, status.HTTP_400_BAD_REQUEST)
