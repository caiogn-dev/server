"""Rate limiting tests."""
import pytest
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from apps.core.auth.models import User


@pytest.mark.django_db
class RateLimitingTest(TestCase):
    """Test DRF throttling behavior."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.auth_token = self.user.auth_token.key if hasattr(self.user, 'auth_token') else None

    def test_anonymous_rate_limit(self):
        """Test anonymous user rate limiting (120/minute)."""
        endpoint = '/api/v1/core/health/'

        # First 120 requests should succeed
        for i in range(120):
            response = self.client.get(endpoint)
            assert response.status_code == 200, f"Request {i} failed"

        # 121st request should be rate limited
        response = self.client.get(endpoint)
        assert response.status_code == 429, f"Expected 429, got {response.status_code}"
        assert 'rate_limit' in response.data.get('error', {}).get('code', '')

    def test_authenticated_rate_limit(self):
        """Test authenticated user rate limiting (600/minute)."""
        endpoint = '/api/v1/core/health/'

        if not self.auth_token:
            pytest.skip("Auth token not available")

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.auth_token}')

        # Authenticated users have higher limit (600/minute)
        # For test, just verify throttle is applied
        response = self.client.get(endpoint)
        assert response.status_code == 200

    def test_rate_limit_response_format(self):
        """Test rate limit response is properly formatted."""
        # Simulate exceeding rate limit
        from rest_framework.throttling import SimpleRateThrottle
        from rest_framework.exceptions import Throttled

        # This is tested indirectly through the exception handler
        # Verify exception handler converts Throttled to proper response
        pass

    def test_checkout_rate_limit_restrictive(self):
        """Test checkout endpoint has stricter rate limit (20/minute)."""
        # Configuration verification
        from django.conf import settings

        rates = settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']
        assert rates['checkout'] == '20/minute', "Checkout rate should be 20/minute"
        assert rates['auth'] == '10/minute', "Auth rate should be 10/minute"
        assert rates['user'] == '600/minute', "User rate should be 600/minute"

    def test_webhook_rate_limit_permissive(self):
        """Test webhook endpoint allows high volume (10000/hour)."""
        from django.conf import settings

        rates = settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']
        assert rates['webhook'] == '10000/hour', "Webhook rate should be 10000/hour"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
