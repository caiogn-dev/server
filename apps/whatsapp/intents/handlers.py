"""
WhatsApp Intent Handlers

Handlers específicos para cada tipo de intenção detectada.
Cada handler retorna uma resposta adequada ou None para fallback.
"""
import re
import unicodedata
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

from apps.whatsapp.intents.detector import IntentType, IntentData
from apps.automation.models import AutoMessage
from apps.stores.models import StoreProduct
from apps.stores.models.order import StoreOrder as Order

logger = logging.getLogger(__name__)


# ─── Shared helper: dynamic item extraction ───────────────────────────────────

def _normalize_text(s: str) -> str:
    """Remove accents and lowercase for fuzzy product matching."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', s.lower())
        if unicodedata.category(c) != 'Mn'
    )


def _parse_items_from_text_dynamic(text: str, store) -> List[Dict[str, Any]]:
    """
    Extrai pares (product_id, quantity) de um texto livre.

    Estratégia (sem keywords hardcoded):
    1. Regex extrai pares (quantity, search_term) do texto.
    2. Para cada par, busca o produto da loja que melhor corresponde ao search_term:
       a. Correspondência exata (accent-insensitive substring)
       b. Primeira palavra do nome do produto dentro do search_term
       c. Qualquer palavra do search_term dentro do nome do produto
    3. Se nenhum par qty+nome for encontrado, tenta apenas nome → qty=1.
    """
    if not store:
        return []

    text_lower = text.lower().strip()
    if not text_lower:
        return []

    products = list(StoreProduct.objects.filter(store=store, is_active=True))
    if not products:
        return []

    # Pre-compute normalized names once
    normalized_products = [
        (p, _normalize_text(p.name), p.name.lower().split())
        for p in products
    ]

    def _match(search_term: str) -> Optional[Any]:
        norm_search = _normalize_text(search_term)
        best = None
        for product, norm_name, words in normalized_products:
            # Full name substring match (most precise)
            if norm_search in norm_name or norm_name in norm_search:
                return product
            # First word of product in search term
            if words and len(words[0]) > 2 and words[0] in search_term:
                best = best or product
            # Any word of search in product name
            for word in search_term.split():
                if len(word) > 3 and word in norm_name:
                    best = best or product
        return best

    # Patterns: "2 rondelli de frango", "quero 1 lasanha", "1x nhoque"
    quantity_patterns = [
        r'(\d+)\s*x?\s+([\w\s]{3,40}?)(?:\s+(?:e|com|sem|por|para)|$)',
        r'(\d+)\s+([\w\s]{3,40})',
    ]

    found_ids: set = set()
    items: List[Dict[str, Any]] = []

    for pattern in quantity_patterns:
        for qty_str, search_term in re.findall(pattern, text_lower):
            search_term = search_term.strip()
            if not search_term:
                continue
            quantity = int(qty_str)
            product = _match(search_term)
            if product and str(product.id) not in found_ids:
                found_ids.add(str(product.id))
                items.append({'product_id': str(product.id), 'quantity': quantity})

    # Fallback: no quantity mentioned — try just the name, qty=1
    if not items:
        product = _match(text_lower)
        if product:
            items.append({'product_id': str(product.id), 'quantity': 1})

    logger.info('[_parse_items_from_text_dynamic] store=%s text=%r items=%d',
                getattr(store, 'slug', store), text[:60], len(items))
    return items


class HandlerResult:
    """Resultado do processamento de um handler"""
    
    def __init__(
        self,
        response_text: Optional[str] = None,
        use_interactive: bool = False,
        interactive_type: Optional[str] = None,  # 'buttons', 'list'
        interactive_data: Optional[Dict] = None,
        requires_llm: bool = False
    ):
        self.response_text = response_text
        self.use_interactive = use_interactive
        self.interactive_type = interactive_type
        self.interactive_data = interactive_data or {}
        self.requires_llm = requires_llm
    
    @classmethod
    def text(cls, text: str) -> 'HandlerResult':
        """Cria resultado com texto simples"""
        return cls(response_text=text)
    
    @classmethod
    def buttons(cls, body: str, buttons: list, header: Optional[str] = None, 
                footer: Optional[str] = None) -> 'HandlerResult':
        """Cria resultado com botões interativos"""
        return cls(
            response_text="BUTTONS_SENT",
            use_interactive=True,
            interactive_type='buttons',
            interactive_data={
                'body': body, 
                'buttons': buttons,
                'header': header,
                'footer': footer
            }
        )
    
    @classmethod
    def list_message(cls, body: str, button: str, sections: list) -> 'HandlerResult':
        """Cria resultado com lista interativa"""
        return cls(
            response_text="LIST_SENT",
            use_interactive=True,
            interactive_type='list',
            interactive_data={'body': body, 'button': button, 'sections': sections}
        )
    
    @classmethod
    def needs_llm(cls) -> 'HandlerResult':
        """Indica que precisa de LLM"""
        return cls(requires_llm=True)
    
    @classmethod
    def none(cls) -> 'HandlerResult':
        """Sem resposta automática"""
        return cls()


class IntentHandler:
    """Handler base para intenções"""

    def __init__(self, account, conversation, company_profile=None):
        self.account = account
        self.conversation = conversation
        self.company_profile = company_profile or getattr(account, 'company_profile', None)
        self._whatsapp_service = None
        self.store = self._get_store()

    @property
    def whatsapp_service(self):
        """Lazy import to avoid circular import"""
        if self._whatsapp_service is None:
            from apps.whatsapp.services.whatsapp_api_service import WhatsAppAPIService
            self._whatsapp_service = WhatsAppAPIService(self.account)
        return self._whatsapp_service
    
    def _get_store(self):
        """Retorna a loja associada"""
        if self.company_profile and hasattr(self.company_profile, 'store'):
            return self.company_profile.store
        return None

    def _send_pix_confirmation(self, order, pix_code: str) -> 'HandlerResult':
        """Envia confirmação do pedido em duas mensagens:
        1. Resumo do pedido com aviso de que o PIX vem a seguir
        2. Apenas o código PIX (fácil de copiar)
        """
        items_text = '\n'.join(
            f"• {item.quantity}x {item.product_name}"
            for item in order.items.all()
        )
        msg1 = (
            f"✅ *Pedido #{order.order_number} confirmado!*\n\n"
            f"{items_text}\n\n"
            f"💰 *Total: R$ {float(order.total):.2f}*\n\n"
            f"💳 Pague via PIX — o código está na próxima mensagem 👇"
        )
        try:
            self.whatsapp_service.send_text_message(
                to=self.conversation.phone_number,
                text=msg1,
            )
        except Exception as exc:
            logger.warning("[_send_pix_confirmation] Erro ao enviar msg1: %s", exc)

        # Segunda mensagem: somente o código
        return HandlerResult.text(pix_code)
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        """Processa a intenção e retorna resultado"""
        raise NotImplementedError
    
    def get_customer_name(self) -> str:
        """Retorna nome do cliente"""
        return self.conversation.contact_name or 'Cliente'


class GreetingHandler(IntentHandler):
    """Handler para saudações usando template refinado"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        customer_name = self.get_customer_name()
        logger.info(f"[GreetingHandler] Saudação para {customer_name}")

        store_name = self.company_profile.company_name if self.company_profile else 'Pastita'

        # Usa template refinado do Jasper Market
        from apps.whatsapp.services.templates import JasperTemplates
        template = JasperTemplates.greeting(
            customer_name=customer_name,
            store_name=store_name
        )

        return HandlerResult.buttons(
            body=template.body,
            buttons=template.buttons,
            header=template.header,
            footer=template.footer
        )


