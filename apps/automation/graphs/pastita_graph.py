"""
Pastita Graph - Definição do grafo LangGraph para orquestração do bot WhatsApp.
"""
import logging
from typing import Dict, List, Any, Optional, TypedDict
from datetime import datetime
from enum import Enum

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)


class ConversationState(str, Enum):
    """Estados possíveis da conversa."""
    GREETING = "greeting"
    MENU = "menu"
    PRODUCT_INQUIRY = "product_inquiry"
    CART = "cart"
    DELIVERY_METHOD = "delivery_method"
    ADDRESS = "address"
    PAYMENT_METHOD = "payment_method"
    CHECKOUT = "checkout"
    AWAITING_PAYMENT = "awaiting_payment"
    ORDER_CONFIRMED = "order_confirmed"
    ORDER_STATUS = "order_status"
    HUMAN_HANDOFF = "human_handoff"
    ERROR = "error"


class IntentType(str, Enum):
    """Tipos de intenção detectada."""
    GREETING = "greeting"
    MENU_REQUEST = "menu_request"
    PRODUCT_INQUIRY = "product_inquiry"
    ADD_TO_CART = "add_to_cart"
    REMOVE_FROM_CART = "remove_from_cart"
    VIEW_CART = "view_cart"
    CLEAR_CART = "clear_cart"
    CREATE_ORDER = "create_order"
    CONFIRM_ORDER = "confirm_order"
    CANCEL_ORDER = "cancel_order"
    SELECT_DELIVERY = "select_delivery"
    SELECT_PICKUP = "select_pickup"
    PROVIDE_ADDRESS = "provide_address"
    SELECT_PAYMENT_PIX = "select_payment_pix"
    SELECT_PAYMENT_CASH = "select_payment_cash"
    SELECT_PAYMENT_CARD = "select_payment_card"
    REQUEST_PIX = "request_pix"
    CONFIRM_PAYMENT = "confirm_payment"
    CHECK_STATUS = "check_status"
    BUSINESS_HOURS = "business_hours"
    DELIVERY_INFO = "delivery_info"
    HUMAN_HANDOFF = "human_handoff"
    RESET = "reset"
    UNKNOWN = "unknown"


class ContextSource(str, Enum):
    """Fonte da resposta."""
    HANDLER = "handler"
    AUTOMESSAGE = "automessage"
    LLM = "llm"
    FALLBACK = "fallback"


class PastitaState(TypedDict):
    """Estado completo da conversação."""
    session_id: str
    phone_number: str
    company_id: str
    store_id: str
    account_id: str
    current_state: str
    previous_state: Optional[str]
    messages: List[BaseMessage]
    cart: Dict[str, Any]
    order_data: Dict[str, Any]
    last_intent: str
    intent_confidence: float
    intent_entities: Dict[str, Any]
    context_source: str
    response_text: str
    response_buttons: Optional[List[Dict[str, str]]]
    metadata: Dict[str, Any]
    error_count: int
    last_activity: str


def create_initial_state(
    session_id: str,
    phone_number: str,
    company_id: str,
    store_id: str,
    account_id: str
) -> PastitaState:
    """Cria estado inicial para uma nova conversa."""
    return {
        'session_id': session_id,
        'phone_number': phone_number,
        'company_id': company_id,
        'store_id': store_id,
        'account_id': account_id,
        'current_state': ConversationState.GREETING,
        'previous_state': None,
        'messages': [],
        'cart': {'items': [], 'total': 0.0},
        'order_data': {
            'order_id': None,
            'order_number': None,
            'payment_method': None,
            'delivery_method': None,
            'delivery_address': None,
            'delivery_fee': None,
            'subtotal': 0.0,
            'total': 0.0,
        },
        'last_intent': '',
        'intent_confidence': 0.0,
        'intent_entities': {},
        'context_source': '',
        'response_text': '',
        'response_buttons': None,
        'metadata': {},
        'error_count': 0,
        'last_activity': datetime.now().isoformat(),
    }


