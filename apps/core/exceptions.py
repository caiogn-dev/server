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
    """Custom exception handler for DRF."""
    response = exception_handler(exc, context)

    if isinstance(exc, BaseAPIException):
        logger.error(
            f"API Exception: {exc.code} - {exc.message}",
            extra={
                'code': exc.code,
                'details': exc.details,
                'view': context.get('view').__class__.__name__ if context.get('view') else None,
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

    if response is not None:
        response.data = {
            'error': {
                'code': 'api_error',
                'message': str(exc),
                'details': response.data if isinstance(response.data, dict) else {'errors': response.data},
            }
        }

    return response