class PriceCheckHandler(IntentHandler):
    """Handler para consulta de preços"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        entities = intent_data.get('entities', {})
        product_name = entities.get('product_name')
        
        logger.info(f"Price check for: {product_name}")
        
        if not self.store:
            return HandlerResult.text("Desculpe, não encontrei informações da loja no momento. 😔")
        
        # Se mencionou produto específico
        if product_name:
            products = StoreProduct.objects.filter(
                store=self.store,
                name__icontains=product_name,
                is_active=True
            )[:5]
            
            if products:
                if len(products) == 1:
                    # Produto único - mostra detalhes
                    p = products[0]
                    response = (
                        f"💰 *{p.name}*\n"
                        f"Preço: *R$ {p.price}*\n\n"
                    )
                    if p.description:
                        response += f"{p.description}\n\n"
                    
                    # Botão para adicionar ao carrinho
                    return HandlerResult.buttons(
                        body=response,
                        buttons=[
                            {'id': f'add_{p.id}_1', 'title': '🛒 Adicionar'},
                            {'id': f'details_{p.id}', 'title': 'ℹ️ Detalhes'},
                            {'id': 'view_catalog', 'title': '📋 Ver mais'},
                        ]
                    )
                else:
                    # Múltiplos produtos - lista
                    response = f"💰 Encontrei esses produtos:\n\n"
                    for p in products:
                        response += f"• *{p.name}*: R$ {p.price}\n"
                    
                    response += "\nQual você quer?"
                    return HandlerResult.text(response)
            else:
                return HandlerResult.text(
                    f"Não encontrei '{product_name}'. 😕\n\n"
                    f"Quer ver nosso cardápio completo?"
                )
        
        # Retorna produtos populares
        products = StoreProduct.objects.filter(
            store=self.store,
            is_active=True
        ).order_by('-created_at')[:5]
        
        if products:
            response = f"💰 *Alguns dos nossos produtos:*\n\n"
            for p in products:
                response += f"• {p.name}: R$ {p.price}\n"
            
            response += f"\nQuer ver mais opções ou detalhes de algum?"
            return HandlerResult.text(response)
        
        return HandlerResult.text(
            "Nosso cardápio está sendo atualizado! 🔄\n"
            "Tente novamente em alguns minutos."
        )


class ProductMentionHandler(IntentHandler):
    """Handler quando usuário menciona produto sem quantidade - mostra TODOS os tipos"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        message = intent_data.get('original_message', '').lower().strip()
        logger.info(f"[ProductMentionHandler] Mensagem: {message}")
        
        if not self.store:
            return HandlerResult.text("Cardápio não disponível. 😔")
        
        # Busca TODOS os produtos ativos
        all_products = StoreProduct.objects.filter(
            store=self.store,
            is_active=True
        )
        
        # Se digitou algo genérico como "rondelli", "lasanha", "nhoque"
        # Mostra TODOS desse tipo
        search_term = message.lower().strip()
        
        # Remove palavras comuns
        search_term = search_term.replace('de ', '').replace('com ', '').replace('e ', '')
        
        # Busca produtos que CONTÊM o termo (para pegar todos os tipos)
        matched_products = []
        for product in all_products:
            product_name_lower = product.name.lower()
            # Verifica se o termo está no nome do produto
            if search_term in product_name_lower:
                matched_products.append(product)
                logger.info(f"[ProductMentionHandler] Match: {product.name}")
        
        # Se encontrou produtos, mostra todos
        if matched_products:
            if len(matched_products) == 1:
                # Só um tipo disponível
                p = matched_products[0]
                return HandlerResult.text(
                    f"*{p.name}* - R$ {p.price}\n\n"
                    f"Quantos você quer? 😊"
                )
            else:
                # Vários tipos - mostra todos
                product_list = "\n".join([f"{i+1}. {p.name} - R$ {p.price}" 
                                          for i, p in enumerate(matched_products[:10])])
                return HandlerResult.text(
                    f"🍝 *{search_term.title()}* - Temos esses:\n\n"
                    f"{product_list}\n\n"
                    f"Qual você quer? Digite o número ou o nome! 👇"
                )
        
        # Se não encontrou com o termo, tenta match parcial
        # Ex: "rondelli" deve pegar "Rondelli de Frango", "Rondelli de Presunto", etc
        keyword_products = []
        for product in all_products:
            product_words = product.name.lower().split()
            # Pega a primeira palavra do produto (ex: "Rondelli" de "Rondelli de Frango")
            if product_words:
                first_word = product_words[0]
                if search_term == first_word or first_word in search_term:
                    keyword_products.append(product)
        
        if keyword_products:
            product_list = "\n".join([f"{i+1}. {p.name} - R$ {p.price}" 
                                      for i, p in enumerate(keyword_products[:10])])
            return HandlerResult.text(
                f"🍝 *{search_term.title()}* - Temos esses:\n\n"
                f"{product_list}\n\n"
                f"Qual você quer? Digite o número ou o nome! 👇"
            )
        
        # Não encontrou - mostra todos os produtos disponíveis
        available = all_products[:10]
        if available:
            product_list = "\n".join([f"• {p.name} - R$ {p.price}" for p in available])
            return HandlerResult.text(
                f"Temos esses produtos:\n\n"
                f"{product_list}\n\n"
                f"Qual você quer?"
            )
        
        return HandlerResult.text(
            "Cardápio em atualização. Tente novamente em breve! 🔄"
        )


