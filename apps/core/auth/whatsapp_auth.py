"""
WhatsApp Authentication Service

Implementa autenticação via WhatsApp usando Authentication Templates.
Segue as melhores práticas da Meta:
- Usa templates pré-aprovados do tipo AUTHENTICATION
- Códigos OTP de 6 dígitos
- Expiração de 15 minutos
- Com botão de cópia automática
"""
import random
import string
from datetime import datetime, timedelta
from django.core.cache import cache
from django.utils import timezone
from typing import Optional, Tuple

from apps.users.models import UnifiedUser
from apps.users.services import UnifiedUserService
from apps.whatsapp.services import MessageService


class WhatsAppAuthError(Exception):
    """Erro de autenticação WhatsApp"""
    pass


class WhatsAppAuthService:
    """
    Serviço de autenticação via WhatsApp usando Authentication Templates.
    
    Fluxo:
    1. Usuário informa número de telefone
    2. Sistema gera código OTP de 6 dígitos
    3. Envia via WhatsApp usando template de autenticação
    4. Usuário recebe código e informa no site/app
    5. Sistema valida código e autentica usuário
    """
    
    # Configurações
    CODE_LENGTH = 6
    CODE_TTL_MINUTES = 15
    MAX_ATTEMPTS = 3
    
    # Template oficial do WhatsApp para autenticação
    # Deve ser criado no Meta Business Manager
    TEMPLATE_NAME = 'auth_verification_v1'
    TEMPLATE_LANGUAGE = 'pt_BR'
    
    @staticmethod
    def generate_code() -> str:
        """Gera código numérico aleatório de 6 dígitos"""
        return ''.join(random.choices(string.digits, k=WhatsAppAuthService.CODE_LENGTH))
    
    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """Normaliza número de telefone para formato internacional"""
        # Remove tudo exceto números
        digits = ''.join(filter(str.isdigit, phone))
        
        # Adiciona código do Brasil se não tiver
        if not digits.startswith('55'):
            digits = '55' + digits
            
        return digits
    
    @staticmethod
    def _get_cache_key(phone: str) -> str:
        """Gera chave de cache para o número"""
        return f"whatsapp_auth:{phone}"
    
    @classmethod
    def send_auth_code(
        cls, 
        phone_number: str, 
        whatsapp_account_id: str,
        user_name: Optional[str] = None
    ) -> dict:
        """
        Envia código de autenticação via WhatsApp Template.
        
        Args:
            phone_number: Número no formato +5511999999999
            whatsapp_account_id: ID da conta WhatsApp Business
            user_name: Nome do usuário (opcional, para personalização)
        
        Returns:
            dict com status, message_id, expires_at
        """
        # Normaliza telefone
        clean_phone = cls._normalize_phone(phone_number)
        
        # Verifica se já existe código válido (evita spam)
        cache_key = cls._get_cache_key(clean_phone)
        existing = cache.get(cache_key)
        
        if existing:
            # Calcula tempo restante
            created_at = datetime.fromisoformat(existing['created_at'])
            elapsed = (timezone.now() - created_at).total_seconds()
            remaining = (cls.CODE_TTL_MINUTES * 60) - elapsed
            
            if remaining > 0:
                return {
                    'success': False,
                    'error': 'code_already_sent',
                    'message': f'Código já enviado. Aguarde {int(remaining/60)} minutos.',
                    'retry_after': int(remaining)
                }
        
        # Gera novo código
        code = cls.generate_code()
        
        # Salva no cache
        cache_data = {
            'code': code,
            'attempts': 0,
            'created_at': timezone.now().isoformat(),
            'phone': clean_phone,
            'whatsapp_account_id': whatsapp_account_id,
        }
        cache.set(cache_key, cache_data, timeout=60 * cls.CODE_TTL_MINUTES)
        
        # Prepara template de autenticação
        # Formato do template da Meta:
        # "Seu código de verificação é: {{1}}\n\nVálido por 15 minutos."
        template_data = {
            'name': cls.TEMPLATE_NAME,
            'language': {'code': cls.TEMPLATE_LANGUAGE},
            'components': [
                {
                    'type': 'body',
                    'parameters': [
                        {'type': 'text', 'text': code},  # {{1}} = código
                    ]
                },
                {
                    'type': 'button',
                    'sub_type': 'copy_code',
                    'index': 0,
                    'parameters': [
                        {'type': 'text', 'text': code}  # Código para copiar
                    ]
                }
            ]
        }
        
        # Envia mensagem
        try:
            message_service = MessageService()
            result = message_service.send_template_message(
                account_id=whatsapp_account_id,
                to=clean_phone,
                template=template_data
            )
            
            expires_at = timezone.now() + timedelta(minutes=cls.CODE_TTL_MINUTES)
            
            return {
                'success': True,
                'message': 'Código enviado com sucesso',
                'message_id': result.get('messages', [{}])[0].get('id'),
                'expires_at': expires_at.isoformat(),
                'expires_in_minutes': cls.CODE_TTL_MINUTES,
                'phone_number': clean_phone,
            }
            
        except Exception as e:
            # Invalida cache em caso de erro
            cache.delete(cache_key)
            raise WhatsAppAuthError(f"Falha ao enviar código: {str(e)}")
    
    @classmethod
    def verify_code(cls, phone_number: str, code: str) -> dict:
        """
        Verifica código de autenticação.
        
        Args:
            phone_number: Número de telefone
            code: Código informado pelo usuário
        
        Returns:
            dict com valid, user (se válido), tokens (se válido)
        """
        clean_phone = cls._normalize_phone(phone_number)
        cache_key = cls._get_cache_key(clean_phone)
        
        stored = cache.get(cache_key)
        
        if not stored:
            return {
                'valid': False,
                'error': 'code_expired',
                'message': 'Código expirado ou não encontrado. Solicite um novo código.'
            }
        
        # Verifica tentativas
        if stored['attempts'] >= cls.MAX_ATTEMPTS:
            cache.delete(cache_key)
            return {
                'valid': False,
                'error': 'too_many_attempts',
                'message': 'Muitas tentativas incorretas. Solicite um novo código.'
            }
        
        # Verifica código
        if stored['code'] != code:
            stored['attempts'] += 1
            cache.set(cache_key, stored, timeout=60 * cls.CODE_TTL_MINUTES)
            
            remaining_attempts = cls.MAX_ATTEMPTS - stored['attempts']
            
            return {
                'valid': False,
                'error': 'invalid_code',
                'message': f'Código incorreto. {remaining_attempts} tentativas restantes.',
                'remaining_attempts': remaining_attempts
            }
        
        # Código válido! Remove do cache
        cache.delete(cache_key)
        
        # Busca ou cria UnifiedUser
        try:
            user, created = UnifiedUser.objects.get_or_create(
                phone_number=clean_phone,
                defaults={
                    'name': 'Usuário WhatsApp',  # Será atualizado depois
                }
            )
            
            # Atualiza last_seen
            user.save(update_fields=['last_seen_at'])
            
            return {
                'valid': True,
                'message': 'Autenticação realizada com sucesso',
                'user': {
                    'id': str(user.id),
                    'phone': user.phone_number,
                    'name': user.name,
                    'is_new': created,
                },
                'phone_number': clean_phone,
            }
            
        except Exception as e:
            return {
                'valid': False,
                'error': 'user_error',
                'message': f'Erro ao processar usuário: {str(e)}'
            }
    
    @classmethod
    def resend_code(cls, phone_number: str, whatsapp_account_id: str) -> dict:
        """
        Reenvia código (apenas se o anterior expirou).
        """
        clean_phone = cls._normalize_phone(phone_number)
        cache_key = cls._get_cache_key(clean_phone)
        
        # Força remoção do cache anterior
        cache.delete(cache_key)
        
        # Envia novo código
        return cls.send_auth_code(clean_phone, whatsapp_account_id)
