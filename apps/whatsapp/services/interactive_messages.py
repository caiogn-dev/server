"""
WhatsApp Interactive Messages - Mensagens Interativas Refinadas

Baseado no Jasper WhatsApp - Implementação de botões, listas e templates
para melhor experiência do usuário.
"""
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


class WhatsAppInteractiveMessage:
    """
    Builder para mensagens interativas do WhatsApp.
    Suporta: botões, listas, e mensagens com código PIX.
    """
    
    @staticmethod
    def create_button_message(
        to: str,
        body: str,
        buttons: List[Dict[str, str]],
        header: Optional[str] = None,
        footer: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cria mensagem com botões.
        
        Args:
            to: Número do destinatário
            body: Texto principal
            buttons: Lista de botões [{'id': 'btn_1', 'title': 'Texto'}]
            header: Texto do cabeçalho (opcional)
            footer: Texto do rodapé (opcional)
        """
        message = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": btn.get('id', f'btn_{i}'),
                                "title": btn.get('title', 'Botão')[:20]  # Limite 20 chars
                            }
                        }
                        for i, btn in enumerate(buttons[:3])  # Máximo 3 botões
                    ]
                }
            }
        }
        
        # Adiciona header se fornecido
        if header:
            message["interactive"]["header"] = {
                "type": "text",
                "text": header[:60]  # Limite 60 chars
            }
        
        # Adiciona footer se fornecido
        if footer:
            message["interactive"]["footer"] = {
                "text": footer[:60]  # Limite 60 chars
            }
        
        return message
    
    @staticmethod
    def create_list_message(
        to: str,
        body: str,
        button: str,
        sections: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Cria mensagem com lista.
        
        Args:
            to: Número do destinatário
            body: Texto principal
            button: Texto do botão que abre a lista
            sections: Seções com rows [{'title': 'Título', 'rows': [...]}]
        """
        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": body},
                "action": {
                    "button": button[:20],  # Limite 20 chars
                    "sections": [
                        {
                            "title": section.get('title', 'Opções')[:24],  # Limite 24 chars
                            "rows": [
                                {
                                    "id": row.get('id', f'row_{i}_{j}'),
                                    "title": row.get('title', 'Opção')[:24],  # Limite 24 chars
                                    "description": row.get('description', '')[:72]  # Limite 72 chars
                                }
                                for j, row in enumerate(section.get('rows', []))
                            ]
                        }
                        for i, section in enumerate(sections[:10])  # Máximo 10 seções
                    ]
                }
            }
        }
    
    @staticmethod
    def create_pix_message(
        to: str,
        order_number: str,
        total: float,
        pix_code: str,
        items: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Cria mensagem de PIX com botão de copiar.
        
        Args:
            to: Número do destinatário
            order_number: Número do pedido
            total: Valor total
            pix_code: Código PIX copia-e-cola
            items: Lista de itens do pedido (opcional)
        """
        # Formata itens se fornecidos
        items_text = ""
        if items:
            for item in items[:5]:  # Limita a 5 itens
                items_text += f"• {item.get('quantity', 1)}x {item.get('name')}\n"
            if len(items) > 5:
                items_text += f"... e mais {len(items) - 5} itens\n"
        
        body = (
            f"{items_text}\n" if items_text else ""
        ) + f"💰 *Total: R$ {total:.2f}*\n\n"
        
        # Trunca código PIX se muito longo
        pix_display = pix_code[:80] + "..." if len(pix_code) > 80 else pix_code
        
        return WhatsAppInteractiveMessage.create_button_message(
            to=to,
            header=f"✅ Pedido #{order_number}",
            body=body + f"Código PIX:\n```{pix_display}```",
            footer="Toque em 'Copiar PIX' para copiar o código",
            buttons=[
                {"id": f"copy_pix_{order_number}", "title": "📋 Copiar PIX"},
                {"id": "already_paid", "title": "✅ Já paguei"},
            ]
        )
    
    @staticmethod
    def create_cart_message(
        to: str,
        items: List[Dict],
        total: float,
        customer_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cria mensagem do carrinho com opções.
        """
        items_text = ""
        for item in items:
            qty = item.get('quantity', 1)
            name = item.get('name', 'Item')
            price = item.get('price', 0)
            items_text += f"• {qty}x {name} = R$ {price * qty:.2f}\n"
        
        body = (
            f"{items_text}\n"
            f"━━━━━━━━━━━━━━\n"
            f"💰 *Total: R$ {total:.2f}*\n\n"
            f"O que deseja fazer?"
        )
        
        return WhatsAppInteractiveMessage.create_button_message(
            to=to,
            header=f"🛒 Carrinho" + (f" de {customer_name}" if customer_name else ""),
            body=body,
            footer="Escolha uma opção abaixo",
            buttons=[
                {"id": "checkout", "title": "💳 Finalizar"},
                {"id": "add_more", "title": "➕ Adicionar"},
                {"id": "clear_cart", "title": "🗑️ Limpar"},
            ]
        )
    
    @staticmethod
    def create_greeting_message(
        to: str,
        customer_name: str,
        store_name: str
    ) -> Dict[str, Any]:
        """
        Cria mensagem de saudação.
        """
        return WhatsAppInteractiveMessage.create_button_message(
            to=to,
            header=f"👋 Olá, {customer_name}!",
            body=f"Bem-vindo à *{store_name}*! 🍝\n\nO que você quer hoje?",
            footer="Escreva ou toque nos botões 👆",
            buttons=[
                {"id": "view_menu", "title": "📋 Cardápio"},
                {"id": "quick_order", "title": "⚡ Pedido Rápido"},
            ]
        )
    
    @staticmethod
    def create_product_message(
        to: str,
        product: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Cria mensagem de produto.
        """
        name = product.get('name', 'Produto')
        price = product.get('price', 0)
        description = product.get('description', '')
        product_id = product.get('id', '0')
        
        body = f"💰 *R$ {price:.2f}*\n\n"
        if description:
            body += f"_{description}_\n\n"
        body += "Deseja adicionar?"
        
        return WhatsAppInteractiveMessage.create_button_message(
            to=to,
            header=f"🍽️ {name}",
            body=body,
            footer="Escolha a quantidade",
            buttons=[
                {"id": f"add_{product_id}_1", "title": "🛒 1 unidade"},
                {"id": f"add_{product_id}_2", "title": "🛒 2 unidades"},
                {"id": "view_more", "title": "⬅️ Voltar"},
            ]
        )

    @staticmethod
    def create_product_with_suggestions(
        to: str,
        product: Dict[str, Any],
        suggestions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Cria mensagem de produto com sugestões de complementos.
        """
        name = product.get('name', 'Produto')
        price = product.get('price', 0)
        description = product.get('description', '')
        product_id = product.get('id', '0')
        
        body = f"💰 *R$ {price:.2f}*\n\n"
        if description:
            body += f"_{description}_\n\n"
        
        if suggestions:
            body += "*Sugestões de complementos:*\n"
            for i, sug in enumerate(suggestions[:2], 1):
                body += f"{i}. {sug.get('name')} - R$ {sug.get('price', 0):.2f}\n"
            body += "\n"
        
        body += "Deseja adicionar?"
        
        buttons = [
            {"id": f"add_{product_id}_1", "title": "🛒 Adicionar"},
        ]
        
        if suggestions:
            buttons.append({"id": f"suggest_{product_id}", "title": "💡 Ver sugestões"})
        
        buttons.append({"id": "view_more", "title": "⬅️ Voltar"})
        
        return WhatsAppInteractiveMessage.create_button_message(
            to=to,
            header=f"🍽️ {name}",
            body=body,
            footer="Adicione ao carrinho ou veja sugestões",
            buttons=buttons
        )

    @staticmethod
    def create_combo_message(
        to: str,
        combo: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Cria mensagem de combo/promoção.
        """
        name = combo.get('name', 'Combo')
        price = combo.get('price', 0)
        original_price = combo.get('original_price', price)
        items = combo.get('items', [])
        combo_id = combo.get('id', '0')
        
        discount = ((original_price - price) / original_price * 100) if original_price > price else 0
        
        body = f"🔥 *PROMOÇÃO ESPECIAL*\n\n"
        body += f"*{name}*\n\n"
        
        if items:
            body += "*Inclui:*\n"
            for item in items:
                body += f"✓ {item}\n"
            body += "\n"
        
        body += f"💰 *R$ {price:.2f}*"
        if discount > 0:
            body += f" _(Economize R$ {original_price - price:.2f})_\n"
            body += f"📉 *{discount:.0f}% OFF*"
        
        return WhatsAppInteractiveMessage.create_button_message(
            to=to,
            header=f"🎉 Combo Especial",
            body=body,
            footer="Aproveite enquanto dura!",
            buttons=[
                {"id": f"add_combo_{combo_id}", "title": "🛒 Quero esse!"},
                {"id": "view_combos", "title": "📋 Ver mais combos"},
            ]
        )

    @staticmethod
    def create_checkout_summary(
        to: str,
        order: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Cria resumo do pedido para checkout.
        """
        items = order.get('items', [])
        subtotal = order.get('subtotal', 0)
        delivery_fee = order.get('delivery_fee', 0)
        total = order.get('total', 0)
        delivery_method = order.get('delivery_method', 'delivery')
        
        items_text = ""
        for item in items[:4]:
            items_text += f"• {item.get('quantity', 1)}x {item.get('name')}\n"
        if len(items) > 4:
            items_text += f"... e mais {len(items) - 4}\n"
        
        body = f"{items_text}\n"
        body += f"Subtotal: R$ {subtotal:.2f}\n"
        
        if delivery_method == 'delivery' and delivery_fee > 0:
            body += f"Entrega: R$ {delivery_fee:.2f}\n"
        elif delivery_method == 'pickup':
            body += f"Retirada: Grátis\n"
        
        body += f"━━━━━━━━━━━━━━\n"
        body += f"💰 *Total: R$ {total:.2f}*"
        
        return WhatsAppInteractiveMessage.create_button_message(
            to=to,
            header=f"🛒 Resumo do Pedido",
            body=body,
            footer="Confirme para prosseguir",
            buttons=[
                {"id": "confirm_order", "title": "✅ Confirmar"},
                {"id": "add_more", "title": "➕ Adicionar mais"},
                {"id": "cancel", "title": "❌ Cancelar"},
            ]
        )

    @staticmethod
    def create_delivery_options(
        to: str,
        delivery_fee: float,
        estimated_time: str = "30-45 min"
    ) -> Dict[str, Any]:
        """
        Cria mensagem com opções de entrega/retirada.
        """
        body = f"Como deseja receber seu pedido?\n\n"
        body += f"🛵 *Entrega*\n"
        body += f"   Taxa: R$ {delivery_fee:.2f}\n"
        body += f"   Tempo: {estimated_time}\n\n"
        body += f"🏪 *Retirada*\n"
        body += f"   Taxa: Grátis\n"
        body += f"   Tempo: 20-30 min"
        
        return WhatsAppInteractiveMessage.create_button_message(
            to=to,
            header=f"📍 Opções de Recebimento",
            body=body,
            footer="Escolha a melhor opção para você",
            buttons=[
                {"id": "choose_delivery", "title": "🛵 Entrega"},
                {"id": "choose_pickup", "title": "🏪 Retirada"},
            ]
        )

    @staticmethod
    def create_suggestion_upsell(
        to: str,
        current_item: str,
        suggestion: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Cria mensagem de sugestão/upsell.
        Quem comprou X também comprou Y.
        """
        sug_name = suggestion.get('name', 'Produto')
        sug_price = suggestion.get('price', 0)
        sug_id = suggestion.get('id', '0')
        
        body = f"Você está pedindo *{current_item}*.\n\n"
        body += f"💡 *Sugestão:*\n"
        body += f"{sug_name} - R$ {sug_price:.2f}\n\n"
        body += f"_Quem pede {current_item} também gosta de adicionar {sug_name}!_"
        
        return WhatsAppInteractiveMessage.create_button_message(
            to=to,
            header=f"✨ Sugestão Especial",
            body=body,
            footer="Aproveite a combinação perfeita",
            buttons=[
                {"id": f"add_suggestion_{sug_id}", "title": f"🛒 Adicionar {sug_name}"},
                {"id": "no_thanks", "title": "❌ Não, obrigado"},
            ]
        )

    @staticmethod
    def create_category_list(
        to: str,
        categories: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Cria lista de categorias.
        """
        sections = []
        rows = []
        
        for cat in categories[:10]:
            rows.append({
                "id": f"cat_{cat.get('id')}",
                "title": cat.get('name', 'Categoria')[:24],
                "description": f"Ver {cat.get('product_count', 0)} produtos"[:72]
            })
        
        if rows:
            sections.append({
                "title": "Categorias",
                "rows": rows
            })
        
        return WhatsAppInteractiveMessage.create_list_message(
            to=to,
            body="Escolha uma categoria para ver os produtos disponíveis:",
            button="📋 Ver Categorias",
            sections=sections
        )

    @staticmethod
    def create_multi_product_message(
        to: str,
        header: str,
        body: str,
        catalog_id: str,
        sections: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Cria mensagem Multi-Product (MPM) usando catálogo do Meta.
        
        ATENÇÃO: Requer catálogo configurado no Commerce Manager.
        
        Args:
            to: Número do destinatário
            header: Título do cabeçalho
            body: Texto do corpo
            catalog_id: ID do catálogo no Meta
            sections: Lista de seções com produtos
                     [{"title": "Seção 1", "product_items": [{"product_retailer_id": "SKU1"}]}]
        """
        message = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "product_list",
                "header": {
                    "type": "text",
                    "text": header[:60]
                },
                "body": {
                    "text": body[:4096]
                },
                "action": {
                    "catalog_id": catalog_id,
                    "sections": sections[:10]  # Máximo 10 seções
                }
            }
        }
        
        logger.info(f"[MultiProduct] Created MPM with {len(sections)} sections")
        return message

    @staticmethod
    def create_single_product_message(
        to: str,
        catalog_id: str,
        product_retailer_id: str,
        body: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cria mensagem Single Product (SPM).
        Mostra um único produto do catálogo.
        
        Args:
            to: Número do destinatário
            catalog_id: ID do catálogo no Meta
            product_retailer_id: SKU do produto
            body: Texto opcional
        """
        message = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "product",
                "action": {
                    "catalog_id": catalog_id,
                    "product_retailer_id": product_retailer_id
                }
            }
        }
        
        if body:
            message["interactive"]["body"] = {"text": body[:4096]}
        
        return message

    @staticmethod
    def create_menu_catalog_simulation(
        to: str,
        products: List[Dict[str, Any]],
        category_name: str = "Cardápio"
    ) -> Dict[str, Any]:
        """
        SIMULAÇÃO de Multi-Product Message usando seu próprio sistema.
        Não requer catálogo do Meta!
        
        Cria uma lista interativa com até 10 produtos do seu cardápio.
        Cada produto vira um item clicável na lista.
        
        Args:
            to: Número do destinatário
            products: Lista de produtos do seu sistema
                     [{"id": "1", "name": "Pizza", "price": 45.90, "description": "..."}]
            category_name: Nome da categoria/seção
        """
        sections = []
        rows = []
        
        # Limita a 10 produtos (máximo da API de listas)
        for product in products[:10]:
            prod_id = str(product.get('id', '0'))
            name = product.get('name', 'Produto')[:24]  # Limite da API
            price = product.get('price', 0)
            description = product.get('description', '')[:72]  # Limite da API
            
            # Formata descrição com preço
            desc = f"R$ {price:.2f}"
            if description:
                desc = f"{description[:50]} - R$ {price:.2f}"
            
            rows.append({
                "id": f"view_product_{prod_id}",
                "title": name,
                "description": desc
            })
        
        if rows:
            sections.append({
                "title": category_name[:24],
                "rows": rows
            })
        
        message = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text",
                    "text": f"📋 {category_name}"[:60]
                },
                "body": {
                    "text": f"Escolha um item para ver detalhes e adicionar ao carrinho:\n\n📦 {len(products)} produtos disponíveis"[:4096]
                },
                "footer": {
                    "text": "Toque em um item para ver mais detalhes"
                },
                "action": {
                    "button": "🛒 Ver Produtos",
                    "sections": sections
                }
            }
        }
        
        logger.info(f"[MenuSimulation] Created catalog simulation with {len(rows)} products")
        return message

    @staticmethod
    def create_product_detail_with_add(
        to: str,
        product: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Mostra detalhes do produto com botão para adicionar ao carrinho.
        Usado após o cliente clicar em um item do catálogo simulado.
        """
        name = product.get('name', 'Produto')
        price = product.get('price', 0)
        description = product.get('description', '')
        product_id = str(product.get('id', '0'))
        
        body = f"💰 *R$ {price:.2f}*\n\n"
        
        if description:
            body += f"_{description}_\n\n"
        
        body += "Quantas unidades deseja?"
        
        return WhatsAppInteractiveMessage.create_button_message(
            to=to,
            header=f"🍽️ {name}",
            body=body,
            footer="Escolha a quantidade",
            buttons=[
                {"id": f"add_{product_id}_1", "title": "1x 🛒"},
                {"id": f"add_{product_id}_2", "title": "2x 🛒"},
                {"id": f"add_{product_id}_3", "title": "3x 🛒"},
            ]
        )


class QuickReplyBuilder:
    """Builder para quick replies (respostas rápidas)"""
    
    @staticmethod
    def yes_no(question: str) -> List[Dict[str, str]]:
        """Retorna botões Sim/Não"""
        return [
            {"id": "yes", "title": "✅ Sim"},
            {"id": "no", "title": "❌ Não"},
        ]
    
    @staticmethod
    def confirm_cancel() -> List[Dict[str, str]]:
        """Retorna botões Confirmar/Cancelar"""
        return [
            {"id": "confirm", "title": "✅ Confirmar"},
            {"id": "cancel", "title": "❌ Cancelar"},
        ]
    
    @staticmethod
    def delivery_pickup() -> List[Dict[str, str]]:
        """Retorna botões Entrega/Retirada"""
        return [
            {"id": "delivery", "title": "🛵 Entrega"},
            {"id": "pickup", "title": "🏪 Retirada"},
        ]
    
    @staticmethod
    def payment_methods() -> List[Dict[str, str]]:
        """Retorna botões de métodos de pagamento"""
        return [
            {"id": "pay_pix", "title": "💠 PIX"},
            {"id": "pay_card", "title": "💳 Cartão"},
            {"id": "pay_cash", "title": "💵 Dinheiro"},
        ]