class MenuRequestHandler(IntentHandler):
    """Handler para solicitação de cardápio"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info(f"[MenuRequestHandler] Store: {self.store}")
        
        if not self.store:
            logger.error("[MenuRequestHandler] Sem store!")
            return HandlerResult.text("Cardápio não disponível no momento. 😔")
        
        # Busca TODOS os produtos ativos primeiro
        all_products = StoreProduct.objects.filter(
            store=self.store,
            is_active=True
        )
        
        total_products = all_products.count()
        logger.info(f"[MenuRequestHandler] Total produtos ativos: {total_products}")
        
        if total_products == 0:
            logger.error("[MenuRequestHandler] Nenhum produto ativo encontrado!")
            return HandlerResult.text("Nenhum produto disponível no momento. 😔")
        
        # Tenta agrupar por categoria
        products_by_category = {}
        for product in all_products:
            cat_name = product.category.name if product.category else 'Outros'
            # Extrai nome curto da categoria (última parte)
            if ' - ' in cat_name:
                cat_name = cat_name.split(' - ')[-1]
            
            if cat_name not in products_by_category:
                products_by_category[cat_name] = []
            products_by_category[cat_name].append(product)
        
        logger.info(f"[MenuRequestHandler] Categorias: {list(products_by_category.keys())}")
        
        # Cria seções - máximo 10 linhas no total
        sections = []
        total_rows = 0
        max_rows = 10
        
        for cat_name, products in list(products_by_category.items())[:5]:
            if total_rows >= max_rows:
                break
            
            # Max 3 produtos por categoria
            products_to_show = products[:3]
            
            rows = [
                {
                    'id': f'product_{p.id}',
                    'title': p.name[:24],
                    'description': f'R$ {p.price}'
                }
                for p in products_to_show
            ]
            
            # Verifica limite
            if total_rows + len(rows) > max_rows:
                rows = rows[:max_rows - total_rows]
            
            if rows:
                section = {
                    'title': cat_name[:24],
                    'rows': rows
                }
                sections.append(section)
                total_rows += len(rows)
                logger.info(f"[MenuRequestHandler] Adicionada categoria '{cat_name}' com {len(rows)} produtos")
        
        # Se não conseguiu criar seções, mostra em formato texto
        if not sections:
            logger.warning("[MenuRequestHandler] Sem seções, usando fallback de texto")
            if all_products.count() > 0:
                products = all_products[:10]
                product_list = "\n".join([f"• {p.name} - R$ {p.price}" for p in products])
                return HandlerResult.text(
                    f"📋 *Cardápio - {self.store.name}*\n\n"
                    f"{product_list}\n\n"
                    f"Para pedir, digite quantos você quer!\n"
                    f"Ex: *2 rondelli de frango*"
                )
            else:
                return HandlerResult.text("Nenhum produto disponível no momento. 😔")
        
        # Envia lista interativa
        logger.info(f"[MenuRequestHandler] Enviando lista com {len(sections)} seções")
        return HandlerResult.list_message(
            body=f"📋 *Cardápio - {self.store.name}*\n\nEscolha uma opção:",
            button="Ver opções",
            sections=sections
        )


class BusinessHoursHandler(IntentHandler):
    """Handler para horário de funcionamento"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        if not self.store:
            return HandlerResult.text(
                "🕐 Nosso horário de atendimento:\n"
                "Segunda a Sábado: 10h às 20h\n"
                "Domingo: 11h às 18h"
            )
        
        from datetime import datetime
        
        # Pega horário de hoje
        today = datetime.now().strftime('%A').lower()
        
        # Mapeia dias da semana
        day_names = {
            'monday': 'Segunda', 'tuesday': 'Terça', 'wednesday': 'Quarta',
            'thursday': 'Quinta', 'friday': 'Sexta', 'saturday': 'Sábado', 'sunday': 'Domingo'
        }
        
        # Tenta pegar horário do banco
        try:
            hours = self.store.operating_hours or {}
            today_hours = hours.get(today, {})
            
            if today_hours:
                open_time = today_hours.get('open', '10:00')
                close_time = today_hours.get('close', '20:00')
                
                response = (
                    f"🕐 *Horário de hoje ({day_names.get(today, 'Hoje')}):*\n"
                    f"{open_time} às {close_time}\n\n"
                )
            else:
                response = "🕐 *Horário de hoje:* Fechado\n\n"
            
            # Adiciona horário completo
            response += "*Horário da semana:*\n"
            for day_code, day_name in day_names.items():
                day_hours = hours.get(day_code, {})
                if day_hours:
                    response += f"{day_name}: {day_hours.get('open', '--:--')} às {day_hours.get('close', '--:--')}\n"
                else:
                    response += f"{day_name}: Fechado\n"
            
            return HandlerResult.text(response)
            
        except Exception as e:
            logger.error(f"Error getting business hours: {e}")
            return HandlerResult.text(
                "🕐 Nosso horário de atendimento:\n"
                "Segunda a Sábado: 10h às 20h\n"
                "Domingo: 11h às 18h"
            )


