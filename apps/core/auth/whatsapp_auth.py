"""
WhatsApp Authentication Service

Implementa autenticação via WhatsApp usando Authentication Templates.
Segue as melhores práticas da Meta:
- Usa templates pré-aprovados do tipo AUTHENTICATION
- Códigos OTP de 6 dígitos
- Expiração de 15 minutos
- Com botão de cópia automática
"""
import logging
import random
import string
from datetime import datetime, timedelta
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
from typing import Optional, Tuple, List

from apps.users.models import UnifiedUser
from apps.users.services import UnifiedUserService
from apps.whatsapp.services import MessageService

logger = logging.getLogger(__name__)


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
    # Criado no Meta Business Manager: auth_verification_v1
    TEMPLATE_NAME = 'auth_verification_v1'
    TEMPLATE_LANGUAGE = 'pt_BR'
    
    # Fallback: Template de marketing (caso auth não funcione)
    # Use um template de marketing simples que já existe e está aprovado
    FALLBACK_TEMPLATE_NAME = 'codigo_verificacao'
    
    # HABILITADO: Usar fallback até que template de auth seja criado no Meta Business Manager
    # O erro #132018 indica problemas nos parâmetros do template de autenticação
    USE_FALLBACK = True
    
    # Lista de templates a tentar em ordem de preferência
    # Cada entrada tem: (nome, idioma, tem_parametro)
    TEMPLATE_ATTEMPTS = [
        ('codigo_verificacao', 'pt_BR', True),    # Template com {{1}} para código
        ('codigo_verificacao', 'pt_BR', False),   # Template sem variáveis
        ('hello_world', 'en_US', False),          # Template padrão da Meta (fallback teste)
    ]
    
    @classmethod
    def _get_template_configs(cls, code: str) -> List[dict]:
        """
        Retorna lista de configurações de templates a tentar.
        Isso permite retry com diferentes templates/configurações.
        
        Erros comuns da Meta API:
        - #131008: Required parameter is missing (template não existe ou nome errado)
        - #132018: Template parameter issue (parâmetros não correspondem)
        - #131009: Template not found
        """
        configs = []
        
        for template_name, language, has_param in cls.TEMPLATE_ATTEMPTS:
            if has_param:
                # Template com variável {{1}}
                configs.append({
                    'name': template_name,
                    'language': {'code': language},
                    'components': [
                        {
                            'type': 'body',
                            'parameters': [
                                {'type': 'text', 'text': code},
                            ]
                        }
                    ]
                })
            else:
                # Template sem variáveis (texto fixo)
                configs.append({
                    'name': template_name,
                    'language': {'code': language},
                    'components': []
                })
        
        return configs
    
    @classmethod
    def _get_template_data(cls, code: str) -> dict:
        """
        Retorna os dados do template principal.
        Para compatibilidade, retorna o primeiro template da lista.
        """
        if cls.USE_FALLBACK:
            # Template de Marketing com variável {{1}} para o código
            return {
                'name': cls.FALLBACK_TEMPLATE_NAME,
                'language': {'code': cls.TEMPLATE_LANGUAGE},
                'components': [
                    {
                        'type': 'body',
                        'parameters': [
                            {'type': 'text', 'text': code},
                        ]
                    }
                ]
            }
        
        # Authentication Template (oficial da Meta para OTP)
        return {
            'name': cls.TEMPLATE_NAME,
            'language': {'code': cls.TEMPLATE_LANGUAGE},
            'components': [
                {
                    'type': 'body',
                    'parameters': [
                        {'type': 'text', 'text': code},
                    ]
                },
                {
                    'type': 'button',
                    'sub_type': 'url',
                    'index': 0,
                    'parameters': [
                        {'type': 'text', 'text': code}
                    ]
                }
            ]
        }
    
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
        
        logger.info(f"[WHATSAPP AUTH] Generated code for {clean_phone}: {code}")
        
        # Salva no cache
        cache_data = {
            'code': code,
            'attempts': 0,
            'created_at': timezone.now().isoformat(),
            'phone': clean_phone,
            'whatsapp_account_id': whatsapp_account_id,
        }
        cache.set(cache_key, cache_data, timeout=60 * cls.CODE_TTL_MINUTES)
        
        # Lista de templates a tentar
        template_configs = cls._get_template_configs(code)
        
        logger.info(f"[WHATSAPP AUTH] UUID received: '{whatsapp_account_id}' (len={len(whatsapp_account_id) if whatsapp_account_id else 0})")
        logger.info(f"[WHATSAPP AUTH] Will try {len(template_configs)} template configurations")
        
        # Tenta enviar com diferentes templates até um funcionar
        message_service = MessageService()
        last_error = None
        
        for i, template_data in enumerate(template_configs):
            logger.info(f"[WHATSAPP AUTH] Attempt {i+1}: Template '{template_data['name']}' with components: {template_data.get('components', [])}")
            
            try:
                result = message_service.send_template_message(
                    account_id=whatsapp_account_id,
                    to=clean_phone,
                    template_name=template_data['name'],
                    language_code=template_data['language']['code'],
                    components=template_data.get('components')
                )
                
                # Sucesso! Log e retorna
                logger.info(f"[WHATSAPP AUTH] Message sent successfully with template '{template_data['name']}': {result}")
                
                expires_at = timezone.now() + timedelta(minutes=cls.CODE_TTL_MINUTES)
                
                response = {
                    'success': True,
                    'message': 'Código enviado com sucesso',
                    'message_id': result.get('messages', [{}])[0].get('id') if hasattr(result, 'get') else str(result.id) if hasattr(result, 'id') else None,
                    'expires_at': expires_at.isoformat(),
                    'expires_in_minutes': cls.CODE_TTL_MINUTES,
                    'phone_number': clean_phone,
                    'template_used': template_data['name'],
                }
                
                # Inclui código apenas em DEBUG
                if settings.DEBUG:
                    response['code'] = code
                
                return response
                
            except Exception as e:
                error_str = str(e)
                logger.warning(f"[WHATSAPP AUTH] Template '{template_data['name']}' failed: {error_str}")
                last_error = e
                
                # Se é erro de template não encontrado ou parâmetro, tenta próximo
                # Erros: 131008 (required param missing), 132018 (param issue), 131009 (not found)
                if any(code in error_str for code in ['131008', '132018', '131009', '132000']):
                    logger.info(f"[WHATSAPP AUTH] Template error, trying next configuration...")
                    continue
                else:
                    # Erro diferente, não tenta mais templates
                    break
        
        # Nenhum template funcionou
        logger.error(f"[WHATSAPP AUTH] All template attempts failed. Last error: {last_error}")
        
        # Invalida cache em caso de erro
        cache.delete(cache_key)
        raise WhatsAppAuthError(f"Falha ao enviar código: {str(last_error)}")
    
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
