"""
Core exceptions and exception handler.
"""
import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)


class BaseAPIException(Exception):
    """Base exception for API errors."""
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_message = "An error occurred"
    default_code = "error"

    def __init__(self, message=None, code=None, details=None):
        self.message = message or self.default_message
        self.code = code or self.default_code
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(BaseAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_message = "Validation error"
    default_code = "validation_error"


class NotFoundError(BaseAPIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_message = "Resource not found"
    default_code = "not_found"


class ConflictError(BaseAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_message = "Resource conflict"
    default_code = "conflict"


class UnauthorizedError(BaseAPIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_message = "Unauthorized"
    default_code = "unauthorized"


class ForbiddenError(BaseAPIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_message = "Forbidden"
    default_code = "forbidden"


class RateLimitError(BaseAPIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_message = "Rate limit exceeded"
    default_code = "rate_limit_exceeded"


class ExternalServiceError(BaseAPIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_message = "External service error"
    default_code = "external_service_error"


class WhatsAppAPIError(ExternalServiceError):
    default_message = "WhatsApp API error"
    default_code = "whatsapp_api_error"


class LangflowAPIError(ExternalServiceError):
    default_message = "Langflow API error"
    default_code = "langflow_api_error"


class WebhookValidationError(BaseAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_message = "Webhook validation failed"
    default_code = "webhook_validation_error"


class PaymentGatewayError(ExternalServiceError):
    default_message = "Payment gateway error"
    default_code = "payment_gateway_error"


def custom_exception_handler(exc, context):
    """
    Custom exception handler for DRF.

    Returns standardized error responses:
    - 400: Validation error
    - 401: Authentication failed
    - 403: Permission denied
    - 404: Not found
    - 429: Rate limit exceeded
    - 500: Server error
    """
    from rest_framework.exceptions import (
        AuthenticationFailed, PermissionDenied, NotFound,
        ValidationError as DRFValidationError, Throttled
    )

    view = context.get('view')
    request = context.get('request')

    # Call DRF's default handler first
    response = exception_handler(exc, context)

    # Handle custom BaseAPIException
    if isinstance(exc, BaseAPIException):
        logger.warning(
            f'API Exception: {exc.code}',
            extra={
                'code': exc.code,
                'message': exc.message,
                'view': view.__class__.__name__ if view else None,
                'method': request.method if request else None,
                'path': request.path if request else None,
            }
        )
        return Response(
            {
                'error': {
                    'code': exc.code,
                    'message': exc.message,
                    'details': exc.details,
                }
            },
            status=exc.status_code
        )

    # Handle specific DRF exceptions with consistent format
    if isinstance(exc, Throttled):
        return Response(
            {
                'error': {
                    'code': 'rate_limit_exceeded',
                    'message': 'Too many requests. Please try again later.',
                    'details': {'retry_after': exc.wait},
                }
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS
        )

    if isinstance(exc, PermissionDenied):
        return Response(
            {
                'error': {
                    'code': 'permission_denied',
                    'message': 'You do not have permission to perform this action.',
                    'details': {},
                }
            },
            status=status.HTTP_403_FORBIDDEN
        )

    if isinstance(exc, AuthenticationFailed):
        return Response(
            {
                'error': {
                    'code': 'authentication_failed',
                    'message': 'Authentication credentials were invalid or missing.',
                    'details': {},
                }
            },
            status=status.HTTP_401_UNAUTHORIZED
        )

    if isinstance(exc, NotFound):
        return Response(
            {
                'error': {
                    'code': 'not_found',
                    'message': 'The requested resource was not found.',
                    'details': {},
                }
            },
            status=status.HTTP_404_NOT_FOUND
        )

    if isinstance(exc, DRFValidationError):
        detalhes = response.data if response else {}
        # Sem este log, "Invalid data provided." era tudo o que existia sobre a
        # falha — no painel E no servidor. Em 11/ago a dona da loja tentou
        # lançar um pedido pelo PDV, levou a frase genérica, e não havia como
        # saber qual campo o serializer recusou nem depois, olhando o log.
        logger.warning(
            'Validação recusou %s %s: %s',
            getattr(request, 'method', '?'),
            getattr(request, 'path', '?'),
            detalhes,
            extra={
                'validation.path': getattr(request, 'path', ''),
                'validation.details': detalhes,
                'validation.view': view.__class__.__name__ if view else None,
            },
        )
        return Response(
            {
                'error': {
                    'code': 'validation_error',
                    'message': 'Invalid data provided.',
                    'details': detalhes,
                }
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # Generic handler for DRF exceptions with response
    if response is not None:
        return Response(
            {
                'error': {
                    'code': 'api_error',
                    'message': str(exc) if str(exc) else 'An error occurred',
                    'details': response.data if isinstance(response.data, dict) else {'errors': response.data},
                }
            },
            status=response.status_code
        )

    # Fallback for unhandled exceptions
    logger.error(
        f'Unhandled exception: {exc.__class__.__name__}',
        exc_info=True,
        extra={
            'view': view.__class__.__name__ if view else None,
            'method': request.method if request else None,
            'path': request.path if request else None,
        }
    )
    return Response(
        {
            'error': {
                'code': 'internal_server_error',
                'message': 'An internal server error occurred.',
                'details': {},
            }
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )
