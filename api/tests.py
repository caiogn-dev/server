from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

from .models import Product, Order, OrderItem, Checkout


User = get_user_model()


class ApiSmokeTests(APITestCase):
    def setUp(self):
        self.user_password = "strong-pass-123"
        self.user = User.objects.create_user(
            username="tester",
            email="tester@example.com",
            password=self.user_password,
            first_name="Test",
            last_name="User",
            phone="11999999999",
        )
        self.product = Product.objects.create(
            name="Teste Produto",
            description="Desc",
            price=10,
            stock_quantity=5,
            image=None,
            category="Test",
            sku="SKU-TEST",
            is_active=True,
        )
        self.order = Order.objects.create(
            user=self.user,
            order_number="ORD-TEST-1",
            total_amount=10,
            status="pending",
            shipping_address="Endereco",
            shipping_city="Cidade",
            shipping_state="ST",
            shipping_zip_code="00000000",
            shipping_country="Brazil",
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=1,
            price=self.product.price,
        )
        self.checkout = Checkout.objects.create(
            order=self.order,
            user=self.user,
            total_amount=self.order.total_amount,
            payment_status="pending",
            session_token="abc123",
            customer_name="Test User",
            customer_email=self.user.email,
            customer_phone=self.user.phone,
            billing_address=self.order.shipping_address,
            billing_city=self.order.shipping_city,
            billing_state=self.order.shipping_state,
            billing_zip_code=self.order.shipping_zip_code,
            billing_country="Brazil",
        )

    def test_csrf_endpoint(self):
        url = reverse("csrf_token")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("csrfToken", resp.data)

    def test_product_list(self):
        url = reverse("product-list")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(resp.data.get("count", 0), 1)

    def test_checkout_status_public(self):
        url = reverse("checkout-status")
        resp = self.client.get(f"{url}?order_number={self.order.order_number}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["order_number"], self.order.order_number)
        self.assertEqual(float(resp.data["total_amount"]), float(self.order.total_amount))
        self.assertIn("checkout", resp.data)

    def test_login_and_profile(self):
        login_url = reverse("api_token_auth")
        resp = self.client.post(login_url, {"login": self.user.email, "password": self.user_password})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        token = resp.data.get("token")
        self.assertIsNotNone(token)
        # auth via header
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        profile_url = reverse("user-profile")
        prof = self.client.get(profile_url)
        self.assertEqual(prof.status_code, status.HTTP_200_OK)
        self.assertEqual(prof.data["email"], self.user.email)