class DeliveryInfoHandler(IntentHandler):
    """Handler para informações de entrega"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        if not self.store:
            return HandlerResult.text(
                "🚚 *Informações de Entrega*\n\n"
                "• Tempo médio: 40-60 minutos\n"
                "• Taxa de entrega: a consultar\n"
                "• Área de cobertura: Consulte seu CEP\n\n"
                "Quer fazer um pedido?"
            )
        
        try:
            delivery_settings = self.store.delivery_settings or {}
            
            response = f"🚚 *{self.store.name} - Entrega*\n\n"
            
            # Tempo de entrega
            delivery_time = delivery_settings.get('delivery_time', '40-60')
            response += f"⏱️ Tempo médio: *{delivery_time} minutos*\n"
            
            # Taxa de entrega
            delivery_fee = delivery_settings.get('delivery_fee')
            if delivery_fee:
                response += f"💰 Taxa de entrega: *R$ {delivery_fee}*\n"
            else:
                response += f"💰 Taxa de entrega: *Consultar*\n"
            
            # Pedido mínimo
            min_order = delivery_settings.get('min_order')
            if min_order:
                response += f"📦 Pedido mínimo: *R$ {min_order}*\n"
            
            response += "\nQuer fazer um pedido?"
            
            return HandlerResult.buttons(
                body=response,
                buttons=[
                    {'id': 'start_order', 'title': '🛒 Fazer Pedido'},
                    {'id': 'check_cep', 'title': '📍 Consultar CEP'},
                    {'id': 'view_menu', 'title': '📋 Cardápio'},
                ]
            )
            
        except Exception as e:
            logger.error(f"Error getting delivery info: {e}")
            return HandlerResult.text(
                "🚚 *Informações de Entrega*\n\n"
                "• Tempo médio: 40-60 minutos\n"
                "• Taxa de entrega: a consultar\n\n"
                "Quer fazer um pedido?"
            )


class TrackOrderHandler(IntentHandler):
    """Handler para rastrear pedido"""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        entities = intent_data.get('entities', {})
        order_number = entities.get('order_number')

        logger.info(f"Track order: number={order_number}")

        if not self.store and not order_number:
            return HandlerResult.text(
                "Não encontrei pedidos recentes. 😕\n\n"
                "Quer fazer um pedido novo?"
            )

        # Se não informou número, busca último pedido
        if not order_number:
            last_order = Order.objects.filter(
                customer_phone=self.conversation.phone_number,
                store=self.store
            ).order_by('-created_at').first()
        else:
            last_order = Order.objects.filter(
                order_number=order_number,
                customer_phone=self.conversation.phone_number
            ).first()
        
        if last_order:
            status_map = {
                'pending': '⏳ Aguardando confirmação',
                'confirmed': '✅ Pedido confirmado',
                'preparing': '👨‍🍳 Em preparo',
                'ready': '✨ Pronto para retirada',
                'out_for_delivery': '🛵 Saiu para entrega',
                'delivered': '📦 Entregue',
                'cancelled': '❌ Cancelado',
            }
            
            status_display = status_map.get(last_order.status, f'Status: {last_order.status}')
            
            response = (
                f"📦 *Pedido #{last_order.order_number}*\n"
                f"{status_display}\n"
                f"Data: {last_order.created_at.strftime('%d/%m/%Y %H:%M')}\n"
                f"Total: R$ {last_order.total}"
            )
            
            # Se ainda está em andamento, mostra botão de acompanhamento
            if last_order.status in ['pending', 'confirmed', 'preparing', 'out_for_delivery']:
                return HandlerResult.buttons(
                    body=response,
                    buttons=[
                        {'id': f'track_{last_order.id}', 'title': '🔄 Atualizar'},
                        {'id': 'contact_support', 'title': '📞 Suporte'},
                    ]
                )
            
            return HandlerResult.text(response)
        
        return HandlerResult.text(
            "Não encontrei pedidos recentes. 😕\n\n"
            "Quer fazer um pedido novo?"
        )


class CreateOrderHandler(IntentHandler):
    """Handler para criar pedido - Extrai produtos da mensagem e cria pedido real"""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info(f"[CreateOrderHandler] Iniciando handle")
        
        # Pega mensagem atual e histórico
        message_text = intent_data.get('original_message', '')
        logger.info(f"[CreateOrderHandler] Mensagem: {message_text}")
        
        # Tenta extrair produtos da mensagem atual ou do contexto
        items = self._extract_items_from_context(intent_data)
        
        if not items:
            # Se não achou itens, tenta extrair da mensagem atual
            items = self._parse_items_from_text(message_text)
        
        logger.info(f"[CreateOrderHandler] Itens extraídos: {items}")
        
        if items:
            # Cria pedido real
            return self._create_real_order(items, message_text)
        
        # Se não achou itens, inicia fluxo normal de pedido
        return self._start_order_flow()
    
    def _extract_items_from_context(self, intent_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Tenta extrair produtos do contexto da conversa"""
        items = []
        
        # Busca nas mensagens anteriores da conversa
        try:
            from apps.whatsapp.models import Message
            recent_messages = Message.objects.filter(
                conversation=self.conversation,
                direction='inbound',
                status='received'
            ).order_by('-created_at')[:5]
            
            for msg in recent_messages:
                parsed = self._parse_items_from_text(msg.body or '')
                if parsed:
                    items.extend(parsed)
                    break  # Usa só o primeiro que encontrar
                    
        except Exception as e:
            logger.warning(f"[CreateOrderHandler] Erro ao buscar contexto: {e}")
        
        return items
    
    def _create_real_order(self, items: List[Dict], message_text: str) -> HandlerResult:
        """Cria pedido real no banco"""
        from apps.whatsapp.services import create_order_from_whatsapp
        
        store_slug = getattr(self.store, 'slug', 'pastita')
        logger.info(f"[CreateOrderHandler] Criando pedido para {self.conversation.phone_number}")
        
        result = create_order_from_whatsapp(
            store_slug=store_slug,
            phone_number=self.conversation.phone_number,
            items=items,
            customer_name=self.get_customer_name(),
            delivery_address='',
            customer_notes=f'Pedido via WhatsApp: {message_text}'
        )
        
        logger.info(f"[CreateOrderHandler] Resultado: {result.get('success')}")
        
        if result.get('success'):
            order = result['order']
            pix_data = result.get('pix_data', {})
            
            if pix_data.get('success'):
                pix_code = pix_data.get('pix_code', '')
                
                # Atualiza sessão com dados do pedido
                from apps.automation.services import get_session_manager
                session_manager = get_session_manager(self.account, self.conversation.phone_number)
                session_manager.set_payment_pending(
                    order_id=str(order.id),
                    pix_code=pix_code,
                    cart_total=float(order.total)
                )
                
                return self._send_pix_confirmation(order, pix_code)
            else:
                # Pedido criado mas PIX falhou
                error_msg = pix_data.get('error', 'Erro ao gerar PIX')
                return HandlerResult.text(
                    f"✅ *Pedido #{order.order_number} criado!*\n\n"
                    f"💰 Total: R$ {order.total}\n"
                    f"⚠️ Erro no PIX: {error_msg}\n\n"
                    f"Você pode pagar na entrega ou tentar novamente."
                )
        else:
            error = result.get('error', 'Erro desconhecido')
            return HandlerResult.text(
                f"❌ *Erro ao criar pedido:*\n{error}\n\n"
                f"Tente novamente ou fale com um atendente."
            )
    
    def _start_order_flow(self) -> HandlerResult:
        """Inicia fluxo de pedido quando não achou itens"""
        from apps.automation.services import get_session_manager
        session_manager = get_session_manager(
            self.account,
            self.conversation.phone_number
        )
        
        session_manager.get_or_create_session()
        context = session_manager.get_context()
        context.start_order_flow()
        
        return HandlerResult.buttons(
            body=(
                f"🛒 *Vamos fazer seu pedido, {self.get_customer_name()}!*\n\n"
                f"Como prefere começar?"
            ),
            buttons=[
                {'id': 'order_catalog', 'title': '📋 Ver Cardápio'},
                {'id': 'order_quick', 'title': '⚡ Pedido Rápido'},
                {'id': 'order_help', 'title': '❓ Preciso de Ajuda'},
            ]
        )
    
    def _parse_items_from_text(self, text: str) -> List[Dict[str, Any]]:
        """Extrai itens do texto — busca dinâmica nos produtos da loja (sem keywords hardcoded)."""
        return _parse_items_from_text_dynamic(text, self.store)