def detect_intent_node(state: PastitaState) -> PastitaState:
    """Nó de detecção de intenção usando regex."""
    import re
    
    last_message = None
    for msg in reversed(state['messages']):
        if isinstance(msg, HumanMessage):
            last_message = msg.content
            break
    
    if not last_message:
        state['last_intent'] = IntentType.UNKNOWN
        state['intent_confidence'] = 0.0
        return state
    
    message_lower = last_message.lower().strip()
    
    patterns = {
        IntentType.GREETING: [
            r'^(oi|ol[áa]|ola|eae|eai|bom dia|boa tarde|boa noite|salve|hey|hi|hello|opa|tudo bem)',
        ],
        IntentType.MENU_REQUEST: [
            r'(card[áa]pio|menu|o que (tem|voc[êe]s t[êe]m)|op[çc][õo]es|produtos)',
        ],
        IntentType.PRODUCT_INQUIRY: [
            r'(quanto custa|qual [o ]?pre[çc]o|valor do|pre[çc]o do|informa[çc][õo]es)',
        ],
        IntentType.ADD_TO_CART: [
            r'(quero|vou querer|adiciona|coloca|me v[êe]|pedir|gostaria)',
            r'^(\d+)\s+(rondelli|lasanha|nhoque|talharim|fettuccine|molho)',
        ],
        IntentType.REMOVE_FROM_CART: [
            r'(tira|remove|retira|tirar|remover|cancela|excluir)',
        ],
        IntentType.VIEW_CART: [
            r'(carrinho|ver pedido|meu pedido|ver carrinho)',
        ],
        IntentType.CLEAR_CART: [
            r'(limpa carrinho|esvazia|tira tudo|cancela tudo|limpar)',
        ],
        IntentType.CREATE_ORDER: [
            r'(finalizar|fechar pedido|confirmar|quero pagar|fazer pedido|terminar)',
        ],
        IntentType.CANCEL_ORDER: [
            r'(cancela|n[ãa]o quero mais|desistir|cancelar|sair|voltar)',
        ],
        IntentType.SELECT_DELIVERY: [
            r'(entrega|delivery|receber em casa|mandar|enviar)',
        ],
        IntentType.SELECT_PICKUP: [
            r'(retirada|pickup|buscar|buscar na loja|retirar)',
        ],
        IntentType.REQUEST_PIX: [
            r'(pix|gerar pix|c[óo]digo|qr code|como pagar|pagar)',
        ],
        IntentType.CONFIRM_PAYMENT: [
            r'(paguei|j[áa] paguei|comprovante|enviei|transferi|pago)',
        ],
        IntentType.CHECK_STATUS: [
            r'(status|onde est[áa]|rastrear|rastreio|acompanhar)',
        ],
        IntentType.BUSINESS_HOURS: [
            r'(hor[áa]rio|que horas|abre|fecha|funcionamento|aberto)',
        ],
        IntentType.DELIVERY_INFO: [
            r'(entrega|frete|delivery|envia|taxa|tempo de entrega)',
        ],
        IntentType.HUMAN_HANDOFF: [
            r'(atendente|humano|falar com pessoa|reclamar|suporte)',
        ],
        IntentType.RESET: [
            r'(cancelar|sair|resetar|novo pedido|come[çc]ar|reiniciar)',
        ],
    }
    
    detected_intent = IntentType.UNKNOWN
    confidence = 0.0
    entities = {}
    
    for intent, pattern_list in patterns.items():
        for pattern in pattern_list:
            match = re.search(pattern, message_lower, re.IGNORECASE)
            if match:
                detected_intent = intent
                confidence = 0.95
                
                if intent == IntentType.ADD_TO_CART:
                    qty_match = re.search(r'^(\d+)', message_lower)
                    if qty_match:
                        entities['quantity'] = int(qty_match.group(1))
                    else:
                        entities['quantity'] = 1
                    product_name = re.sub(r'^\d+\s*', '', last_message).strip()
                    entities['product_name'] = product_name
                
                break
        if confidence > 0:
            break
    
    if detected_intent == IntentType.UNKNOWN:
        qty_pattern = r'^(\d+)\s+(.+)$'
        match = re.match(qty_pattern, message_lower)
        if match:
            potential_product = match.group(2)
            if any(word in potential_product for word in ['rondelli', 'lasanha', 'nhoque', 'talharim', 'fettuccine', 'molho']):
                detected_intent = IntentType.ADD_TO_CART
                confidence = 0.9
                entities['quantity'] = int(match.group(1))
                entities['product_name'] = match.group(2)
    
    state['last_intent'] = detected_intent
    state['intent_confidence'] = confidence
    state['intent_entities'] = entities
    
    return state


