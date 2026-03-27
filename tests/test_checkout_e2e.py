"""
End-to-end integration tests for the storefront checkout flow.

Covers the full happy path plus key error scenarios:
  1. Add items to cart  → POST /{slug}/cart/add/
  2. Submit checkout    → POST /{slug}/checkout/
  3. Verify order created with correct totals, items, stock deducted
  4. Verify access-token endpoint returns the order
  5. Verify PDF receipt endpoint returns valid PDF bytes
  6. Coupon validation and discount application
  7. Checkout rejected when product has insufficient stock
"""
import unittest
from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.stores.models import (
    Store,
    StoreCategory,
    StoreProduct,
    StoreOrder,
    StoreCoupon,
)

User = get_user_model()

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_owner(username="checkout_owner", email="checkout@example.com"):
    return User.objects.create_user(username=username, email=email, password="pass123")


def _make_store(owner, slug="checkout-store"):
    return Store.objects.create(
        name="Checkout Store",
        slug=slug,
        store_type=Store.StoreType.FOOD,
        status=Store.StoreStatus.ACTIVE,
        owner=owner,
        currency="BRL",
    )


def _make_category(store):
    return StoreCategory.objects.create(
        store=store, name="Salads", slug="salads", is_active=True, sort_order=1
    )


def _make_product(store, category, name="Caesar Salad", price=29.90, stock=10):
    slug = name.lower().replace(" ", "-")
    return StoreProduct.objects.create(
        store=store,
        category=category,
        name=name,
        slug=slug,
        price=Decimal(str(price)),
        status=StoreProduct.ProductStatus.ACTIVE,
        sort_order=1,
        stock_quantity=stock,
        track_stock=True,
    )


# ─── Base test case ────────────────────────────────────────────────────────────


class CheckoutTestBase(TestCase):
    """
    Base class that wires up a store + product and provides helpers to:
      - add items to the cart
      - submit checkout
    """

    slug = "base-checkout-store"
    owner_username = "base_owner"
    owner_email = "base@example.com"

    def setUp(self):
        self.client = APIClient()
        # Keep the Django session alive across requests
        self.client.handler.enforce_csrf_checks = False
        self.owner = User.objects.create_user(
            username=self.owner_username, email=self.owner_email, password="pass123"
        )
        self.store = _make_store(self.owner, slug=self.slug)
        self.category = _make_category(self.store)
        self.product = _make_product(self.store, self.category)
        self.url_base = f"/api/v1/stores/{self.store.slug}"

    # ------------------------------------------------------------------
    # Cart helpers — same session maintained via self.client
    # ------------------------------------------------------------------

    def _add_to_cart(self, product, quantity=1):
        response = self.client.post(
            f"{self.url_base}/cart/add/",
            {"product_id": str(product.id), "quantity": quantity},
            format="json",
        )
        return response

    def _checkout(self, extra=None):
        payload = {
            "customer_name": "Ana Silva",
            "customer_phone": "11999990000",
            "customer_email": "ana@example.com",
            "delivery_method": "pickup",
            "payment_method": "cash",
        }
        if extra:
            payload.update(extra)
        return self.client.post(f"{self.url_base}/checkout/", payload, format="json")

    def _get_order_from_response(self, resp_data):
        order_id = resp_data.get("order_id") or resp_data.get("id")
        self.assertIsNotNone(order_id, f"No order_id in response: {resp_data}")
        return StoreOrder.objects.select_related("store").prefetch_related("items").get(id=order_id)


# ─── Happy-path tests ─────────────────────────────────────────────────────────