class QuickOrderHandler(IntentHandler):
    """Handler para pedido rápido - cria pedido diretamente"""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info(f"[QuickOrderHandler] Iniciando handle")

        # Extrai itens da mensagem original
        message_text = intent_data.get('original_message', '')
        logger.info(f"[QuickOrderHandler] Mensagem original: {message_text}")

        if not message_text:
            return HandlerResult.text(
                "🛒 *Pedido Rápido*\n\n"
                "Digite seu pedido:\n"
                "• 'Quero 2 rondelli de frango'\n"
                "• '1 lasanha e 1 nhoque'\n\n"
                "Ou digite 'cardápio' para ver opções."
            )

        # Processa itens e cria pedido
        from apps.whatsapp.services import create_order_from_whatsapp

        store_slug = getattr(self.store, 'slug', 'pastita')
        logger.info(f"[QuickOrderHandler] Store slug: {store_slug}")

        # Extrai itens do texto
        items = self._parse_items_from_text(message_text)
        logger.info(f"[QuickOrderHandler] Itens extraídos: {items}")

        if not items:
            logger.warning(f"[QuickOrderHandler] Nenhum item encontrado na mensagem: {message_text}")
            return HandlerResult.text(
                "❌ Não consegui identificar os itens do seu pedido.\n\n"
                "Tente escrever de outra forma ou digite 'cardápio'."
            )

        # Cria o pedido
        logger.info(f"[QuickOrderHandler] Criando pedido para {self.conversation.phone_number}")
        result = create_order_from_whatsapp(
            store_slug=store_slug,
            phone_number=self.conversation.phone_number,
            items=items,
            customer_name=self.get_customer_name(),
            delivery_address='',
            customer_notes=f'Pedido rápido via WhatsApp: {message_text}'
        )

        logger.info(f"[QuickOrderHandler] Resultado da criação: {result.get('success')}")

        if result.get('success'):
            order = result['order']
            pix_data = result.get('pix_data', {})
            
            logger.info(f"[QuickOrderHandler] Pedido criado: {order.order_number}")
            logger.info(f"[QuickOrderHandler] PIX data: {pix_data}")

            if pix_data.get('success'):
                pix_code = pix_data.get('pix_code', '')
                logger.info(f"[QuickOrderHandler] PIX code: {pix_code[:50]}...")
                
                return self._send_pix_confirmation(order, pix_code)
            else:
                error_msg = pix_data.get('error', 'Erro desconhecido')
                logger.error(f"[QuickOrderHandler] Erro no PIX: {error_msg}")
                return HandlerResult.text(
                    f"✅ *Pedido #{order.order_number} criado!*\n\n"
                    f"💰 Total: R$ {order.total}\n"
                    f"📋 Itens:\n{self._format_order_items(order)}\n\n"
                    f"⚠️ *Erro ao gerar PIX:* {error_msg}\n"
                    f"Você pode pagar na entrega ou tentar novamente."
                )
        else:
            error = result.get('error', 'Erro desconhecido')
            logger.error(f"[QuickOrderHandler] Erro ao criar pedido: {error}")
            return HandlerResult.text(
                f"❌ *Erro ao criar pedido:*\n{error}\n\n"
                f"Se preferir, ligue para nós ou tente pelo site."
            )

    def _parse_items_from_text(self, text: str) -> List[Dict[str, Any]]:
        """Extrai itens do texto do usuário — busca dinâmica nos produtos da loja."""
        return _parse_items_from_text_dynamic(text, self.store)

    def _format_order_items(self, order) -> str:
        """Formata itens do pedido para exibição"""
        items_text = ""
        for item in order.items.all():
            items_text += f"• {item.quantity}x {item.product_name} = R$ {item.total}\n"
        return items_text