def route_context_node(state: PastitaState) -> PastitaState:
    """Nó de roteamento contextual."""
    intent = state['last_intent']
    current_state = state['current_state']
    
    handler_intents = [
        IntentType.ADD_TO_CART, IntentType.REMOVE_FROM_CART,
        IntentType.VIEW_CART, IntentType.CLEAR_CART,
        IntentType.CREATE_ORDER, IntentType.CONFIRM_ORDER,
        IntentType.CANCEL_ORDER, IntentType.SELECT_DELIVERY,
        IntentType.SELECT_PICKUP, IntentType.REQUEST_PIX,
        IntentType.CONFIRM_PAYMENT, IntentType.CHECK_STATUS,
    ]
    
    critical_states = [
        ConversationState.CHECKOUT,
        ConversationState.AWAITING_PAYMENT,
        ConversationState.PAYMENT_METHOD,
    ]
    
    if current_state in critical_states:
        state['context_source'] = ContextSource.HANDLER
        return state
    
    if intent in handler_intents:
        state['context_source'] = ContextSource.HANDLER
        return state
    
    if intent == IntentType.UNKNOWN:
        state['context_source'] = ContextSource.LLM
        return state
    
    state['context_source'] = ContextSource.HANDLER
    return state


def execute_handler_node(state: PastitaState) -> PastitaState:
    """Nó de execução de handlers."""
    from apps.automation.tools.pastita_tools import (
        get_menu, add_to_cart, view_cart,
        clear_cart, calculate_delivery_fee, create_order,
        generate_pix, check_order_status
    )
    
    intent = state['last_intent']
    entities = state['intent_entities']
    
    try:
        if intent == IntentType.GREETING:
            state['response_text'] = (
                "👋 *Olá! Bem-vindo à Pastita!*\n\n"
                "Somos especialistas em massas artesanais. 🍝\n\n"
                "*Como posso ajudar?*\n"
                "• Ver *cardápio*\n"
                "• Fazer um *pedido*\n"
                "• Tirar *dúvidas*"
            )
            state['response_buttons'] = [
                {'id': 'menu', 'title': '📋 Ver Cardápio'},
                {'id': 'cart', 'title': '🛒 Meu Carrinho'},
            ]
            state['current_state'] = ConversationState.MENU
        
        elif intent == IntentType.MENU_REQUEST:
            menu_result = get_menu(state['store_id'])
            if isinstance(menu_result, dict) and menu_result.get('success'):
                # Formatar cardápio
                menu_text = f"📋 *Cardápio - {menu_result['store_name']}*\n\n"
                for category in menu_result.get('categories', []):
                    menu_text += f"*{category['name']}*\n"
                    for product in category.get('products', [])[:5]:
                        menu_text += f"  • {product['name']} - R$ {product['price']:.2f}\n"
                    menu_text += "\n"
                menu_text += "_Digite o nome do produto para adicionar ao carrinho_"
                state['response_text'] = menu_text
            else:
                state['response_text'] = "❌ Erro ao carregar cardápio. Tente novamente."
            state['current_state'] = ConversationState.MENU
        
        elif intent == IntentType.PRODUCT_INQUIRY:
            product_name = entities.get('product_name', '')
            if product_name:
                state['response_text'] = "Produto não encontrado. Digite *cardápio* para ver opções."
            else:
                state['response_text'] = "Para ver nossos produtos, digite *cardápio*."
        
        elif intent == IntentType.ADD_TO_CART:
            quantity = entities.get('quantity', 1)
            product_name = entities.get('product_name', '')
            
            if product_name:
                result = add_to_cart(state['session_id'], product_name, quantity)
                if isinstance(result, dict) and result.get('success'):
                    state['response_text'] = "✅ " + result.get('product_name', 'Produto') + " adicionado! Carrinho: " + str(result.get('item_count', 0)) + " itens"
                else:
                    state['response_text'] = "❌ " + result.get('error', 'Erro ao adicionar')
                state['current_state'] = ConversationState.CART
            else:
                state['response_text'] = "Qual produto você deseja adicionar?"
        
        elif intent == IntentType.VIEW_CART:
            cart_result = view_cart(state['session_id'])
            if isinstance(cart_result, dict) and cart_result.get('success'):
                if cart_result.get('empty'):
                    state['response_text'] = "🛒 Carrinho vazio. Digite *cardápio* para ver opções."
                else:
                    cart_text = "🛒 *Carrinho*\n\n"
                    for item in cart_result.get('items', []):
                        cart_text += str(item['index']) + ". " + item['name'] + "\n"
                        cart_text += "   " + str(item['quantity']) + "x R$ " + str(round(item['unit_price'], 2)) + "\n"
                    cart_text += "\nTotal: R$ " + str(round(cart_result.get('total', 0), 2))
                    state['response_text'] = cart_text
            else:
                state['response_text'] = "❌ Erro ao carregar carrinho."
        
        elif intent == IntentType.CLEAR_CART:
            clear_result = clear_cart(state['session_id'])
            if isinstance(clear_result, dict) and clear_result.get('success'):
                state['response_text'] = "🗑️ Carrinho limpo!"
            else:
                state['response_text'] = "❌ Erro ao limpar carrinho."
        
        elif intent == IntentType.CREATE_ORDER:
            cart_result = view_cart(state['session_id'])
            if "vazio" in cart_result.lower():
                state['response_text'] = "❌ Seu carrinho está vazio. Adicione itens primeiro!"
            else:
                state['response_text'] = (
                    "🚚 *Como deseja receber seu pedido?*\n\n"
                    "Escolha uma opção:"
                )
                state['response_buttons'] = [
                    {'id': 'delivery', 'title': '🛵 Entrega'},
                    {'id': 'pickup', 'title': '🏪 Retirada na Loja'},
                ]
                state['current_state'] = ConversationState.DELIVERY_METHOD
        
        elif intent == IntentType.SELECT_DELIVERY:
            state['response_text'] = (
                "📍 *Entrega selecionada*\n\n"
                "Por favor, informe seu endereço completo:\n\n"
                "_Exemplo: Rua das Flores, 123, Centro, Palmas-TO_"
            )
            state['current_state'] = ConversationState.ADDRESS
        
        elif intent == IntentType.SELECT_PICKUP:
            state['order_data']['delivery_method'] = 'pickup'
            state['order_data']['delivery_fee'] = 0.0
            state['response_text'] = (
                "🏪 *Retirada na loja selecionada*\n\n"
                "Como deseja pagar?"
            )
            state['response_buttons'] = [
                {'id': 'pay_pickup', 'title': '💵 Pagar na Retirada'},
                {'id': 'pay_pix', 'title': '💳 PIX (antecipado)'},
            ]
            state['current_state'] = ConversationState.PAYMENT_METHOD
        
        elif intent == IntentType.SELECT_PAYMENT_PIX:
            order_result = create_order.invoke({
                'session_id': state['session_id'],
                'payment_method': 'pix',
                'delivery_method': state['order_data'].get('delivery_method', 'pickup')
            })
            
            if order_result.get('success'):
                state['order_data']['order_id'] = order_result.get('order_id')
                state['order_data']['order_number'] = order_result.get('order_number')
                state['order_data']['total'] = order_result.get('total', 0.0)
                
                pix_result = generate_pix.invoke({
                    'order_id': order_result.get('order_id')
                })
                
                if pix_result.get('success'):
                    state['response_text'] = (
                        f"💳 *Código PIX gerado!*\n\n"
                        f"Pedido: *{order_result.get('order_number')}*\n"
                        f"Total: R$ {order_result.get('total', 0):.2f}\n\n"
                        f"*Código copia-e-cola:*\n"
                        f"`{pix_result.get('pix_code')}`\n\n"
                        f"_Válido por 30 minutos_\n\n"
                        f"Depois de pagar, envie *paguei*!"
                    )
                    state['current_state'] = ConversationState.AWAITING_PAYMENT
                else:
                    state['response_text'] = f"❌ Erro ao gerar PIX: {pix_result.get('error')}"
            else:
                state['response_text'] = f"❌ Erro ao criar pedido: {order_result.get('error')}"
        
        elif intent == IntentType.SELECT_PAYMENT_CASH:
            order_result = create_order.invoke({
                'session_id': state['session_id'],
                'payment_method': 'cash',
                'delivery_method': state['order_data'].get('delivery_method', 'pickup')
            })
            
            if order_result.get('success'):
                state['order_data']['order_id'] = order_result.get('order_id')
                state['order_data']['order_number'] = order_result.get('order_number')
                
                delivery_text = 'entregue' if state['order_data'].get('delivery_method') == 'delivery' else 'pronto para retirada'
                
                state['response_text'] = (
                    f"✅ *Pedido confirmado!*\n\n"
                    f"Número: *{order_result.get('order_number')}*\n"
                    f"Total: R$ {order_result.get('total', 0):.2f}\n"
                    f"Pagamento: Dinheiro\n\n"
                    f"Seu pedido será {delivery_text} em breve!\n\n"
                    f"Obrigado pela preferência! 🍝"
                )
                state['current_state'] = ConversationState.ORDER_CONFIRMED
            else:
                state['response_text'] = f"❌ Erro: {order_result.get('error')}"
        
        elif intent == IntentType.CHECK_STATUS:
            import re
            match = re.search(r'(PAS\d+|\d{10,})', state['messages'][-1].content if state['messages'] else '')
            if match:
                order_number = match.group(1)
                state['response_text'] = check_order_status(order_number)
            else:
                state['response_text'] = "Por favor, informe o número do pedido. Exemplo: status PAS2502241234"
        
        elif intent == IntentType.HUMAN_HANDOFF:
            state['response_text'] = (
                "👨‍💼 *Transferindo para atendente humano...*\n\n"
                "Um de nossos atendentes vai te atender em breve.\n\n"
                "Por favor, aguarde."
            )
            state['current_state'] = ConversationState.HUMAN_HANDOFF
        
        elif intent == IntentType.RESET:
            clear_cart(state['session_id'])
            state['cart'] = {'items': [], 'total': 0.0}
            state['order_data'] = {
                'order_id': None, 'order_number': None, 'payment_method': None,
                'delivery_method': None, 'delivery_address': None,
                'delivery_fee': None, 'subtotal': 0.0, 'total': 0.0,
            }
            state['response_text'] = (
                "🔄 *Fluxo reiniciado!*\n\n"
                "Como posso ajudar você agora?\n"
                "• Ver *cardápio*\n"
                "• Fazer um *pedido*"
            )
            state['current_state'] = ConversationState.GREETING
        
        else:
            state['response_text'] = (
                "Não entendi bem. Você pode:\n"
                "• Digitar *cardápio* para ver produtos\n"
                "• Digitar *carrinho* para ver seu pedido\n"
                "• Digitar *finalizar* para concluir\n"
                "• Digitar *atendente* para falar com uma pessoa"
            )
        
        state['context_source'] = ContextSource.HANDLER
        
    except Exception as e:
        logger.error(f"Erro no handler: {e}")
        state['response_text'] = "Desculpe, tive um problema. Tente novamente ou digite 'atendente'."
        state['error_count'] = state.get('error_count', 0) + 1
        state['context_source'] = ContextSource.FALLBACK
    
    return state


