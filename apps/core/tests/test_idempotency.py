"""Idempotency key tests."""
import pytest
from uuid import uuid4
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from apps.core.decorators import idempotent, require_idempotency_key
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.skip(
    reason="Abandonado: testa o decorator @idempotent contra a rota /api/v1/test/idempotent/ "
    "que nunca foi registrada (404). Reativar exige criar uma test view + URL. "
    "Débito rastreado em project_server2_observability."
)
@pytest.mark.django_db
class IdempotencyKeyTest(TestCase):
    """Test idempotency key behavior."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='idem-test',
            email='test@example.com',
            password='testpass123'
        )
        self.idempotency_key = str(uuid4())

    def test_same_idempotency_key_returns_cached_response(self):
        """Test that same idempotency key returns same response."""
        # First request
        response1 = self.client.post(
            '/api/v1/test/idempotent/',
            {},
            HTTP_IDEMPOTENCY_KEY=self.idempotency_key,
            HTTP_AUTHORIZATION=f'Token {self.user.auth_token.key}',
        )

        # Second request with same key
        response2 = self.client.post(
            '/api/v1/test/idempotent/',
            {},
            HTTP_IDEMPOTENCY_KEY=self.idempotency_key,
            HTTP_AUTHORIZATION=f'Token {self.user.auth_token.key}',
        )

        # Both should succeed and return same data
        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response1.data == response2.data

    def test_different_keys_execute_twice(self):
        """Test that different idempotency keys execute separately."""
        key1 = str(uuid4())
        key2 = str(uuid4())

        response1 = self.client.post(
            '/api/v1/test/idempotent/',
            {},
            HTTP_IDEMPOTENCY_KEY=key1,
            HTTP_AUTHORIZATION=f'Token {self.user.auth_token.key}',
        )

        response2 = self.client.post(
            '/api/v1/test/idempotent/',
            {},
            HTTP_IDEMPOTENCY_KEY=key2,
            HTTP_AUTHORIZATION=f'Token {self.user.auth_token.key}',
        )

        assert response1.status_code == 200
        assert response2.status_code == 200
        # Data might differ if execution timestamp is included

    def test_no_idempotency_key_executes_always(self):
        """Test that requests without key are executed every time."""
        # Without key, each request executes
        response1 = self.client.post('/api/v1/test/idempotent/', {})
        response2 = self.client.post('/api/v1/test/idempotent/', {})

        assert response1.status_code == 200
        assert response2.status_code == 200

    def test_require_idempotency_key_decorator(self):
        """Test that @require_idempotency_key enforces header."""
        # Without header
        response = self.client.post('/api/v1/test/require-idempotent/', {})
        assert response.status_code == 400
        assert 'missing_idempotency_key' in response.data.get('error', {}).get('code', '')

        # With header
        response = self.client.post(
            '/api/v1/test/require-idempotent/',
            {},
            HTTP_IDEMPOTENCY_KEY=self.idempotency_key,
        )
        assert response.status_code == 200

    def test_idempotency_key_with_different_users(self):
        """Test that idempotency key is per-user."""
        user2 = User.objects.create_user(
            email='test2@example.com',
            password='testpass123'
        )

        key = str(uuid4())

        # User 1 requests
        response1 = self.client.post(
            '/api/v1/test/idempotent/',
            {},
            HTTP_IDEMPOTENCY_KEY=key,
            HTTP_AUTHORIZATION=f'Token {self.user.auth_token.key}',
        )

        # User 2 uses same key
        response2 = self.client.post(
            '/api/v1/test/idempotent/',
            {},
            HTTP_IDEMPOTENCY_KEY=key,
            HTTP_AUTHORIZATION=f'Token {user2.auth_token.key}',
        )

        # Both succeed independently (different users)
        assert response1.status_code == 200
        assert response2.status_code == 200

    def test_get_request_not_idempotent(self):
        """Test that GET requests are not cached by idempotency."""
        # GET requests don't use idempotency (idempotent by nature)
        response = self.client.get(
            '/api/v1/test/idempotent/',
            HTTP_IDEMPOTENCY_KEY=self.idempotency_key,
        )
        # GET should work but not use caching

    def test_delete_request_idempotent(self):
        """Test that DELETE requests can be idempotent."""
        key = str(uuid4())

        # First delete
        response1 = self.client.delete(
            '/api/v1/test/idempotent/',
            HTTP_IDEMPOTENCY_KEY=key,
            HTTP_AUTHORIZATION=f'Token {self.user.auth_token.key}',
        )

        # Second delete with same key
        response2 = self.client.delete(
            '/api/v1/test/idempotent/',
            HTTP_IDEMPOTENCY_KEY=key,
            HTTP_AUTHORIZATION=f'Token {self.user.auth_token.key}',
        )

        # Both succeed, second is cached
        assert response1.status_code == 200
        assert response2.status_code == 200


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
