"""
WhatsApp Authentication API Views
"""
import logging

from django.conf import settings
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle


class WhatsAppAuthThrottle(AnonRateThrottle):
    """10 requests/minute per IP — same scope as other auth endpoints."""
    scope = 'auth'

from apps.core.services.customer_identity import CustomerIdentityService

from .whatsapp_auth import WhatsAppAuthService, WhatsAppAuthError

logger = logging.getLogger(__name__)


def _resolve_whatsapp_account_id(account_id: str | None = None) -> str:
    """
    Resolve the WhatsApp account to use for OTP flows.

    Compatibility:
    - Keeps supporting explicit `whatsapp_account_id` from the client.
    - Falls back to `DEFAULT_WHATSAPP_ACCOUNT_ID` when configured.
    - Falls back to a single active WhatsApp account when only one exists.
    """
    candidate = str(account_id or '').strip()
    if candidate:
        return candidate

    default_account_id = str(getattr(settings, 'DEFAULT_WHATSAPP_ACCOUNT_ID', '') or '').strip()
    if default_account_id:
        return default_account_id

    from apps.whatsapp.models import WhatsAppAccount

    account = WhatsAppAccount.objects.filter(is_active=True).order_by('created_at').first()
    return str(account.id) if account else ''


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([WhatsAppAuthThrottle])
def send_whatsapp_auth_code(request):
    """
    Envia código de autenticação para número de WhatsApp.
    
    POST /api/v1/auth/whatsapp/send/
    {
        "phone_number": "+5511999999999",
        "whatsapp_account_id": "uuid-da-conta-whatsapp"
    }
    
    Response:
    {
        "success": true,
        "message": "Código enviado com sucesso",
        "message_id": "wamid....",
        "expires_at": "2024-01-01T12:15:00Z",
        "expires_in_minutes": 15,
        "phone_number": "5511999999999",
        "code": "123456"  # Apenas em DEBUG
    }
    """
    phone = request.data.get('phone_number')
    account_id = _resolve_whatsapp_account_id(request.data.get('whatsapp_account_id'))
    
    logger.info(f"[WHATSAPP AUTH API] Request to send code to: {phone}")
    
    if not phone:
        return Response(
            {'error': 'phone_number é obrigatório'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if not account_id:
        return Response(
            {'error': 'Nenhuma conta WhatsApp disponível para autenticação'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        result = WhatsAppAuthService.send_auth_code(phone, account_id)
        
        if result.get('success'):
            from django.conf import settings
            if settings.DEBUG:
                logger.debug(f"[WHATSAPP AUTH API] Code sent: {result.get('code')}")
            # Never expose the OTP code in the API response
            result.pop('code', None)
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_429_TOO_MANY_REQUESTS)
            
    except WhatsAppAuthError as e:
        logger.error(f"[WHATSAPP AUTH API] Error: {str(e)}")
        return Response(
            {'error': 'send_error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([WhatsAppAuthThrottle])
def verify_whatsapp_auth_code(request):
    """
    Verifica código de autenticação e autentica usuário.
    
    POST /api/v1/auth/whatsapp/verify/
    {
        "phone_number": "+5511999999999",
        "code": "123456"
    }
    
    Response (sucesso):
    {
        "valid": true,
        "message": "Autenticação realizada com sucesso",
        "user": {
            "id": 123,
            "phone": "5511999999999",
            "name": "Usuário WhatsApp",
            "is_new": false
        },
        "token": "drf_authtoken",
        "token_type": "Token"
    }
    
    Response (erro):
    {
        "valid": false,
        "error": "invalid_code",
        "message": "Código incorreto. 2 tentativas restantes.",
        "remaining_attempts": 2
    }
    """
    phone = request.data.get('phone_number')
    code = request.data.get('code')
    
    if not phone or not code:
        return Response(
            {'error': 'phone_number e code são obrigatórios'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    result = WhatsAppAuthService.verify_code(phone, code)
    
    if result['valid']:
        whatsapp_user = result.get('user') or {}

        try:
            user, profile, user_created = CustomerIdentityService.resolve_user(
                email='',
                phone=result.get('phone_number') or phone,
                full_name=whatsapp_user.get('name', '') if isinstance(whatsapp_user, dict) else '',
                create=True,
            )
            token, _ = Token.objects.get_or_create(user=user)
        except Exception as exc:
            logger.exception(f"[WHATSAPP AUTH API] Failed to create auth token: {exc}")
            return Response(
                {'error': 'auth_error', 'message': 'Falha ao autenticar usuário'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        display_name = f"{user.first_name} {user.last_name}".strip() or whatsapp_user.get('name') or ''
        if not display_name or display_name.lower().startswith('cliente_'):
            display_name = profile.phone or result.get('phone_number') or ''

        return Response({
            'valid': True,
            'message': result['message'],
            'user': {
                'id': user.id,
                'phone': profile.phone or result.get('phone_number'),
                'name': display_name,
                'is_new': user_created,
            },
            'phone_number': result['phone_number'],
            'token': token.key,
            'token_type': 'Token',
            # Compatibilidade temporária para clientes que ainda esperam "tokens.access".
            'tokens': {
                'access': token.key,
                'refresh': None,
            },
        })
    
    return Response(result, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([WhatsAppAuthThrottle])
def resend_whatsapp_auth_code(request):
    """
    Reenvia código de autenticação (após expiração).
    
    POST /api/v1/auth/whatsapp/resend/
    {
        "phone_number": "+5511999999999",
        "whatsapp_account_id": "uuid-da-conta-whatsapp"
    }
    """
    phone = request.data.get('phone_number')
    account_id = _resolve_whatsapp_account_id(request.data.get('whatsapp_account_id'))

    if not phone or not account_id:
        return Response(
            {'error': 'phone_number é obrigatório e nenhuma conta WhatsApp está disponível'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        result = WhatsAppAuthService.resend_code(phone, account_id)
        
        if result.get('success'):
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_429_TOO_MANY_REQUESTS)
            
    except WhatsAppAuthError as e:
        return Response(
            {'error': 'send_error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