class CheckoutHappyPathTestCase(CheckoutTestBase):
    """Full happy-path e2e tests for the storefront checkout flow."""

    slug = "checkout-store-happy"
    owner_username = "happy_owner"
    owner_email = "happy@example.com"

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------

    def test_public_catalog_no_auth(self):
        """Anyone can fetch the store catalog without authentication."""
        response = self.client.get(f"{self.url_base}/catalog/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check product appears somewhere in the response
        content = str(response.data)
        self.assertIn(str(self.product.id), content)

    # ------------------------------------------------------------------
    # Cart
    # ------------------------------------------------------------------

    def test_add_to_cart(self):
        """POST to /cart/add/ returns 200/201 and the updated cart."""
        response = self._add_to_cart(self.product, quantity=2)
        self.assertIn(
            response.status_code, [200, 201], msg=f"Add to cart failed: {response.data}"
        )

    # ------------------------------------------------------------------
    # Pickup checkout
    # ------------------------------------------------------------------

    def test_pickup_checkout_creates_order(self):
        """Full cart → checkout flow creates a StoreOrder."""
        self._add_to_cart(self.product, quantity=2)

        initial_stock = self.product.stock_quantity
        resp = self._checkout()
        self.assertIn(resp.status_code, [200, 201], msg=f"Checkout failed: {resp.data}")

        order = self._get_order_from_response(resp.data)
        self.assertEqual(order.store, self.store)
        self.assertEqual(order.delivery_method, "pickup")
        self.assertEqual(order.customer_name, "Ana Silva")

        # Items persisted
        item = order.items.first()
        self.assertIsNotNone(item)
        self.assertEqual(item.quantity, 2)

        # Stock deducted
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, initial_stock - 2)

    def test_pickup_checkout_total_calculation(self):
        """Order total = unit_price × quantity (no delivery fee for pickup)."""
        self._add_to_cart(self.product, quantity=3)
        resp = self._checkout()
        self.assertIn(resp.status_code, [200, 201], msg=str(resp.data))

        order = self._get_order_from_response(resp.data)
        expected = Decimal("29.90") * 3
        self.assertEqual(order.total, expected)

    # ------------------------------------------------------------------
    # Delivery checkout
    # ------------------------------------------------------------------

    def test_delivery_checkout_stores_address(self):
        """Delivery checkout stores the address on the order."""
        self._add_to_cart(self.product)
        resp = self._checkout(
            extra={
                "delivery_method": "delivery",
                "delivery_address": {
                    "street": "Rua das Flores",
                    "number": "123",
                    "neighborhood": "Centro",
                    "city": "São Paulo",
                    "state": "SP",
                    "zip_code": "01310-100",
                },
            }
        )
        self.assertIn(resp.status_code, [200, 201], msg=str(resp.data))

        order = self._get_order_from_response(resp.data)
        self.assertEqual(order.delivery_method, "delivery")
        addr = order.delivery_address or {}
        self.assertEqual(addr.get("city"), "São Paulo")

    # ------------------------------------------------------------------
    # Access token
    # ------------------------------------------------------------------

    def test_order_by_access_token(self):
        """An order can be retrieved publicly using its access token."""
        self._add_to_cart(self.product)
        resp = self._checkout()
        self.assertIn(resp.status_code, [200, 201])

        order = self._get_order_from_response(resp.data)
        token = order.access_token
        self.assertIsNotNone(token)

        token_resp = self.client.get(f"/api/v1/stores/orders/by-token/{token}/")
        self.assertEqual(token_resp.status_code, status.HTTP_200_OK)
        # The by-token endpoint returns `order_id` (not `id`)
        self.assertEqual(str(token_resp.data["order_id"]), str(order.id))

    # ------------------------------------------------------------------
    # PDF receipt
    # ------------------------------------------------------------------

    @unittest.skipUnless(
        __import__("importlib.util", fromlist=["find_spec"]).find_spec("reportlab") is not None,
        "reportlab not installed",
    )
    def test_receipt_returns_pdf(self):
        """GET /orders/{id}/receipt/?token=… returns a valid PDF."""
        self._add_to_cart(self.product)
        resp = self._checkout()
        self.assertIn(resp.status_code, [200, 201])

        order = self._get_order_from_response(resp.data)

        receipt_resp = self.client.get(
            f"/api/v1/stores/orders/{order.id}/receipt/?token={order.access_token}"
        )
        self.assertEqual(receipt_resp.status_code, status.HTTP_200_OK)
        self.assertIn("application/pdf", receipt_resp["Content-Type"])
        self.assertTrue(receipt_resp.content.startswith(b"%PDF"))

    # ------------------------------------------------------------------
    # Empty-cart guard
    # ------------------------------------------------------------------

    def test_checkout_with_empty_cart_returns_400(self):
        """Checkout without any cart items returns 400."""
        resp = self._checkout()
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("empty", str(resp.data).lower())


