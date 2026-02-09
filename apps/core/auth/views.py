"""
WhatsApp Authentication API Views
"""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .whatsapp_auth import WhatsAppAuthService, WhatsAppAuthError


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
    import logging
    logger = logging.getLogger(__name__)
    
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
            "id": "uuid",
            "phone": "5511999999999",
            "name": "Usuário WhatsApp",
            "is_new": false
        },
        "tokens": {
            "access": "...",
            "refresh": "..."
        }
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
        # Gera tokens JWT para o usuário
        from rest_framework_simplejwt.tokens import RefreshToken
        
        user = result['user']
        # Aqui você precisaria ter um User model Django
        # Por enquanto retornamos sem tokens
        
        return Response({
            'valid': True,
            'message': result['message'],
            'user': user,
            'phone_number': result['phone_number'],
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