class PaymentStatusHandler(IntentHandler):
    """Handler para status de pagamento"""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        # Busca sessão ativa primeiro
        from apps.automation.services import get_session_manager
        session_manager = get_session_manager(
            self.account,
            self.conversation.phone_number
        )

        # Verifica se há sessão com pagamento pendente
        if session_manager.is_payment_pending():
            session_data = session_manager.get_session_data()
            pix_code = session_data.get('pix_code', '')

            if pix_code:
                return HandlerResult.buttons(
                    body=(
                        f"💳 *Pagamento Pendente*\n\n"
                        f"Valor: R$ {session_data.get('cart_total', 0)}\n\n"
                        f"*Código PIX:*\n`{pix_code[:30]}...`\n\n"
                        f"Cole este código no seu aplicativo bancário para pagar."
                    ),
                    buttons=[
                        {'id': 'pix_copy', 'title': '📋 Ver código PIX'},
                        {'id': 'send_comprovante', 'title': '📤 Enviar Comprovante'},
                        {'id': 'cancel_order', 'title': '❌ Cancelar'},
                    ]
                )

        # Fallback: busca último pedido pendente no banco
        pending_order = Order.objects.filter(
            customer_phone=self.conversation.phone_number,
            **({"store": self.store} if self.store else {}),
            status='pending_payment'
        ).order_by('-created_at').first()

        if pending_order and pending_order.pix_code:
            # Atualiza sessão com dados do pedido
            session_manager.set_payment_pending(
                pix_code=pending_order.pix_code,
                payment_id=str(pending_order.id)
            )

            return HandlerResult.buttons(
                body=(
                    f"💳 *Pagamento Pendente*\n\n"
                    f"Pedido: #{pending_order.order_number}\n"
                    f"Valor: R$ {pending_order.total}\n\n"
                    f"*Código PIX:*\n`{pending_order.pix_code[:30]}...`\n\n"
                    f"Cole este código no seu aplicativo bancário para pagar."
                ),
                buttons=[
                    {'id': f'pix_copy_{pending_order.id}', 'title': '📋 Ver código PIX'},
                    {'id': 'send_comprovante', 'title': '📤 Enviar Comprovante'},
                    {'id': 'cancel_order', 'title': '❌ Cancelar'},
                ]
            )

        return HandlerResult.text(
            "Não encontrei pagamentos pendentes. ✅\n\n"
            "Quer fazer um pedido novo?"
        )


class LocationHandler(IntentHandler):
    """Handler para localização/endereço"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        if self.store and self.store.address:
            return HandlerResult.text(
                f"📍 *Endereço*\n\n"
                f"{self.store.name}\n"
                f"{self.store.address}\n\n"
                f"Aguardamos sua visita! 😊"
            )
        
        return HandlerResult.text(
            "📍 Entregamos em toda a região!\n\n"
            "Para fazer um pedido com entrega, é só me informar seu endereço completo."
        )


class ContactHandler(IntentHandler):
    """Handler para contato"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        if self.store and self.store.phone:
            return HandlerResult.text(
                f"📞 *Contato*\n\n"
                f"WhatsApp: {self.store.phone}\n\n"
                f"Estamos aqui para ajudar! 😊"
            )
        
        return HandlerResult.text(
            "📞 *Atendimento*\n\n"
            "Estou aqui para ajudar!\n"
            "Se precisar falar com um atendente humano, digite 'atendente'."
        )


class CancelOrderHandler(IntentHandler):
    """Handler para cancelar pedido em andamento"""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info(f"Cancel order intent")

        from apps.automation.services import get_session_manager
        session_manager = get_session_manager(
            self.account,
            self.conversation.phone_number
        )

        # Verifica se há pedido para cancelar
        if session_manager.is_order_in_progress():
            session_manager.reset_session()
            return HandlerResult.text(
                "❌ *Pedido cancelado!*\n\n"
                "Seu carrinho foi esvaziado.\n\n"
                "Quer fazer um novo pedido? É só digitar *pedido* ou *cardápio*!"
            )

        return HandlerResult.text(
            "Não encontrei nenhum pedido em andamento para cancelar. ✅\n\n"
            "Quer fazer um pedido?"
        )


class HumanHandoffHandler(IntentHandler):
    """Handler para transferência para humano"""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info(f"Human handoff requested by {self.get_customer_name()}")
        
        # Marca conversa para atendimento humano
        self.conversation.metadata['human_handoff'] = True
        self.conversation.metadata['handoff_requested_at'] = datetime.now().isoformat()
        self.conversation.save()
        
        return HandlerResult.text(
            f"👨‍💼 *Transferindo para atendimento humano...*\n\n"
            f"Um de nossos atendentes vai te atender em breve.\n"
            f"Por favor, aguarde um momento. 🙏"
        )


class FAQHandler(IntentHandler):
    """Handler para perguntas frequentes"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        # Retorna FAQ com botões
        return HandlerResult.buttons(
            body="❓ *Perguntas Frequentes*\n\nO que você quer saber?",
            buttons=[
                {'id': 'faq_hours', 'title': '🕐 Horário'},
                {'id': 'faq_delivery', 'title': '🚚 Entrega'},
                {'id': 'faq_payment', 'title': '💳 Pagamento'},
            ]
        )


class ViewQRCodeHandler(IntentHandler):
    """Handler para mostrar QR Code do PIX"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        from apps.automation.services import get_session_manager
        
        session_manager = get_session_manager(self.account, self.conversation.phone_number)
        session_data = session_manager.get_session_data()
        
        pix_code = session_data.get('pix_code', '')
        order_id = session_data.get('order_id', '')
        
        if not pix_code:
            return HandlerResult.text(
                "❌ Não encontrei um pagamento pendente.\n\n"
                "Quer fazer um pedido novo?"
            )
        
        # Busca o pedido para pegar o ticket_url
        try:
            from apps.stores.models import StoreOrder
            order = StoreOrder.objects.get(id=order_id)
            ticket_url = order.payment_url if hasattr(order, 'payment_url') else None
        except:
            ticket_url = None
        
        if ticket_url:
            return HandlerResult.text(
                f"📱 *QR Code do PIX*\n\n"
                f"Escaneie o QR Code no seu app bancário:\n\n"
                f"{ticket_url}\n\n"
                f"Ou use o código PIX abaixo 👇"
            )
        else:
            return HandlerResult.text(
                f"📱 *QR Code*\n\n"
                f"Use o código PIX que enviei antes:\n"
                f"`{pix_code[:50]}...`\n\n"
                f"Cole no seu app bancário!"
            )


