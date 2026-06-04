"""WebSocket authentication utilities."""
from rest_framework.authtoken.models import Token
from django.contrib.auth import get_user_model

User = get_user_model()


def validate_websocket_token(token_key: str) -> User | None:
    """
    Validate WebSocket auth token and return authenticated user.

    Args:
        token_key: The auth token string from query params

    Returns:
        Authenticated User if token valid, None otherwise

    This function is called BEFORE accepting WebSocket connection
    to reject unauthorized connections early.
    """
    if not token_key:
        return None

    try:
        token = Token.objects.select_related('user').get(key=token_key)
        return token.user
    except Token.DoesNotExist:
        return None
