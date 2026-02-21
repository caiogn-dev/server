"""
WhatsApp Intent Detection System

Sistema de detecção de intenções usando:
1. Regex patterns (rápido, sem custo) - 80% dos casos
2. LLM fallback (quando necessário) - 20% dos casos

Baseado em: Jasper's Market + Meta Best Practices
"""
from enum import Enum
from typing import Optional, Dict, Any, List
import re
import logging

logger = logging.getLogger(__name__)

# Type alias for intent data
IntentData = Dict[str, Any]


class IntentType(Enum):
    """Tipos de intenção do usuário"""
    
    # ===== NÍVEL 1: Templates Diretos (Sem LLM) =====
    GREETING = "greeting"                    # "Oi", "Olá", "Bom dia"
    PRICE_CHECK = "price_check"              # "Quanto custa", "Preço"
    BUSINESS_HOURS = "business_hours"        # "Horário", "Abre quando"
    DELIVERY_INFO = "delivery_info"          # "Frete", "Entrega"
    MENU_REQUEST = "menu_request"            # "Cardápio", "Menu", "Produtos"
    TRACK_ORDER = "track_order"              # "Rastrear", "Status do pedido"
    PAYMENT_STATUS = "payment_status"        # "Pagamento", "PIX"
    LOCATION = "location"                    # "Onde fica", "Endereço"
    CONTACT = "contact"                      # "Telefone", "Falar com"
    FAQ = "faq"                              # Perguntas frequentes
    
    # ===== NÍVEL 2: Ação Direta (Sem LLM) =====
    CREATE_ORDER = "create_order"            # "Quero pedir", "Fazer pedido"
    CANCEL_ORDER = "cancel_order"            # "Cancelar pedido"
    MODIFY_ORDER = "modify_order"            # "Trocar", "Alterar pedido"
    CONFIRM_PAYMENT = "confirm_payment"      # "Paguei", "Comprovante"
    REQUEST_PIX = "request_pix"              # "Gerar PIX", "Pagamento"
    VIEW_QR_CODE = "view_qr_code"            # "Ver QR Code"
    COPY_PIX = "copy_pix"                    # "Copiar PIX"
    ADD_TO_CART = "add_to_cart"              # "Quero X", "Adicionar Y"
    PRODUCT_MENTION = "product_mention"      # "Rondelli", "Pizza" (só o nome)
    
    # ===== NÍVEL 3: LLM Necessário =====
    PRODUCT_INQUIRY = "product_inquiry"      # "Qual a diferença..."
    CUSTOMIZATION = "customization"          # "Sem cebola", "Mais queijo"
    COMPARISON = "comparison"                # "Qual é melhor..."
    RECOMMENDATION = "recommendation"        # "O que você sugere..."
    COMPLAINT = "complaint"                  # Reclamações complexas
    GENERAL_QUESTION = "general_question"    # Outras dúvidas
    
    # ===== Fallback =====
    UNKNOWN = "unknown"
    HUMAN_HANDOFF = "human_handoff"          # "Falar com atendente"


