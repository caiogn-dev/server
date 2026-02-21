"""
Jasper Market Style Templates for WhatsApp

Templates refinados e profissionais inspirados no Jasper Market
para melhor experiência do usuário.
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass


@dataclass
class MessageTemplate:
    """Template de mensagem estruturado"""
    name: str
    body: str
    buttons: Optional[List[Dict[str, str]]] = None
    footer: Optional[str] = None
    header: Optional[str] = None


class JasperTemplates:
    """
    Templates profissionais estilo Jasper Market
    """
    
    @staticmethod
    def greeting(customer_name: str, store_name: str) -> MessageTemplate:
        """Saudação personalizada - Curta e direta"""
        return MessageTemplate(
            name="greeting",
            header=f"👋 Olá, {customer_name}!",
            body=f"Bem-vindo à *{store_name}*! 🍝\n\nO que você quer hoje?",
            buttons=[
                {"id": "view_menu", "title": "📋 Cardápio"},
                {"id": "quick_order", "title": "⚡ Pedido Rápido"},
            ],
            footer="Escreva ou toque nos botões 👆"
        )
    
    @staticmethod
    def menu_categories(store_name: str, categories: List[str]) -> MessageTemplate:
        """Menu com categorias"""
        buttons = [{"id": f"cat_{cat.lower()}", "title": cat} for cat in categories[:3]]
        
        return MessageTemplate(
            name="menu_categories",
            header=f"📋 Cardápio - {store_name}",
            body=(
                "Escolha uma categoria para ver nossos produtos:\n\n"
                "⭐ Os mais pedidos estão em *Destaques*"
            ),
            buttons=buttons if len(categories) <= 3 else [
                {"id": "cat_destaque", "title": "⭐ Destaques"},
                {"id": "cat_rondelli", "title": "🍝 Rondelli"},
                {"id": "cat_bebidas", "title": "🥤 Bebidas"},
            ],
            footer="Responde com o número ou nome do produto"
        )
    
    @staticmethod
    def product_card(product: Dict[str, Any]) -> MessageTemplate:
        """Card de produto formatado"""
        price = product.get('price', 0)
        name = product.get('name', 'Produto')
        description = product.get('description', '')
        
        body = f"*🍽️ {name}*\n"
        body += f"💰 *R$ {price:.2f}*\n\n"
        if description:
            body += f"_{description}_\n\n"
        
        body += "Deseja adicionar ao seu pedido?"
        
        return MessageTemplate(
            name="product_card",
            header="📋 Detalhes do Produto",
            body=body,
            buttons=[
                {"id": f"add_{product.get('id')}_1", "title": "🛒 Adicionar 1"},
                {"id": f"add_{product.get('id')}_2", "title": "🛒 Adicionar 2"},
                {"id": "view_more", "title": "⬅️ Ver Mais"},
            ]
        )
    
    @staticmethod
    def cart_summary(items: List[Dict], total: float, customer_name: str) -> MessageTemplate:
        """Resumo do carrinho"""
        items_text = ""
        for item in items:
            items_text += f"• {item.get('quantity', 1)}x {item.get('name')} = R$ {item.get('total', 0):.2f}\n"
        
        return MessageTemplate(
            name="cart_summary",
            header=f"🛒 Carrinho de {customer_name}",
            body=(
                f"*{items_text}*\n"
                f"━━━━━━━━━━━━━━\n"
                f"💰 *Total: R$ {total:.2f}*\n\n"
                f"O que deseja fazer?"
            ),
            buttons=[
                {"id": "checkout", "title": "💳 Finalizar Pedido"},
                {"id": "add_more", "title": "➕ Adicionar Mais"},
                {"id": "clear_cart", "title": "🗑️ Limpar"},
            ]
        )
    
    @staticmethod
    def order_confirmation(order_number: str, total: float, items: List[Dict], 
                          pix_code: str, ticket_url: str) -> MessageTemplate:
        """Confirmação de pedido com PIX - SUPER CURTO E DIRETO"""
        items_text = ""
        for item in items:
            items_text += f"• {item.get('quantity', 1)}x {item.get('name')}\n"
        
        return MessageTemplate(
            name="order_confirmation",
            header=f"✅ Pedido #{order_number}",
            body=(
                f"{items_text}\n"
                f"💰 Total: R$ {total:.2f}\n\n"
                f"Código PIX:\n"
                f"```{pix_code[:60]}...```"
            ),
            buttons=[
                {"id": "copy_pix", "title": "📋 Copiar PIX"},
            ],
            footer="Cole no app do seu banco"
        )
    
    @staticmethod
    def payment_confirmed(order_number: str, estimated_time: str = "30-45 min") -> MessageTemplate:
        """Pagamento confirmado"""
        return MessageTemplate(
            name="payment_confirmed",
            header="✅ Pagamento Confirmado!",
            body=(
                f"*Pedido #{order_number}*\n\n"
                f"💳 Seu pagamento foi confirmado com sucesso!\n\n"
                f"👨‍🍳 Seu pedido já está sendo preparado.\n"
                f"⏰ *Tempo estimado: {estimated_time}*\n\n"
                f"Avisaremos quando sair para entrega!"
            ),
            buttons=[
                {"id": "track_order", "title": "📦 Acompanhar Pedido"},
                {"id": "support", "title": "💬 Falar com Atendente"},
            ],
            footer="Obrigado pela preferência! 🙏"
        )
    
    @staticmethod
    def order_status_update(order_number: str, status: str, message: str) -> MessageTemplate:
        """Atualização de status do pedido"""
        status_emoji = {
            'confirmed': '✅',
            'preparing': '👨‍🍳',
            'ready': '📦',
            'out_for_delivery': '🛵',
            'delivered': '🎉',
        }.get(status, '📋')
        
        return MessageTemplate(
            name="order_status_update",
            header=f"{status_emoji} Atualização do Pedido #{order_number}",
            body=message,
            footer="Toque abaixo para mais opções"
        )
    
    @staticmethod
    def business_hours(hours: Dict[str, str]) -> MessageTemplate:
        """Horário de funcionamento"""
        hours_text = ""
        for day, time in hours.items():
            hours_text += f"*{day}:* {time}\n"
        
        return MessageTemplate(
            name="business_hours",
            header="🕐 Horário de Funcionamento",
            body=hours_text,
            footer="📍 Delivery funciona até 30 min antes do fechamento"
        )
    
    @staticmethod
    def need_help() -> MessageTemplate:
        """Oferecer ajuda"""
        return MessageTemplate(
            name="need_help",
            header="💬 Precisa de ajuda?",
            body=(
                "Não se preocupe! Estou aqui para ajudar você.\n\n"
                "Posso assistir com:\n"
                "• Fazer seu pedido\n"
                "• Tirar dúvidas sobre produtos\n"
                "• Acompanhar entregas\n"
                "• Falar com um atendente humano"
            ),
            buttons=[
                {"id": "start_order", "title": "🛒 Fazer Pedido"},
                {"id": "view_menu", "title": "📋 Ver Cardápio"},
                {"id": "human_support", "title": "👨‍💼 Falar com Atendente"},
            ]
        )
    
    @staticmethod
    def fallback_message() -> MessageTemplate:
        """Mensagem quando não entende"""
        return MessageTemplate(
            name="fallback",
            header="🤔 Não entendi direito...",
            body=(
                "Desculpe, não consegui entender o que você precisa.\n\n"
                "Posso te ajudar com:\n"
                "• Fazer pedidos\n"
                "• Ver o cardápio\n"
                "• Consultar horários\n"
                "• Acompanhar seu pedido"
            ),
            buttons=[
                {"id": "view_menu", "title": "📋 Ver Cardápio"},
                {"id": "start_order", "title": "🛒 Fazer Pedido"},
                {"id": "help", "title": "❓ Ajuda"},
            ],
            footer="Ou digite 'atendente' para falar com uma pessoa"
        )


class TemplateRenderer:
    """Renderiza templates com variáveis"""
    
    @staticmethod
    def render(template: MessageTemplate, **kwargs) -> Dict[str, Any]:
        """Renderiza template substituindo variáveis"""
        body = template.body
        header = template.header
        footer = template.footer
        
        # Substitui variáveis {nome}
        for key, value in kwargs.items():
            placeholder = f"{{{key}}}"
            body = body.replace(placeholder, str(value))
            if header:
                header = header.replace(placeholder, str(value))
            if footer:
                footer = footer.replace(placeholder, str(value))
        
        return {
            'name': template.name,
            'header': header,
            'body': body,
            'footer': footer,
            'buttons': template.buttons
        }
