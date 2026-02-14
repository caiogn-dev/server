"""
WhatsApp Authentication API Views
"""
import logging

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .whatsapp_auth import WhatsAppAuthService, WhatsAppAuthError

logger = logging.getLogger(__name__)


def _normalize_phone(phone_number):
    """Normalize phone to digits only."""
    return ''.join(ch for ch in str(phone_number or '') if ch.isdigit())


def _phone_candidates(phone_number):
    """Return candidate phone formats to match existing profiles."""
    digits = _normalize_phone(phone_number)
    if not digits:
        return []

    candidates = {digits, f'+{digits}'}

    # Common local variation: without Brazil country code.
    if digits.startswith('55') and len(digits) > 11:
        local_digits = digits[2:]
        candidates.add(local_digits)
        candidates.add(f'+{local_digits}')

    return list(candidates)


def _split_name(full_name):
    parts = (full_name or '').strip().split(' ', 1)
    first_name = parts[0] if parts and parts[0] else ''
    last_name = parts[1] if len(parts) > 1 else ''
    return first_name, last_name


def _generate_unique_username(base_username):
    User = get_user_model()

    cleaned = ''.join(
        ch if ch.isalnum() else '_'
        for ch in (base_username or 'wa_user')
    ).strip('_').lower() or 'wa_user'
    cleaned = cleaned[:24]

    username = cleaned
    counter = 1
    while User.objects.filter(username=username).exists():
        suffix = str(counter)
        username = f"{cleaned[:max(1, 24 - len(suffix))]}{suffix}"
        counter += 1

    return username


def _get_or_create_auth_user(whatsapp_user, phone_number):
    """
    Resolve a Django auth user from WhatsApp login and ensure a UserProfile exists.
    """
    from apps.core.models import UserProfile

    User = get_user_model()
    phone_digits = _normalize_phone(phone_number)
    phone_formats = _phone_candidates(phone_number)

    profile = UserProfile.objects.select_related('user').filter(phone__in=phone_formats).first()
    user_created = False

    if profile:
        user = profile.user
    else:
        generated_email = f"{phone_digits}@pastita.local" if phone_digits else ''
        local_digits = phone_digits[2:] if phone_digits.startswith('55') and len(phone_digits) > 11 else ''
        alt_email = f"{local_digits}@pastita.local" if local_digits else ''
        email_candidates = [email for email in [generated_email, alt_email] if email]

        user = User.objects.filter(email__in=email_candidates).first() if email_candidates else None
        if not user:
            wa_name = whatsapp_user.get('name', '') if isinstance(whatsapp_user, dict) else ''
            first_name, last_name = _split_name(wa_name)

            username = _generate_unique_username(f"wa_{phone_digits or 'user'}")
            email = generated_email or f"{username}@pastita.local"

            user = User.objects.create_user(
                username=username,
                email=email,
                password=User.objects.make_random_password(),
                first_name=first_name,
                last_name=last_name,
            )
            user_created = True

        profile, _ = UserProfile.objects.get_or_create(user=user)

    if phone_digits and profile.phone != phone_digits:
        profile.phone = phone_digits
        profile.save(update_fields=['phone'])

    wa_name = whatsapp_user.get('name', '') if isinstance(whatsapp_user, dict) else ''
    first_name, last_name = _split_name(wa_name)
    updated_fields = []

    if first_name and not user.first_name:
        user.first_name = first_name
        updated_fields.append('first_name')
    if last_name and not user.last_name:
        user.last_name = last_name
        updated_fields.append('last_name')

    if updated_fields:
        user.save(update_fields=updated_fields)

    return user, profile, user_created


@api_view(['POST'])
@permission_classes([AllowAny])
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
    account_id = request.data.get('whatsapp_account_id')
    
    logger.info(f"[WHATSAPP AUTH API] Request to send code to: {phone}")
    
    if not phone:
        return Response(
            {'error': 'phone_number é obrigatório'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if not account_id:
        return Response(
            {'error': 'whatsapp_account_id é obrigatório'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        result = WhatsAppAuthService.send_auth_code(phone, account_id)
        
        if result.get('success'):
            # Em desenvolvimento, retorna o código para facilitar testes
            from django.conf import settings
            if settings.DEBUG:
                logger.info(f"[WHATSAPP AUTH API] Code sent (DEBUG mode): {result.get('code')}")
            else:
                # Remove código do response em produção
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
            user, profile, user_created = _get_or_create_auth_user(
                whatsapp_user=whatsapp_user,
                phone_number=result.get('phone_number') or phone
            )
            token, _ = Token.objects.get_or_create(user=user)
        except Exception as exc:
            logger.exception(f"[WHATSAPP AUTH API] Failed to create auth token: {exc}")
            return Response(
                {'error': 'auth_error', 'message': 'Falha ao autenticar usuário'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        display_name = (
            f"{user.first_name} {user.last_name}".strip()
            or whatsapp_user.get('name')
            or user.username
        )

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
    account_id = request.data.get('whatsapp_account_id')
    
    if not phone or not account_id:
        return Response(
            {'error': 'phone_number e whatsapp_account_id são obrigatórios'},
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
