"""
WhatsApp Automation Service

Orquestrador principal que decide entre:
1. Templates automáticos (rápido, sem custo)
2. Consulta ao banco (dados dinâmicos)
3. Mensagens interativas (botões/listas)
4. LLM apenas quando necessário
"""
from typing import Optional, Dict, Any
import logging
from datetime import datetime

from apps.whatsapp.intents.detector import IntentDetector, IntentType, intent_detector
from apps.whatsapp.intents.handlers import (
    HandlerResult, 
    get_handler,
    HANDLER_MAP
)
from apps.whatsapp.services.whatsapp_api_service import WhatsAppAPIService
from apps.agents.services import LangchainService

logger = logging.getLogger(__name__)


class WhatsAppAutomationService:
    """
    Serviço de automação inteligente para WhatsApp
    
    Responsável por:
    - Detectar intenção do usuário
    - Escolher melhor estratégia de resposta
    - Orquestrar entre templates, handlers e LLM
    - Enviar mensagens interativas quando apropriado
    """
    
    # Intenções que NUNCA usam LLM (templates/handlers diretos)
    NO_LLM_INTENTS = [
        IntentType.GREETING,
        IntentType.PRICE_CHECK,
        IntentType.BUSINESS_HOURS,
        IntentType.DELIVERY_INFO,
        IntentType.MENU_REQUEST,
        IntentType.TRACK_ORDER,
        IntentType.PAYMENT_STATUS,
        IntentType.LOCATION,
        IntentType.CONTACT,
        IntentType.CREATE_ORDER,
        IntentType.CANCEL_ORDER,
        IntentType.HUMAN_HANDOFF,
        IntentType.FAQ,
    ]
    
    # Intenções que SEMPRE usam LLM
    LLM_REQUIRED_INTENTS = [
        IntentType.PRODUCT_INQUIRY,
        IntentType.CUSTOMIZATION,
        IntentType.COMPARISON,
        IntentType.RECOMMENDATION,
        IntentType.COMPLAINT,
        IntentType.GENERAL_QUESTION,
    ]
    
    # Intenções que podem usar ambos (decide baseado em contexto)
    HYBRID_INTENTS = [
        IntentType.MODIFY_ORDER,
        IntentType.ADD_TO_CART,
        IntentType.REQUEST_PIX,
        IntentType.CONFIRM_PAYMENT,
    ]
    
    def __init__(
        self,
        account,
        conversation,
        use_llm: bool = True,
        enable_interactive: bool = True,
        debug: bool = False
    ):
        """
        Args:
            account: WhatsAppAccount
            conversation: WhatsAppConversation
            use_llm: Se True, permite fallback para LLM
            enable_interactive: Se True, usa botões/listas da Meta API
            debug: Se True, loga informações detalhadas
        """
        self.account = account
        self.conversation = conversation
        self.use_llm = use_llm
        self.enable_interactive = enable_interactive
        self.debug = debug
        
        self.detector = IntentDetector(use_llm_fallback=use_llm)
        self.whatsapp_service = WhatsAppAPIService(account)
        
        # Estatísticas para análise
        self.stats = {
            'intents_detected': 0,
            'regex_used': 0,
            'llm_used': 0,
            'handlers_called': 0,
            'interactive_sent': 0,
        }
    
    def process_message(self, message_text: str) -> Optional[str]:
        """
        Processa mensagem do usuário e retorna resposta
        
        Fluxo:
        1. Detecta intenção (regex → LLM)
        2. Busca handler específico
        3. Executa handler
        4. Se precisar, envia mensagem interativa
        5. Se handler retornar None ou precisar de LLM, processa com LLM
        
        Returns:
            str: Texto da resposta ou marcador especial
            None: Se não houver resposta automática (ex: handoff)
        """
        if not message_text or not message_text.strip():
            logger.warning("Empty message received")
            return None
        
        clean_message = message_text.strip()
        
        if self.debug:
            logger.info(f"[Automation] Processing: {clean_message[:50]}...")
        
        # ===== 1. DETECTAR INTENÇÃO =====
        intent_data = self.detector.detect(clean_message)
        intent = intent_data['intent']
        method = intent_data['method']
        
        self.stats['intents_detected'] += 1
        if method == 'regex':
            self.stats['regex_used'] += 1
        elif method == 'llm':
            self.stats['llm_used'] += 1
        
        logger.info(
            f"[Automation] Intent: {intent.value} "
            f"(method: {method}, confidence: {intent_data['confidence']})"
        )
        
        # ===== 2. VERIFICAR SE USA HANDLER =====
        handler = get_handler(intent, self.account, self.conversation)
        
        if handler:
            self.stats['handlers_called'] += 1
            
            try:
                result = handler.handle(intent_data)
                
                if result.requires_llm and self.use_llm:
                    # Handler indica que precisa de LLM
                    logger.info("[Automation] Handler requires LLM")
                    return self._process_with_llm(clean_message, intent_data)
                
                if result.use_interactive and self.enable_interactive:
                    # Envia mensagem interativa (botões/lista)
                    self.stats['interactive_sent'] += 1
                    return self._send_interactive_message(result)
                
                if result.response_text:
                    # Retorna texto do handler
                    logger.info(f"[Automation] Handler response: {result.response_text[:50]}...")
                    return result.response_text
                
                # Handler retornou None - sem resposta automática
                logger.info("[Automation] Handler returned None")
                return None
                
            except Exception as e:
                logger.error(f"[Automation] Handler error: {str(e)}", exc_info=True)
                # Fallback para LLM em caso de erro
                if self.use_llm:
                    return self._process_with_llm(clean_message, intent_data)
                return self._get_fallback_message()
        
        # ===== 3. SEM HANDLER - DECIDE ESTRATÉGIA =====
        
        # Se é intenção que requer LLM
        if intent in self.LLM_REQUIRED_INTENTS and self.use_llm:
            return self._process_with_llm(clean_message, intent_data)
        
        # Se é unknown e permite LLM
        if intent == IntentType.UNKNOWN and self.use_llm:
            return self._process_with_llm(clean_message, intent_data)
        
        # Se é handoff, não responde
        if intent == IntentType.HUMAN_HANDOFF:
            logger.info("[Automation] Human handoff requested")
            return None
        
        # Fallback genérico
        logger.warning(f"[Automation] No handler for intent: {intent.value}")
        return self._get_fallback_message()
    
    def _send_interactive_message(self, result: HandlerResult) -> str:
        """Envia mensagem interativa (botões ou lista)"""
        
        phone_number = self.conversation.phone_number
        interactive_data = result.interactive_data
        
        try:
            if result.interactive_type == 'buttons':
                # Envia botões
                buttons = interactive_data.get('buttons', [])
                body = interactive_data.get('body', '')
                
                self.whatsapp_service.send_interactive_buttons(
                    to=phone_number,
                    body_text=body,
                    buttons=buttons
                )
                
                logger.info(f"[Automation] Sent interactive buttons to {phone_number}")
                return "BUTTONS_SENT"
                
            elif result.interactive_type == 'list':
                # Envia lista
                body = interactive_data.get('body', '')
                button = interactive_data.get('button', 'Ver opções')
                sections = interactive_data.get('sections', [])
                
                self.whatsapp_service.send_interactive_list(
                    to=phone_number,
                    body_text=body,
                    button_text=button,
                    sections=sections
                )
                
                logger.info(f"[Automation] Sent interactive list to {phone_number}")
                return "LIST_SENT"
                
        except Exception as e:
            logger.error(f"[Automation] Error sending interactive message: {e}")
            # Retorna texto como fallback
            return interactive_data.get('body', 'Desculpe, tive um problema. Pode tentar novamente?')
        
        return "INTERACTIVE_SENT"
    
    def _process_with_llm(
        self, 
        message_text: str, 
        intent_data: Dict[str, Any]
    ) -> Optional[str]:
        """Processa mensagem usando LLM (Langchain)"""
        
        if not self.account.default_agent:
            logger.warning("[Automation] No agent configured for LLM processing")
            return self._get_fallback_message()
        
        if not self.use_llm:
            logger.info("[Automation] LLM disabled, using fallback")
            return self._get_fallback_message()
        
        logger.info(f"[Automation] Processing with LLM for intent: {intent_data['intent'].value}")
        
        try:
            service = LangchainService(self.account.default_agent)
            
            result = service.process_message(
                message=message_text,
                session_id=str(self.conversation.id),
                phone_number=self.conversation.phone_number,
                conversation_id=str(self.conversation.id)
            )
            
            response = result.get('response')
            
            if response:
                logger.info(f"[Automation] LLM response: {response[:50]}...")
                return response
            else:
                logger.warning("[Automation] LLM returned empty response")
                return self._get_fallback_message()
                
        except Exception as e:
            logger.error(f"[Automation] LLM processing error: {str(e)}", exc_info=True)
            return self._get_fallback_message()
    
    def _get_fallback_message(self) -> str:
        """Retorna mensagem de fallback quando não consegue processar"""
        
        fallbacks = [
            "Desculpe, não entendi direito. 😕\n\nPode reformular ou escolher uma opção:",
            "Hmm, não consegui entender. 🤔\n\nQuer ver nosso cardápio?",
            "Desculpe, estou com dificuldades. 😅\n\nComo posso ajudar?",
        ]
        
        # Alterna entre mensagens para não ficar repetitivo
        index = self.stats['intents_detected'] % len(fallbacks)
        return fallbacks[index]
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do serviço"""
        return {
            **self.stats,
            'timestamp': datetime.now().isoformat(),
        }
    
    def reset_stats(self):
        """Reseta estatísticas"""
        self.stats = {
            'intents_detected': 0,
            'regex_used': 0,
            'llm_used': 0,
            'handlers_called': 0,
            'interactive_sent': 0,
        }


def process_whatsapp_message(
    account,
    conversation,
    message_text: str,
    use_llm: bool = True,
    enable_interactive: bool = True
) -> Optional[str]:
    """
    Função utilitária para processar mensagem do WhatsApp
    
    Args:
        account: WhatsAppAccount
        conversation: WhatsAppConversation
        message_text: Texto da mensagem
        use_llm: Se True, permite uso de LLM como fallback
        enable_interactive: Se True, usa botões/listas
    
    Returns:
        str: Resposta ou marcador especial
        None: Se não houver resposta automática
    """
    service = WhatsAppAutomationService(
        account=account,
        conversation=conversation,
        use_llm=use_llm,
        enable_interactive=enable_interactive
    )
    
    return service.process_message(message_text)
