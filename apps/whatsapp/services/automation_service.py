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

import time

from apps.whatsapp.intents.detector import IntentDetector, IntentType, intent_detector
from apps.whatsapp.intents.handlers import (
    HandlerResult,
    get_handler,
    HANDLER_MAP
)
from apps.whatsapp.services.whatsapp_api_service import WhatsAppAPIService
from apps.agents.services import LangchainService
from apps.automation.models import IntentLog
from apps.automation.services import SessionManager, get_session_manager

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
    
    # Intenções que SEMPRE usam LLM - DESATIVADO para evitar alucinações
    LLM_REQUIRED_INTENTS = []
    
    # Intenções que podem usar ambos - DESATIVADO
    HYBRID_INTENTS = []
    
    def __init__(
        self,
        account,
        conversation,
        use_llm: bool = False,  # DESATIVADO por padrão
        enable_interactive: bool = True,
        debug: bool = False
    ):
        """
        Args:
            account: WhatsAppAccount
            conversation: WhatsAppConversation
            use_llm: DESATIVADO - Não usa LLM para evitar alucinações
            enable_interactive: Se True, usa botões/listas da Meta API
            debug: Se True, loga informações detalhadas
        """
        self.account = account
        self.conversation = conversation
        self.use_llm = False  # SEMPRE False - não usa LLM
        self.enable_interactive = enable_interactive
        self.debug = debug
        
        # Detector SEM LLM fallback
        self.detector = IntentDetector(use_llm_fallback=False)
        self.whatsapp_service = WhatsAppAPIService(account)
        
        # Gerenciador de sessão para manter contexto
        self.session_manager = None
        if conversation:
            self.session_manager = get_session_manager(
                account, 
                conversation.phone_number
            )
        
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
        # Marca tempo de início para métricas
        start_time = time.time()

        if not message_text or not message_text.strip():
            logger.warning("Empty message received")
            return None

        clean_message = message_text.strip().lower()

        if self.debug:
            logger.info(f"[Automation] Processing: {clean_message[:50]}...")

        # ===== 0. VERIFICAR COMANDOS ESPECIAIS E CONTEXTO =====
        # Verifica se há sessão ativa
        if self.session_manager:
            session_data = self.session_manager.get_session_data()
            
            # Comandos para resetar/encerrar fluxo
            reset_commands = ['cancelar', 'sair', 'resetar', 'novo pedido', 'começar', 'comecar', 'reiniciar']
            if any(cmd in clean_message for cmd in reset_commands):
                self.session_manager.reset_session()
                logger.info("[Automation] Session reset by user command")
                return "🔄 *Fluxo reiniciado!*\n\nComo posso ajudar você agora?"
            
            # Verifica se há pedido em andamento
            if self.session_manager.is_order_in_progress():
                # Se está em fluxo de pedido e tenta fazer outra coisa
                if intent_data['intent'] not in [IntentType.CREATE_ORDER, IntentType.ADD_TO_CART, 
                                                  IntentType.MODIFY_ORDER, IntentType.CANCEL_ORDER,
                                                  IntentType.CONFIRM_PAYMENT]:
                    logger.info(f"[Automation] User in order flow but sent: {clean_message[:30]}")
                    # Permite continuar mas mantém o contexto
            
            # Verifica se há pagamento pendente
            if self.session_manager.is_payment_pending():
                # Se usuário envia comprovante ou confirma pagamento
                if any(word in clean_message for word in ['paguei', 'comprovante', 'pago', 'transferi']):
                    logger.info("[Automation] Payment confirmation detected")
                    self.session_manager.confirm_payment()
                    return "✅ *Obrigado!*\n\nVamos verificar seu pagamento. Assim que for confirmado, avisaremos você!"

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

        # Variáveis para logging
        handler_used = ""
        response_text = ""
        response_type = "text"
        final_result = None

        # ===== 2. VERIFICAR SE USA HANDLER =====
        handler = get_handler(intent, self.account, self.conversation)

        if handler:
            self.stats['handlers_called'] += 1
            handler_used = handler.__class__.__name__

            try:
                result = handler.handle(intent_data)

                if result.requires_llm and self.use_llm:
                    # Handler indica que precisa de LLM
                    logger.info("[Automation] Handler requires LLM")
                    final_result = self._process_with_llm(clean_message, intent_data)
                    response_text = final_result or ""
                    response_type = "llm_fallback"
                    self._log_intent(intent_data, handler_used, response_text, response_type, start_time)
                    return final_result

                if result.use_interactive and self.enable_interactive:
                    # Envia mensagem interativa (botões/lista)
                    self.stats['interactive_sent'] += 1
                    final_result = self._send_interactive_message(result)
                    response_text = result.interactive_data.get('body', '')
                    response_type = result.interactive_type or "interactive"
                    self._log_intent(intent_data, handler_used, response_text, response_type, start_time)
                    return final_result

                if result.response_text:
                    # Retorna texto do handler
                    logger.info(f"[Automation] Handler response: {result.response_text[:50]}...")
                    final_result = result.response_text
                    response_text = final_result
                    response_type = "text"
                    self._log_intent(intent_data, handler_used, response_text, response_type, start_time)
                    return final_result

                # Handler retornou None - sem resposta automática
                logger.info("[Automation] Handler returned None")
                self._log_intent(intent_data, handler_used, "", "none", start_time)
                return None

            except Exception as e:
                logger.error(f"[Automation] Handler error: {str(e)}", exc_info=True)
                # Fallback para LLM em caso de erro
                if self.use_llm:
                    final_result = self._process_with_llm(clean_message, intent_data)
                    response_text = final_result or ""
                    response_type = "llm_error_fallback"
                    self._log_intent(intent_data, handler_used, response_text, response_type, start_time, error=str(e))
                    return final_result
                final_result = self._get_fallback_message()
                response_text = final_result
                response_type = "error_fallback"
                self._log_intent(intent_data, handler_used, response_text, response_type, start_time, error=str(e))
                return final_result

        # ===== 3. SEM HANDLER - DECIDE ESTRATÉGIA =====

        # Se é intenção que requer LLM
        if intent in self.LLM_REQUIRED_INTENTS and self.use_llm:
            final_result = self._process_with_llm(clean_message, intent_data)
            response_text = final_result or ""
            response_type = "llm"
            self._log_intent(intent_data, "LLM", response_text, response_type, start_time)
            return final_result

        # Se é unknown e permite LLM
        if intent == IntentType.UNKNOWN and self.use_llm:
            final_result = self._process_with_llm(clean_message, intent_data)
            response_text = final_result or ""
            response_type = "llm"
            self._log_intent(intent_data, "LLM", response_text, response_type, start_time)
            return final_result

        # Se é handoff, não responde
        if intent == IntentType.HUMAN_HANDOFF:
            logger.info("[Automation] Human handoff requested")
            self._log_intent(intent_data, "HumanHandoff", "", "handoff", start_time)
            return None

        # Fallback genérico
        logger.warning(f"[Automation] No handler for intent: {intent.value}")
        final_result = self._get_fallback_message()
        response_text = final_result
        response_type = "fallback"
        self._log_intent(intent_data, "None", response_text, response_type, start_time)
        return final_result
    
    def _send_interactive_message(self, result: HandlerResult) -> str:
        """Envia mensagem interativa (botões ou lista)"""

        phone_number = self.conversation.phone_number
        interactive_data = result.interactive_data

        logger.info(f"[_send_interactive_message] Starting - type: {result.interactive_type}, phone: {phone_number}")
        logger.info(f"[_send_interactive_message] Interactive data: {interactive_data}")

        try:
            if result.interactive_type == 'buttons':
                # Envia botões
                buttons = interactive_data.get('buttons', [])
                body = interactive_data.get('body', '')
                header = interactive_data.get('header')
                footer = interactive_data.get('footer')

                logger.info(f"[_send_interactive_message] Buttons: {buttons}")
                logger.info(f"[_send_interactive_message] Body length: {len(body)}")
                logger.info(f"[_send_interactive_message] Header: {header}")
                logger.info(f"[_send_interactive_message] Footer: {footer}")

                # Monta header no formato da API
                header_payload = None
                if header:
                    header_payload = {
                        'type': 'text',
                        'text': header
                    }

                logger.info(f"[_send_interactive_message] Calling send_interactive_buttons...")
                response = self.whatsapp_service.send_interactive_buttons(
                    to=phone_number,
                    body_text=body,
                    buttons=buttons,
                    header=header_payload,
                    footer=footer
                )

                logger.info(f"[_send_interactive_message] Response: {response}")
                logger.info(f"[Automation] Sent interactive buttons to {phone_number}")
                
            elif result.interactive_type == 'list':
                # Envia lista
                body = interactive_data.get('body', '')
                button = interactive_data.get('button', 'Ver opções')
                sections = interactive_data.get('sections', [])
                
                logger.info(f"[_send_interactive_message] List sections: {len(sections)}")
                
                # Valida seções
                if not sections:
                    logger.warning("[_send_interactive_message] Sem seções, retornando texto")
                    return body or "Cardápio disponível!"
                
                # Conta total de linhas
                total_rows = sum(len(s.get('rows', [])) for s in sections)
                logger.info(f"[_send_interactive_message] Total rows: {total_rows}")
                
                if total_rows == 0:
                    logger.warning("[_send_interactive_message] Seções vazias, retornando texto")
                    return body or "Cardápio disponível!"
                
                # Limita a 10 linhas (limite da API do WhatsApp)
                if total_rows > 10:
                    logger.warning(f"[_send_interactive_message] Muitas linhas ({total_rows}), limitando a 10")
                    new_sections = []
                    rows_count = 0
                    for section in sections:
                        rows = section.get('rows', [])
                        remaining = 10 - rows_count
                        if remaining <= 0:
                            break
                        if len(rows) > remaining:
                            rows = rows[:remaining]
                        new_section = {**section, 'rows': rows}
                        new_sections.append(new_section)
                        rows_count += len(rows)
                    sections = new_sections
                
                try:
                    response = self.whatsapp_service.send_interactive_list(
                        to=phone_number,
                        body_text=body,
                        button_text=button,
                        sections=sections
                    )
                    logger.info(f"[Automation] Sent interactive list to {phone_number}: {response}")
                except Exception as e:
                    logger.error(f"[Automation] Error sending list: {e}")
                    # Fallback para texto
                    fallback_text = body + "\n\n"
                    for section in sections:
                        fallback_text += f"*{section.get('title', 'Produtos')}:*\n"
                        for row in section.get('rows', []):
                            fallback_text += f"• {row.get('title', '')} - {row.get('description', '')}\n"
                    return fallback_text
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
        """Processa mensagem usando LLM - USA NVIDIA DIRETAMENTE"""
        from django.conf import settings
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI
        
        if not self.use_llm:
            logger.info("[Automation] LLM disabled, using fallback")
            return self._get_fallback_message()
        
        # USA NVIDIA DIRETAMENTE - Não usa o agente configurado
        nvidia_key = getattr(settings, 'NVIDIA_API_KEY', None)
        if nvidia_key:
            logger.info("[Automation] Using NVIDIA AI directly (not Moonshot!)")
            try:
                # Usa o melhor modelo da NVIDIA
                model_name = getattr(settings, 'NVIDIA_MODEL_NAME', 'meta/llama-3.1-70b-instruct')
                if '8b' in model_name.lower():
                    model_name = 'meta/llama-3.1-70b-instruct'
                
                llm = ChatOpenAI(
                    model=model_name,
                    base_url=getattr(settings, 'NVIDIA_API_BASE_URL', 'https://integrate.api.nvidia.com/v1'),
                    api_key=nvidia_key,
                    temperature=0.3,
                    max_tokens=150  # Limita respostas longas
                )
                
                # Contexto simples e direto
                prompt = ChatPromptTemplate.from_messages([
                    ("system", """Você é um atendente simpático da Pastita - Massas Artesanais.

REGRAS IMPORTANTES:
1. Responda de forma CURTA e direta (máximo 2-3 frases)
2. Seja humano e simpático, não robótico
3. Se o cliente quiser pedir, pergunte quantos itens
4. Não invente informações - só fale do cardápio se souber
5. Não escreva textos longos!

Exemplo de resposta boa: "Oi! 😊 Quer fazer um pedido hoje? Temos rondelli de frango, presunto e 4 queijos. Quantos você gostaria?"

Exemplo de resposta ruim: Textos longos com muitas seções e informações desnecessárias."""),
                    ("human", "{message}")
                ])
                
                chain = prompt | llm
                result = chain.invoke({"message": message_text[:500]})
                
                response = result.content.strip()
                logger.info(f"[Automation] NVIDIA response: {response[:50]}...")
                return response
                
            except Exception as e:
                logger.error(f"[Automation] NVIDIA error: {e}")
                # Fall through to fallback
        
        # Fallback: tenta usar o agente configurado se NVIDIA falhar
        if self.account.default_agent:
            try:
                logger.info("[Automation] Falling back to configured agent")
                service = LangchainService(self.account.default_agent)
                result = service.process_message(
                    message=message_text,
                    session_id=str(self.conversation.id),
                    phone_number=self.conversation.phone_number,
                    conversation_id=str(self.conversation.id)
                )
                return result.get('response') or self._get_fallback_message()
            except Exception as e:
                logger.error(f"[Automation] Agent error: {e}")
        
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
    
    def _log_intent(
        self,
        intent_data: Dict[str, Any],
        handler_used: str,
        response_text: str,
        response_type: str,
        start_time: float,
        error: str = ""
    ) -> None:
        """
        Cria registro de log da intenção detectada.

        Args:
            intent_data: Dados da intenção detectada
            handler_used: Nome do handler utilizado
            response_text: Texto da resposta enviada
            response_type: Tipo da resposta (text/buttons/list/llm/etc)
            start_time: Timestamp de início do processamento
            error: Mensagem de erro (se houver)
        """
        try:
            processing_time = int((time.time() - start_time) * 1000)  # ms

            # Prepara metadados
            metadata = {}
            if error:
                metadata['error'] = error

            # Obtém company do account
            company = getattr(self.account, 'company_profile', None)
            if not company:
                logger.warning("[IntentLog] No company profile found, skipping log")
                return

            # Cria o log
            IntentLog.objects.create(
                company=company,
                conversation=self.conversation,
                phone_number=self.conversation.phone_number,
                message_text=intent_data.get('original_message', '')[:500],  # Limita tamanho
                intent_type=intent_data['intent'].value,
                method=intent_data.get('method', 'none'),
                confidence=float(intent_data.get('confidence', 0)),
                handler_used=handler_used,
                response_text=response_text[:1000] if response_text else "",  # Limita tamanho
                response_type=response_type,
                processing_time_ms=processing_time,
                entities=intent_data.get('entities', {}),
                metadata=metadata
            )

            if self.debug:
                logger.info(f"[IntentLog] Created log for intent: {intent_data['intent'].value}")

        except Exception as e:
            # Nunca deve quebrar o fluxo por causa de logging
            logger.error(f"[IntentLog] Error creating log: {str(e)}")

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