class IntentDetector:
    """
    Detecta intenção do usuário usando regex (rápido) 
    com fallback para LLM quando necessário
    """
    
    # ===== PATTERNS PARA DETECÇÃO RÁPIDA =====
    PATTERNS = {
        IntentType.GREETING: [
            r'^(oi|ol[aá]|ola|eae|eai|bom dia|boa tarde|boa noite|salve|hey|hi|hello)[!?.\s]*$',
            r'^(tudo bem|como vai|beleza|tranquilo|e a[ií]|oi tudo bem)',
            r'^(opa|eai|eae|fala)',
        ],
        IntentType.PRICE_CHECK: [
            r'(quanto custa|qual [o ]?pre[çc]o|valor do|pre[çc]o do|quanto [ée]|tabela de pre[çc]o|quanto sai)',
            r'(valor da|pre[çc]o da|quanto fica|qual valor)',
            r'(custa quanto|sai por quanto)',
        ],
        IntentType.BUSINESS_HOURS: [
            r'(que horas (abre|fecha)|hor[áa]rio|funcionamento|atendimento|aberto|fecha que horas)',
            r'(at[eé] que horas|qual o hor[áa]rio|quando abre|quando fecha)',
            r'(abre quando|fecha quando|vai abrir|vai fechar)',
        ],
        IntentType.DELIVERY_INFO: [
            r'(frete|entrega|delivery|envia|entregam|tempo de entrega|quanto tempo demora|prazo)',
            r'(taxa de entrega|valor do frete|custo da entrega|entrega em quanto tempo)',
            r'(delivery [ée]|entrega gr[áa]tis|tem entrega|faz entrega)',
        ],
        IntentType.MENU_REQUEST: [
            r'(card[áa]pio|menu|o que (tem|voc[êe]s t[êe]m)|op[çc][õo]es|opcoes|lista|cat[áa]logo|produtos)',
            r'(ver produtos|mostrar card[áa]pio|mostra o menu|tem o que|o que vende)',
            r'(quais s[ãa]o os produtos|o que tem dispon[íi]vel)',
        ],
        IntentType.TRACK_ORDER: [
            r'(rastrear|rastreio|status (do )?pedido|onde est[áa] (meu )?pedido|n[úu]mero do pedido|acompanhar)',
            r'(meu pedido|onde ficou meu pedido|como est[áa] meu pedido|status da entrega)',
        ],
        IntentType.PAYMENT_STATUS: [
            r'(status do pagamento|ver pagamento|consultar pagamento)',
            r'(pix gerado|c[oó]digo pix|chave pix|onde est[áa] o pix)',
        ],
        IntentType.LOCATION: [
            r'(onde (fica|voc[êe]s (est[ãa]o|ficam))|endere[çc]o|localiza[çc][ãa]o|como chegar)',
            r'(qual o endere[çc]o|onde [ée] a loja|tem loja f[íi]sica)',
        ],
        IntentType.CONTACT: [
            r'(telefone|whatsapp|contato|falar com|atendente|pessoa|humano|sac)',
            r'(falar com algu[ée]m|quero falar|atendimento humano|suporte)',
        ],
        IntentType.FAQ: [
            r'(como funciona|como [ée]|qual [ée] a|o que [ée]|me explica|explica como)',
        ],
        IntentType.CREATE_ORDER: [
            r'(quero (fazer )?pedido|quero pedir|fazer pedido|vou querer|queria (comprar|pedir)|quero comprar)',
            r'(come[çc]ar pedido|novo pedido|quero encomendar|quero solicitar)',
            r'(pode fazer pedido|aceita pedido|tem como pedir|pedido rápido)',
            r'(confirmar pedido|finalizar pedido|fechar pedido|concluir pedido|criar pedido)',
            r'(quero confirmar|quero finalizar|confirmar compra|finalizar compra)',
        ],
        IntentType.CANCEL_ORDER: [
            r'(cancelar pedido|quero cancelar|posso cancelar|preciso cancelar)',
        ],
        IntentType.MODIFY_ORDER: [
            r'(trocar|alterar pedido|mudar pedido|modificar|tirar|adicionar|remover)',
        ],
        IntentType.CONFIRM_PAYMENT: [
            r'(paguei|j[áa] paguei|comprovante|enviei o pix|confirma pagamento|fiz o pagamento)',
        ],
        IntentType.REQUEST_PIX: [
            r'(gerar pix|c[oó]digo pix|quero pagar|forma de pagamento|como pago|gerar c[oó]digo)',
        ],
        IntentType.VIEW_QR_CODE: [
            r'(qr code|qr-code|ver qr|mostrar qr|c[óo]digo qr)',
        ],
        IntentType.COPY_PIX: [
            r'(copiar pix|copiar c[oó]digo|c[oó]digo pix|pix c[oó]digo|ver pix)',
        ],
        IntentType.ADD_TO_CART: [
            r'(quero \d+|vou querer \d+|adicionar \d+|me v[êe] \d+|manda \d+)',
            r'(coloca \d+|bota \d+|queria \d+)',  # Pega números como "quero 2 rondelli"
            r'^\d+\s+(rondelli|rondellis|rondel|rondelis|massa|massas|lasanha|lasanhas|nhoque|nhoques|refri|refrigerante|coca|guaran[áa])',  # Número primeiro: "2 rondelis"
            r'^\d+\s+de\s+(frango|queijo|presunto|calabresa|mussarela)',  # "2 de frango"
            r'(rondelli de|rondellis de|rondel de)',  # "rondelli de frango"
        ],
        IntentType.PRODUCT_MENTION: [
            # Só o nome do produto sem número - pergunta sobre o produto
            r'^(rondelli|rondellis|rondel|rondelis|massa|massas|lasanha|lasanhas|nhoque|nhoques|bolonhesa|bolonhesas)$',
            r'^(rondelli|rondellis|rondel|rondelis) de (frango|queijo|presunto|calabresa|mussarela|4 queijos|quatro queijos)$',
        ],
        IntentType.HUMAN_HANDOFF: [
            r'(atendente|pessoa|humano|falar com algu[ée]m|n[ãa]o [ée] o que quero|errado|atendente humano)',
            r'(quero falar com pessoa|me passa pro atendente|chama algu[ée]m|quero ajuda humana)',
        ],
    }
    
    # ===== PALAVRAS QUE INDICAM NECESSIDADE DE LLM =====
    LLM_TRIGGERS = [
        r'(qual [ée] (melhor|a diferen[çc]a)|compare|versus|vs|melhor que|pior que)',
        r'(sem .+|mais .+|tira .+|coloca .+|substitui|trocar .+ por|ao inv[ée]s de)',
        r'(recomenda|sugere|indica|qual voc[êe] (gosta|recomenda)|o que me indica)',
        r'(por que|porqu[êe]|qual a raz[ãa]o|explique|me explica|por qual motivo)',
        r'(diferen[çc]a entre|comparar|qual a vantagem|vale a pena)',
    ]
    
    # ===== ENTIDADES EXTRAÍVEIS =====
    ENTITY_PATTERNS = {
        'quantity': r'\b(\d+)\b',
        'product_name': r'(?:de|do|da)\s+([\w\s]+?)(?:\s+(?:por|para|com|e|$))',
        'order_number': r'(?:pedido|n[úu]mero|#)\s*(\d+)',
        'phone_number': r'\(?\d{2}\)?\s*\d{4,5}[-\s]?\d{4}',
        'email': r'[\w\.-]+@[\w\.-]+\.\w+',
    }
    
    def __init__(self, use_llm_fallback: bool = True):
        self.use_llm_fallback = use_llm_fallback
    
    def detect_regex(self, message: str) -> Optional[IntentType]:
        """
        Detecta intenção usando regex (rápido, sem custo)
        
        Returns:
            IntentType ou None se não encontrar match
        """
        message_lower = message.lower().strip()
        
        # Ordena por prioridade (mais específicos primeiro)
        priority_order = [
            IntentType.CREATE_ORDER,
            IntentType.CANCEL_ORDER,
            IntentType.TRACK_ORDER,
            IntentType.PAYMENT_STATUS,
            IntentType.HUMAN_HANDOFF,
            IntentType.ADD_TO_CART,
            IntentType.PRODUCT_MENTION,
            IntentType.CONFIRM_PAYMENT,
            IntentType.REQUEST_PIX,
            IntentType.PRICE_CHECK,
            IntentType.MENU_REQUEST,
            IntentType.BUSINESS_HOURS,
            IntentType.DELIVERY_INFO,
            IntentType.LOCATION,
            IntentType.CONTACT,
            IntentType.FAQ,
            IntentType.GREETING,
        ]
        
        for intent in priority_order:
            patterns = self.PATTERNS.get(intent, [])
            for pattern in patterns:
                if re.search(pattern, message_lower):
                    logger.debug(f"Regex match: {intent.value} for message: {message[:30]}...")
                    return intent
        
        return None
    
    def needs_llm(self, message: str) -> bool:
        """Verifica se mensagem precisa de LLM para análise"""
        message_lower = message.lower()
        
        for pattern in self.LLM_TRIGGERS:
            if re.search(pattern, message_lower):
                logger.debug(f"LLM trigger detected in: {message[:30]}...")
                return True
        
        return False
    
    def detect_with_llm(self, message: str, context: Dict[str, Any] = None) -> IntentType:
        """
        Usa LLM para classificação quando regex não é suficiente
        
        IMPORTANTE: Esta função só é chamada se use_llm_fallback=True
        """
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI
        from django.conf import settings
        
        if not self.use_llm_fallback:
            return IntentType.UNKNOWN
        
        logger.info(f"Using LLM for intent detection: {message[:50]}...")
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """Classifique a intenção da mensagem do usuário.

Opções disponíveis:
- product_inquiry: Pergunta específica sobre produto
- customization: Personalização de pedido ("sem cebola", "mais queijo")
- comparison: Comparação entre produtos
- recommendation: Pedido de recomendação
- complaint: Reclamação
- general_question: Outra dúvida
- human_handoff: Quer falar com atendente
- unknown: Não sei classificar

Responda APENAS com o nome da intenção em inglês minúsculo."""),
            ("human", "Mensagem: {message}")
        ])
        
        try:
            # Verifica se tem configuração da NVIDIA
            nvidia_key = getattr(settings, 'NVIDIA_API_KEY', None)
            if not nvidia_key:
                logger.warning("NVIDIA_API_KEY not configured, skipping LLM intent detection")
                return IntentType.UNKNOWN
            
            # Usa modelo melhor da NVIDIA (Llama 3.1 70B é mais inteligente que o 8B)
            model_name = getattr(settings, 'NVIDIA_MODEL_NAME', "meta/llama-3.1-70b-instruct")
            # Fallback para 70B se estiver usando o 8B antigo
            if '8b' in model_name.lower():
                model_name = "meta/llama-3.1-70b-instruct"
                logger.info("Upgrading to Llama 3.1 70B for better responses")
            
            model = ChatOpenAI(
                model=model_name,
                base_url=getattr(settings, 'NVIDIA_API_BASE_URL', "https://integrate.api.nvidia.com/v1"),
                api_key=nvidia_key,
                temperature=0.1,  # Leve criatividade mas controlada
                max_tokens=100    # Limita respostas longas
            )
            
            chain = prompt | model
            result = chain.invoke({"message": message[:500]})  # Limita tamanho
            
            intent_str = result.content.strip().lower()
            
            intent_map = {
                'product_inquiry': IntentType.PRODUCT_INQUIRY,
                'customization': IntentType.CUSTOMIZATION,
                'comparison': IntentType.COMPARISON,
                'recommendation': IntentType.RECOMMENDATION,
                'complaint': IntentType.COMPLAINT,
                'general_question': IntentType.GENERAL_QUESTION,
                'human_handoff': IntentType.HUMAN_HANDOFF,
                'unknown': IntentType.UNKNOWN,
            }
            
            detected = intent_map.get(intent_str, IntentType.UNKNOWN)
            logger.info(f"LLM detected intent: {detected.value}")
            return detected
            
        except Exception as e:
            logger.error(f"LLM intent detection error: {str(e)}")
            return IntentType.UNKNOWN
    
    def extract_entities(self, message: str, intent: IntentType) -> Dict[str, Any]:
        """Extrai entidades relevantes da mensagem"""
        entities = {}
        message_lower = message.lower()
        
        # Quantidade (para add_to_cart)
        if intent == IntentType.ADD_TO_CART:
            qty_match = re.search(self.ENTITY_PATTERNS['quantity'], message)
            if qty_match:
                entities['quantity'] = int(qty_match.group(1))
            else:
                entities['quantity'] = 1  # Default
            
            # Tenta extrair nome do produto
            # Procura por padrões como "2 rondelli", "quero 3 massas"
            words = message_lower.split()
            for i, word in enumerate(words):
                if word.isdigit() and i + 1 < len(words):
                    # Pega até 3 palavras após o número
                    product_words = words[i+1:i+4]
                    entities['product_name'] = ' '.join(product_words)
                    break
        
        # Número do pedido (para track_order)
        if intent == IntentType.TRACK_ORDER:
            order_match = re.search(self.ENTITY_PATTERNS['order_number'], message)
            if order_match:
                entities['order_number'] = order_match.group(1)
        
        # Nome do produto (para price_check)
        if intent == IntentType.PRICE_CHECK:
            # Pega tudo após "preço de" ou "quanto custa"
            price_patterns = [
                r'(?:pre[çc]o|valor|custa)(?:\s+(?:de|do|da))?\s+([^?]+)',
                r'quanto [ée]\s+([^?]+)',
            ]
            for pattern in price_patterns:
                match = re.search(pattern, message_lower)
                if match:
                    entities['product_name'] = match.group(1).strip()
                    break
        
        return entities
    
    def detect(self, message: str, force_llm: bool = False) -> Dict[str, Any]:
        """
        Detecta intenção completa com metadados
        
        Args:
            message: Texto da mensagem
            force_llm: Se True, sempre usa LLM (para testes)
        
        Returns:
            {
                'intent': IntentType,
                'method': 'regex' | 'llm' | 'none',
                'confidence': float,
                'entities': dict,
                'original_message': str
            }
        """
        if not message or not message.strip():
            return {
                'intent': IntentType.UNKNOWN,
                'method': 'none',
                'confidence': 0.0,
                'entities': {},
                'original_message': message
            }
        
        # Limpa mensagem
        clean_message = message.strip()
        
        # Tenta regex primeiro
        if not force_llm:
            regex_intent = self.detect_regex(clean_message)
            
            if regex_intent:
                entities = self.extract_entities(clean_message, regex_intent)
                logger.info(f"Intent detected via regex: {regex_intent.value}")
                return {
                    'intent': regex_intent,
                    'method': 'regex',
                    'confidence': 0.95,
                    'entities': entities,
                    'original_message': clean_message
                }
        
        # Se não encontrou e use_llm=True, tenta com LLM
        if self.use_llm_fallback or force_llm:
            llm_intent = self.detect_with_llm(clean_message)
            return {
                'intent': llm_intent,
                'method': 'llm',
                'confidence': 0.80,
                'entities': {},
                'original_message': clean_message
            }
        
        logger.warning(f"No intent detected for: {clean_message[:50]}...")
        return {
            'intent': IntentType.UNKNOWN,
            'method': 'none',
            'confidence': 0.0,
            'entities': {},
            'original_message': clean_message
        }


# Instância global para uso
intent_detector = IntentDetector(use_llm_fallback=True)