# ─── Coupon tests ─────────────────────────────────────────────────────────────


class CheckoutCouponTestCase(CheckoutTestBase):
    """Tests for coupon validation and discount application."""

    slug = "checkout-store-coupon"
    owner_username = "coupon_owner"
    owner_email = "coupon@example.com"

    def setUp(self):
        super().setUp()
        # Override product to price=100 for easy discount maths
        self.product = _make_product(
            self.store, self.category, name="Premium Salad", price=100.00, stock=20
        )
        now = timezone.now()
        self.coupon = StoreCoupon.objects.create(
            store=self.store,
            code="SAVE10",
            discount_type=StoreCoupon.DiscountType.PERCENTAGE,
            discount_value=Decimal("10.00"),
            is_active=True,
            min_purchase=Decimal("50.00"),
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=30),
        )

    def test_validate_coupon_endpoint(self):
        """POST /validate-coupon/ returns coupon details for a valid code."""
        response = self.client.post(
            f"{self.url_base}/validate-coupon/",
            {"code": "SAVE10", "subtotal": "100"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get("valid", False))

    def test_checkout_with_valid_coupon_applies_discount(self):
        """Checkout with a valid coupon correctly deducts the discount."""
        self._add_to_cart(self.product, quantity=1)
        resp = self._checkout(extra={"coupon_code": "SAVE10"})
        self.assertIn(resp.status_code, [200, 201], msg=str(resp.data))

        order = self._get_order_from_response(resp.data)
        # 10% of R$100 = R$10 discount → total R$90
        self.assertEqual(order.discount, Decimal("10.00"))
        self.assertEqual(order.total, Decimal("90.00"))
        self.assertEqual(order.coupon_code, "SAVE10")

    def test_invalid_coupon_does_not_apply_discount(self):
        """Checkout with a non-existent coupon must not apply any discount."""
        self._add_to_cart(self.product, quantity=1)
        resp = self._checkout(extra={"coupon_code": "FAKECODE"})

        if resp.status_code in [200, 201]:
            order = self._get_order_from_response(resp.data)
            self.assertEqual(order.discount, Decimal("0.00"))
        else:
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ─── Stock tests ──────────────────────────────────────────────────────────────


class CheckoutStockTestCase(CheckoutTestBase):
    """Tests for stock management during checkout."""

    slug = "checkout-store-stock"
    owner_username = "stock_owner"
    owner_email = "stock@example.com"

    def test_checkout_rejected_when_stock_insufficient(self):
        """Checkout fails with 400 when quantity exceeds available stock."""
        low_product = _make_product(
            self.store, self.category, name="Low Stock Item", price=50.00, stock=1
        )
        self._add_to_cart(low_product, quantity=5)
        resp = self._checkout()

        self.assertEqual(
            resp.status_code,
            status.HTTP_400_BAD_REQUEST,
            msg=f"Expected 400 for insufficient stock, got {resp.status_code}: {resp.data}",
        )
        low_product.refresh_from_db()
        self.assertEqual(low_product.stock_quantity, 1)

    def test_checkout_uses_all_available_units(self):
        """Checkout succeeds when requesting exactly the available stock quantity."""
        exact_product = _make_product(
            self.store, self.category, name="Exact Stock", price=50.00, stock=3
        )
        self._add_to_cart(exact_product, quantity=3)
        resp = self._checkout()

        self.assertIn(resp.status_code, [200, 201], msg=str(resp.data))
        exact_product.refresh_from_db()
        self.assertEqual(exact_product.stock_quantity, 0)