class CopyPixHandler(IntentHandler):
    """Handler para copiar código PIX"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        from apps.automation.services import get_session_manager
        
        session_manager = get_session_manager(self.account, self.conversation.phone_number)
        session_data = session_manager.get_session_data()
        
        pix_code = session_data.get('pix_code', '')
        
        if not pix_code:
            return HandlerResult.text(
                "❌ Não encontrei um pagamento pendente.\n\n"
                "Quer fazer um pedido novo?"
            )
        
        # Retorna o código PIX formatado para cópia fácil
        return HandlerResult.text(
            f"📋 *Código PIX para copiar:*\n\n"
            f"```\n{pix_code}\n```\n\n"
            f"✅ Toque no código acima para copiar\n"
            f"📱 Cole no seu app bancário\n"
            f"⏳ Válido por 30 minutos"
        )


class ProductNotFoundHandler(IntentHandler):
    """Handler quando produto não é encontrado - evita alucinações da IA"""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        if not self.store:
            return HandlerResult.text(
                "❌ Não encontrei esse produto.\n\n"
                "Digite *cardápio* para ver o que temos disponível! 📋"
            )

        # Busca produtos similares
        from apps.stores.models import StoreProduct
        products = StoreProduct.objects.filter(
            store=self.store,
            is_active=True
        )[:5]

        product_list = "\n".join([f"• {p.name} - R$ {p.price}" for p in products])

        return HandlerResult.text(
            f"❌ Não encontrei esse produto.\n\n"
            f"Temos disponíveis:\n{product_list}\n\n"
            f"Qual desses você quer? 😊"
        )


class UnknownHandler(IntentHandler):
    """Handler para intenções desconhecidas — tenta resolver número de quantidade
    (pedido na sequência de seleção de produto) antes de responder com fallback."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info(f"Unknown intent detected")

        message = intent_data.get('original_message', '').lower().strip()

        # Se a mensagem é só um número, pode ser quantidade após seleção de produto
        if message.isdigit():
            qty = int(message)
            if 1 <= qty <= 20:
                result = self._try_pending_product_order(qty)
                if result:
                    return result

        # Verifica se parece ser um pedido (contém números ou nomes de produtos)
        has_number = any(char.isdigit() for char in message)

        if has_number:
            # Parece ser pedido mas não reconheceu o produto
            return HandlerResult.text(
                "❌ Não encontrei esse produto.\n\n"
                "Digite *cardápio* para ver o que temos disponível! 📋"
            )

        # Saudação simples
        if any(word in message for word in ['oi', 'olá', 'ola', 'bom dia', 'boa tarde', 'boa noite']):
            store_name = getattr(self.store, 'name', 'nossa loja') if self.store else 'nossa loja'
            return HandlerResult.buttons(
                body=f"Oi! 👋 Bem-vindo à {store_name}!\n\nComo posso ajudar?",
                buttons=[
                    {'id': 'view_menu', 'title': '📋 Ver Cardápio'},
                    {'id': 'start_order', 'title': '🛒 Fazer Pedido'},
                    {'id': 'contact_support', 'title': '📞 Falar com Atendente'},
                ],
            )

        # Resposta curta e direta para qualquer coisa não reconhecida
        return HandlerResult.text(
            "Oi! Não entendi direito. 😅\n\n"
            "Quer ver nosso cardápio? Digite *cardápio* ou *menu*"
        )

    def _try_pending_product_order(self, qty: int) -> Optional[HandlerResult]:
        """Se há produto pendente na sessão, cria pedido com a quantidade digitada."""
        try:
            from apps.automation.services import get_session_manager
            session_manager = get_session_manager(self.account, self.conversation.phone_number)
            session = session_manager.get_or_create_session()
            context_data = session.context or {}
            product_id = context_data.get('pending_product_id')
            if not product_id:
                return None

            from apps.stores.models import StoreProduct
            product = StoreProduct.objects.get(id=product_id, is_active=True)

            # Limpa produto pendente da sessão
            session.update_context('pending_product_id', None)
            session.update_context('pending_product_name', None)
            session.update_context('pending_product_price', None)

            return InteractiveReplyHandler(
                self.account, self.conversation, self.company_profile
            )._create_order_for_product(product, qty)
        except Exception as exc:
            logger.warning('[UnknownHandler] pending product order failed: %s', exc)
            return None