def generate_llm_response_node(state: PastitaState) -> PastitaState:
    """Nó de geração de resposta via LLM."""
    state['response_text'] = (
        "Desculpe, não entendi direito. 😕\n\n"
        "Pode reformular ou escolher uma opção:\n"
        "• *cardápio* - Ver produtos\n"
        "• *carrinho* - Ver seu pedido\n"
        "• *finalizar* - Concluir compra\n"
        "• *atendente* - Falar com pessoa"
    )
    state['context_source'] = ContextSource.LLM
    return state


def update_state_node(state: PastitaState) -> PastitaState:
    """Nó de atualização de estado."""
    state['last_activity'] = datetime.now().isoformat()
    state['previous_state'] = state['current_state']
    
    if state.get('response_text'):
        state['messages'].append(AIMessage(content=state['response_text']))
    
    if len(state['messages']) > 20:
        state['messages'] = state['messages'][-20:]
    
    return state


def error_recovery_node(state: PastitaState) -> PastitaState:
    """Nó de recuperação de erros."""
    error_count = state.get('error_count', 0)
    
    if error_count >= 3:
        state['response_text'] = (
            "⚠️ Estou tendo dificuldades técnicas.\n\n"
            "Gostaria de falar com um atendente humano?\n"
            "Digite *atendente* para ser transferido."
        )
        state['current_state'] = ConversationState.ERROR
    else:
        state['response_text'] = (
            "Desculpe, tive um problema. Pode tentar novamente?\n\n"
            "Ou digite *menu* para voltar ao início."
        )
    
    state['context_source'] = ContextSource.FALLBACK
    return state


