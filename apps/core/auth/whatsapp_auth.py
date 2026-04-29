"""
WhatsApp Authentication Service

Implementa autenticação via WhatsApp usando Authentication Templates.
Segue as melhores práticas da Meta:
- Usa templates pré-aprovados do tipo AUTHENTICATION
- Códigos OTP de 6 dígitos
- Expiração de 15 minutos
- Com botão de cópia automática

TROUBLESHOOTING:
- Erro #131008: Template não existe ou nome errado
- Erro #132018: Parâmetros do template não correspondem à definição
- Erro #131009: Template não encontrado
- Erro #132000: Número de parâmetros incorreto

Para resolver, verifique no Meta Business Manager:
1. Se o template existe e está aprovado
2. Se o nome do template está correto (case-sensitive)
3. Se o template tem variáveis {{1}}, {{2}}, etc.
4. Se os componentes enviados correspondem ao template
"""
import logging
import random
import string
from datetime import datetime, timedelta
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
from typing import Optional, Tuple, List

from django.contrib.auth import get_user_model
from apps.whatsapp.services import MessageService

User = get_user_model()

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
    
    # Se True, envia mensagem de texto simples como último recurso
    # Isso funciona apenas se o usuário já iniciou conversa nas últimas 24h
    USE_TEXT_FALLBACK = True
    
    # Lista de templates a tentar em ordem de preferência
    # Cada entrada tem: (nome, idioma, tem_parametro)
    # IMPORTANTE: Use apenas templates que existem e estão aprovados no Meta Business Manager
    TEMPLATE_ATTEMPTS = [
        ('codigo_verificacao', 'pt_BR', True),    # Template AUTH com {{1}}; o botão COPY_CODE vem do template aprovado
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
                # Template OTP/copy-code: o código vai no body; o botão COPY_CODE
                # já faz parte do template aprovado e não deve ser montado no payload.
                configs.append({
                    'name': template_name,
                    'language': {'code': language},
                    'components': [
                        {
                            'type': 'body',
                            'parameters': [
                                {'type': 'text', 'text': code},
                            ]
                        },
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
        logger.info(f"[WHATSAPP AUTH] Template configs: {template_configs}")
        
        # Tenta enviar com diferentes templates até um funcionar
        message_service = None
        try:
            logger.info(f"[WHATSAPP AUTH] Creating MessageService...")
            message_service = MessageService()
            logger.info(f"[WHATSAPP AUTH] MessageService created successfully")
        except Exception as init_error:
            import traceback
            logger.error(f"[WHATSAPP AUTH] Failed to initialize MessageService: {init_error}\n{traceback.format_exc()}")
            cache.delete(cache_key)
            raise WhatsAppAuthError(f"Falha ao inicializar serviço de mensagens: {init_error}")
        
        last_error = None
        last_error_details = None
        templates_tried = 0
        
        logger.info(f"[WHATSAPP AUTH] Starting template loop with {len(template_configs)} configs...")
        
        for i, template_data in enumerate(template_configs):
            templates_tried += 1
            logger.info(f"[WHATSAPP AUTH] === Attempt {i+1}/{len(template_configs)} ===")
            logger.info(f"[WHATSAPP AUTH] Template: '{template_data['name']}', Language: {template_data['language']}")
            logger.info(f"[WHATSAPP AUTH] Components: {template_data.get('components', [])}")
            
            try:
                logger.info(f"[WHATSAPP AUTH] Calling send_template_message...")
                logger.info(f"[WHATSAPP AUTH]   account_id={whatsapp_account_id}")
                logger.info(f"[WHATSAPP AUTH]   to={clean_phone}")
                logger.info(f"[WHATSAPP AUTH]   template_name={template_data['name']}")
                
                result = message_service.send_template_message(
                    account_id=whatsapp_account_id,
                    to=clean_phone,
                    template_name=template_data['name'],
                    language_code=template_data['language']['code'],
                    components=template_data.get('components')
                )
                logger.info(f"[WHATSAPP AUTH] send_template_message returned successfully: {result}")
                
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
                import traceback
                # Captura todos os detalhes possíveis do erro
                error_str = str(e) if str(e) else ''
                error_repr = repr(e)
                error_type = type(e).__name__
                error_message = getattr(e, 'message', '') if hasattr(e, 'message') else ''
                error_details = getattr(e, 'details', {}) if hasattr(e, 'details') else {}
                error_code = getattr(e, 'code', 'unknown') if hasattr(e, 'code') else 'unknown'
                error_traceback = traceback.format_exc()
                
                # Usa a melhor mensagem disponível
                final_error_str = error_str or error_message or error_repr or f"Unknown {error_type} error"
                
                logger.error(f"[WHATSAPP AUTH] Template '{template_data['name']}' EXCEPTION:")
                logger.error(f"[WHATSAPP AUTH]   Type: {error_type}")
                logger.error(f"[WHATSAPP AUTH]   str(e): '{error_str}'")
                logger.error(f"[WHATSAPP AUTH]   repr(e): '{error_repr}'")
                logger.error(f"[WHATSAPP AUTH]   e.message: '{error_message}'")
                logger.error(f"[WHATSAPP AUTH]   e.code: '{error_code}'")
                logger.error(f"[WHATSAPP AUTH]   e.details: {error_details}")
                logger.error(f"[WHATSAPP AUTH]   Traceback:\n{error_traceback}")
                
                last_error = e
                last_error_details = error_details
                
                # Se é erro de template não encontrado ou parâmetro, tenta próximo
                # Erros: 131008 (required param missing), 132018 (param issue), 131009 (not found)
                error_codes_to_retry = ['131008', '132018', '131009', '132000']
                all_error_text = f"{final_error_str} {error_code}"
                if any(ec in all_error_text for ec in error_codes_to_retry):
                    logger.info(f"[WHATSAPP AUTH] Template error (code: {error_code}), trying next configuration...")
                    # Se é erro de botão URL (131008), tenta fallback de texto imediatamente
                    if '131008' in all_error_text and cls.USE_TEXT_FALLBACK:
                        logger.info(f"[WHATSAPP AUTH] Button URL parameter error, trying text fallback immediately...")
                        break  # Sai do loop de templates para tentar texto
                    continue
                else:
                    # Erro diferente, não tenta mais templates
                    logger.warning(f"[WHATSAPP AUTH] Non-template error ({error_type}), stopping template attempts: {error_code}")
                    break
        
        # Tenta enviar mensagem de texto simples como último recurso
        # Isso só funciona se o usuário já iniciou conversa nas últimas 24h
        if cls.USE_TEXT_FALLBACK:
            logger.info(f"[WHATSAPP AUTH] Trying text message fallback...")
            try:
                text_message = f"🥗 Seu código de verificação Cê Saladas é: *{code}*\n\nEste código expira em {cls.CODE_TTL_MINUTES} minutos."
                result = message_service.send_text_message(
                    account_id=whatsapp_account_id,
                    to=clean_phone,
                    text=text_message
                )
                
                logger.info(f"[WHATSAPP AUTH] Text message sent successfully: {result}")
                
                expires_at = timezone.now() + timedelta(minutes=cls.CODE_TTL_MINUTES)
                
                response = {
                    'success': True,
                    'message': 'Código enviado com sucesso',
                    'message_id': str(result.id) if hasattr(result, 'id') else None,
                    'expires_at': expires_at.isoformat(),
                    'expires_in_minutes': cls.CODE_TTL_MINUTES,
                    'phone_number': clean_phone,
                    'template_used': 'text_fallback',
                }
                
                if settings.DEBUG:
                    response['code'] = code
                
                return response
                
            except Exception as text_error:
                text_error_str = str(text_error) if str(text_error) else repr(text_error)
                logger.warning(f"[WHATSAPP AUTH] Text fallback also failed: {text_error_str}")
                # Continue to raise the original template error
        
        # Nenhum método funcionou
        logger.error(f"[WHATSAPP AUTH] All attempts failed. Templates tried: {templates_tried}, last_error: {last_error}")
        
        if last_error:
            error_str = str(last_error) if str(last_error) else ''
            error_message_attr = getattr(last_error, 'message', '') if hasattr(last_error, 'message') else ''
            error_repr = repr(last_error)
            error_type = type(last_error).__name__
            
            error_message = error_str or error_message_attr or error_repr or f"Unknown {error_type} error"
        elif templates_tried == 0:
            error_message = "Nenhum template configurado para tentar"
        else:
            error_message = f"Erro desconhecido após {templates_tried} tentativas"
        
        if last_error_details:
            error_message = f"{error_message} - Detalhes: {last_error_details}"
        
        logger.error(f"[WHATSAPP AUTH] Final error message: {error_message}")
        
        # Invalida cache em caso de erro
        cache.delete(cache_key)
        raise WhatsAppAuthError(f"Falha ao enviar código: {error_message}")
    
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
        
        # Retorna sucesso - o usuário Django será criado/buscado no views.py
        # via _get_or_create_auth_user que já lida com UserProfile
        return {
            'valid': True,
            'message': 'Autenticação realizada com sucesso',
            'user': {
                'phone': clean_phone,
                'name': None,  # Deixar None para que o sistema use o telefone ou peça o nome depois
                'is_new': True,  # Será determinado em views.py
            },
            'phone_number': clean_phone,
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