class InteractiveReplyHandler(IntentHandler):
    """
    Handles interactive replies from WhatsApp (button clicks / list selections).

    ID routing conventions:
      product_<uuid>          — user selected a product from a list menu
      add_<uuid>_<qty>        — user clicked an "add N units" button
      view_menu | view_catalog | order_catalog
                              — show the product catalog list
      start_order | order_quick
                              — start/fast order flow
      track_<order_id>        — track an existing order
      contact_support         — handoff to human agent
    """

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        reply_id = intent_data.get('reply_id', '')
        reply_title = intent_data.get('reply_title', '')

        logger.info('[InteractiveReplyHandler] reply_id=%s', reply_id)

        if reply_id.startswith('product_'):
            return self._handle_product_selection(reply_id, reply_title)

        if reply_id.startswith('add_'):
            return self._handle_add_to_cart(reply_id)

        if reply_id in ('view_menu', 'view_catalog', 'order_catalog'):
            return MenuRequestHandler(
                self.account, self.conversation, self.company_profile
            ).handle(intent_data)

        if reply_id in ('start_order', 'order_quick'):
            return CreateOrderHandler(
                self.account, self.conversation, self.company_profile
            ).handle(intent_data)

        if reply_id.startswith('pix_copy'):
            return CopyPixHandler(
                self.account, self.conversation, self.company_profile
            ).handle(intent_data)

        if reply_id == 'send_comprovante':
            return HandlerResult.text(
                "📤 Para enviar o comprovante, tire uma foto ou screenshot do pagamento "
                "e envie aqui na conversa.\n\n"
                "Vamos verificar e confirmar seu pedido! ✅"
            )

        if reply_id == 'cancel_order':
            return CancelOrderHandler(
                self.account, self.conversation, self.company_profile
            ).handle(intent_data)

        if reply_id.startswith('track_'):
            return TrackOrderHandler(
                self.account, self.conversation, self.company_profile
            ).handle(intent_data)

        if reply_id == 'contact_support':
            return HumanHandoffHandler(
                self.account, self.conversation, self.company_profile
            ).handle(intent_data)

        # Unknown ID — acknowledge and guide
        logger.warning('[InteractiveReplyHandler] Unhandled reply_id=%s', reply_id)
        return HandlerResult.buttons(
            body=f"Você selecionou: {reply_title or reply_id}\n\nComo posso ajudar?",
            buttons=[
                {'id': 'view_menu', 'title': '📋 Ver Cardápio'},
                {'id': 'start_order', 'title': '🛒 Fazer Pedido'},
            ],
        )

    def _handle_product_selection(self, reply_id: str, reply_title: str) -> HandlerResult:
        """User selected a product from the interactive list — ask for quantity."""
        product_uuid = reply_id[len('product_'):]

        try:
            product = StoreProduct.objects.get(id=product_uuid, is_active=True)
        except StoreProduct.DoesNotExist:
            logger.warning('[InteractiveReplyHandler] product_id not found: %s', product_uuid)
            return HandlerResult.text(
                "Produto não encontrado. 😕\n\nQuer ver o cardápio completo? Digite *cardápio*."
            )
        except Exception as exc:
            logger.error('[InteractiveReplyHandler] Error fetching product %s: %s', product_uuid, exc)
            return HandlerResult.text("Erro ao buscar produto. Tente novamente.")

        # Persist selected product in session so the next free-text reply can resolve it
        try:
            from apps.automation.services import get_session_manager
            session_manager = get_session_manager(self.account, self.conversation.phone_number)
            session = session_manager.get_or_create_session()
            session.update_context('pending_product_id', str(product.id))
            session.update_context('pending_product_name', product.name)
            session.update_context('pending_product_price', float(product.price))
        except Exception as exc:
            logger.warning('[InteractiveReplyHandler] session context save failed: %s', exc)

        return HandlerResult.buttons(
            body=(
                f"🍽️ *{product.name}*\n"
                f"💰 R$ {product.price}\n\n"
                f"Quantas unidades você quer?"
            ),
            buttons=[
                {'id': f'add_{product.id}_1', 'title': '1 unidade'},
                {'id': f'add_{product.id}_2', 'title': '2 unidades'},
                {'id': f'add_{product.id}_3', 'title': '3 unidades'},
            ],
            footer="Ou digite a quantidade desejada",
        )

    def _handle_add_to_cart(self, reply_id: str) -> HandlerResult:
        """User clicked an 'add N units' button: add_<product_uuid>_<qty>."""
        # Format: add_<uuid>_<qty>  — qty is the last segment, uuid may contain hyphens
        parts = reply_id.split('_')
        if len(parts) < 3:
            return HandlerResult.text("Erro ao processar pedido. Tente novamente.")

        try:
            quantity = int(parts[-1])
            # UUID sits between the first underscore and the last underscore
            product_id = '_'.join(parts[1:-1])
        except (ValueError, IndexError):
            return HandlerResult.text("Erro ao processar pedido. Tente novamente.")

        try:
            product = StoreProduct.objects.get(id=product_id, is_active=True)
        except StoreProduct.DoesNotExist:
            return HandlerResult.text("Produto não encontrado. 😕")
        except Exception as exc:
            logger.error('[InteractiveReplyHandler] Error fetching product %s: %s', product_id, exc)
            return HandlerResult.text("Erro ao buscar produto. Tente novamente.")

        return self._create_order_for_product(product, quantity)

    def _create_order_for_product(self, product, quantity: int) -> HandlerResult:
        """Create an order for one product + quantity."""
        if not self.store:
            return HandlerResult.text("Loja não disponível no momento. 😔")

        from apps.whatsapp.services import create_order_from_whatsapp

        result = create_order_from_whatsapp(
            store_slug=self.store.slug,
            phone_number=self.conversation.phone_number,
            items=[{'product_id': str(product.id), 'quantity': quantity}],
            customer_name=self.get_customer_name(),
            delivery_address='',
            customer_notes='Pedido via WhatsApp (seleção de cardápio)',
        )

        if result.get('success'):
            order = result['order']
            pix_data = result.get('pix_data', {})

            if pix_data.get('success'):
                pix_code = pix_data.get('pix_code', '')
                return self._send_pix_confirmation(order, pix_code)
            else:
                return HandlerResult.text(
                    f"✅ *Pedido #{order.order_number} criado!*\n\n"
                    f"💰 Total: R$ {order.total}\n"
                    f"⚠️ Erro ao gerar PIX: {pix_data.get('error', 'Tente novamente')}\n\n"
                    f"Você pode pagar na entrega."
                )
        else:
            return HandlerResult.text(
                f"❌ Erro ao criar pedido: {result.get('error', 'Erro desconhecido')}\n\n"
                f"Tente novamente ou fale com um atendente."
            )


# ===== MAPEAMENTO DE HANDLERS =====
HANDLER_MAP = {
    IntentType.GREETING: GreetingHandler,
    IntentType.PRICE_CHECK: PriceCheckHandler,
    IntentType.PRODUCT_MENTION: ProductMentionHandler,
    IntentType.MENU_REQUEST: MenuRequestHandler,
    IntentType.BUSINESS_HOURS: BusinessHoursHandler,
    IntentType.DELIVERY_INFO: DeliveryInfoHandler,
    IntentType.TRACK_ORDER: TrackOrderHandler,
    IntentType.PAYMENT_STATUS: PaymentStatusHandler,
    IntentType.VIEW_QR_CODE: ViewQRCodeHandler,
    IntentType.COPY_PIX: CopyPixHandler,
    IntentType.LOCATION: LocationHandler,
    IntentType.CONTACT: ContactHandler,
    IntentType.CREATE_ORDER: CreateOrderHandler,
    IntentType.ADD_TO_CART: QuickOrderHandler,
    IntentType.CANCEL_ORDER: CancelOrderHandler,
    IntentType.HUMAN_HANDOFF: HumanHandoffHandler,
    IntentType.FAQ: FAQHandler,
    IntentType.UNKNOWN: UnknownHandler,
}


def get_handler(intent_type: IntentType, account, conversation) -> Optional[IntentHandler]:
    """Retorna o handler apropriado para a intenção"""
    handler_class = HANDLER_MAP.get(intent_type)
    if handler_class:
        return handler_class(account, conversation)
    return None