def should_use_handler(state: PastitaState) -> str:
    """Decide se deve usar handler."""
    if state.get('error_count', 0) > 0:
        return "error"
    if state['context_source'] == ContextSource.HANDLER:
        return "handler"
    return "llm"


def build_pastita_graph() -> StateGraph:
    """Constrói o grafo de estado completo."""
    workflow = StateGraph(PastitaState)
    
    workflow.add_node("detect_intent", detect_intent_node)
    workflow.add_node("route_context", route_context_node)
    workflow.add_node("execute_handler", execute_handler_node)
    workflow.add_node("generate_llm_response", generate_llm_response_node)
    workflow.add_node("update_state", update_state_node)
    workflow.add_node("error_recovery", error_recovery_node)
    
    workflow.set_entry_point("detect_intent")
    
    workflow.add_edge("detect_intent", "route_context")
    
    workflow.add_conditional_edges(
        "route_context",
        should_use_handler,
        {
            "handler": "execute_handler",
            "llm": "generate_llm_response",
            "error": "error_recovery",
        }
    )
    
    workflow.add_edge("execute_handler", "update_state")
    workflow.add_edge("generate_llm_response", "update_state")
    workflow.add_edge("error_recovery", "update_state")
    workflow.add_edge("update_state", END)
    
    return workflow.compile()


# Instância global do grafo
_pastita_graph = None


def get_pastita_graph():
    """Retorna instância singleton do grafo."""
    global _pastita_graph
    if _pastita_graph is None:
        _pastita_graph = build_pastita_graph()
    return _pastita_graph
