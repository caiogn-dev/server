"""
WhatsApp Message Templates

Templates profissionais para interações do bot de WhatsApp.
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


@dataclass
class MessageTemplate:
    """Template de mensagem estruturado"""
    name: str
    body: str
    buttons: Optional[List[Dict[str, str]]] = None
    footer: Optional[str] = None
    header: Optional[str] = None


class JasperTemplates:
    """Templates profissionais para WhatsApp Business"""

    @staticmethod
    def greeting(customer_name: str, store_name: str) -> MessageTemplate:
        """Saudação inicial — curta, calorosa e com opções claras."""
        return MessageTemplate(
            name="greeting",
            body=(
                f"Olá, *{customer_name}*! 👋\n\n"
                f"Seja bem-vindo(a) à *{store_name}*!\n\n"
                f"Como posso te ajudar hoje?"
            ),
            buttons=[
                {"id": "view_menu", "title": "📋 Ver Cardápio"},
                {"id": "start_order", "title": "🛒 Fazer Pedido"},
                {"id": "contact_support", "title": "💬 Falar com Atendente"},
            ],
            footer="Toque em uma opção ou escreva sua dúvida",
        )

    @staticmethod
    def menu_categories(store_name: str, categories: List[str]) -> MessageTemplate:
        """Menu com categorias disponíveis."""
        buttons = [{"id": f"cat_{cat.lower()[:20]}", "title": cat[:20]} for cat in categories[:3]]
        if not buttons:
            buttons = [
                {"id": "view_menu", "title": "📋 Ver Cardápio"},
                {"id": "start_order", "title": "🛒 Fazer Pedido"},
            ]
        return MessageTemplate(
            name="menu_categories",
            body=(
                f"*📋 Cardápio — {store_name}*\n\n"
                "Escolha uma categoria:"
            ),
            buttons=buttons,
            footer="Ou escreva o nome do produto que deseja",
        )

    @staticmethod
    def product_card(product: Dict[str, Any]) -> MessageTemplate:
        """Card de produto formatado."""
        price = product.get('price', 0)
        name = product.get('name', 'Produto')
        description = product.get('description', '')

        body = f"*🍽️ {name}*\n💰 *R$ {price:.2f}*\n"
        if description:
            body += f"\n_{description}_\n"
        body += "\nQuantas unidades deseja?"

        return MessageTemplate(
            name="product_card",
            body=body,
            buttons=[
                {"id": f"add_{product.get('id')}_1", "title": "1 unidade"},
                {"id": f"add_{product.get('id')}_2", "title": "2 unidades"},
                {"id": f"add_{product.get('id')}_3", "title": "3 unidades"},
            ],
            footer="Ou digite a quantidade desejada",
        )

    @staticmethod
    def cart_summary(items: List[Dict], total: float, customer_name: str) -> MessageTemplate:
        """Resumo do carrinho antes de finalizar."""
        items_text = "\n".join(
            f"• {item.get('quantity', 1)}x {item.get('name')} — R$ {item.get('total', 0):.2f}"
            for item in items
        )
        return MessageTemplate(
            name="cart_summary",
            body=(
                f"🛒 *Carrinho de {customer_name}*\n\n"
                f"{items_text}\n\n"
                f"━━━━━━━━━━━━\n"
                f"💰 *Total: R$ {total:.2f}*\n\n"
                f"Deseja finalizar o pedido?"
            ),
            buttons=[
                {"id": "start_order", "title": "✅ Finalizar Pedido"},
                {"id": "view_menu", "title": "➕ Adicionar Mais"},
            ],
        )

    @staticmethod
    def payment_confirmed(customer_name: str, estimated_time: str = "30-45 min") -> MessageTemplate:
        """Pagamento confirmado — usa nome do cliente."""
        return MessageTemplate(
            name="payment_confirmed",
            body=(
                f"✅ *Pagamento confirmado, {customer_name}!*\n\n"
                f"👨‍🍳 Seu pedido já está sendo preparado.\n"
                f"⏰ *Previsão: {estimated_time}*\n\n"
                f"Avisaremos quando sair para entrega! 🛵"
            ),
            buttons=[
                {"id": "contact_support", "title": "💬 Falar com Atendente"},
            ],
            footer="Obrigado pela preferência! 🙏",
        )

    @staticmethod
    def order_status_update(customer_name: str, status: str, message: str) -> MessageTemplate:
        """Atualização de status — usa nome do cliente."""
        status_emoji = {
            'confirmed': '✅',
            'preparing': '👨‍🍳',
            'ready': '📦',
            'out_for_delivery': '🛵',
            'delivered': '🎉',
            'cancelled': '❌',
        }.get(status, '📋')

        return MessageTemplate(
            name="order_status_update",
            body=f"{status_emoji} *{customer_name}*, {message}",
            footer="Toque abaixo se precisar de ajuda",
        )

    @staticmethod
    def business_hours(hours: Dict[str, str]) -> MessageTemplate:
        """Horário de funcionamento."""
        hours_text = "\n".join(f"*{day}:* {time}" for day, time in hours.items())
        return MessageTemplate(
            name="business_hours",
            body=f"🕐 *Horário de Funcionamento*\n\n{hours_text}",
            footer="Delivery disponível até 30 min antes do fechamento",
        )

    @staticmethod
    def out_of_hours(store_name: str, today_hours: str = '') -> MessageTemplate:
        """Mensagem curta para contatos recebidos fora do horário."""
        body = f"*{store_name}* está fora do horário no momento."
        if today_hours:
            body += f"\n\nHoje atendemos de *{today_hours}*."
        body += "\n\nMe envie sua mensagem que seguimos assim que a loja abrir."
        return MessageTemplate(
            name="out_of_hours",
            body=body,
            buttons=[
                {"id": "view_menu", "title": "📋 Cardápio"},
                {"id": "contact_support", "title": "💬 Atendimento"},
            ],
            footer="Você pode deixar sua mensagem agora",
        )

    @staticmethod
    def need_help(customer_name: str = '') -> MessageTemplate:
        """Oferecer ajuda."""
        greeting = f"{customer_name}, " if customer_name else ""
        return MessageTemplate(
            name="need_help",
            body=(
                f"💬 {greeting}estou aqui para ajudar!\n\n"
                f"Posso te ajudar com:\n"
                f"• Fazer um pedido\n"
                f"• Ver o cardápio\n"
                f"• Acompanhar sua entrega\n"
                f"• Falar com um atendente"
            ),
            buttons=[
                {"id": "view_menu", "title": "📋 Ver Cardápio"},
                {"id": "start_order", "title": "🛒 Fazer Pedido"},
                {"id": "contact_support", "title": "👨‍💼 Falar com Atendente"},
            ],
        )

    @staticmethod
    def fallback_message(customer_name: str = '') -> MessageTemplate:
        """Mensagem quando não entende."""
        greeting = f"*{customer_name}*" if customer_name else "você"
        return MessageTemplate(
            name="fallback",
            body=(
                f"Desculpe, {greeting}, não entendi bem. 😅\n\n"
                f"Posso te ajudar com:\n"
                f"• Cardápio e produtos\n"
                f"• Fazer pedidos\n"
                f"• Horário de funcionamento\n"
                f"• Acompanhar pedido"
            ),
            buttons=[
                {"id": "view_menu", "title": "📋 Ver Cardápio"},
                {"id": "start_order", "title": "🛒 Fazer Pedido"},
                {"id": "contact_support", "title": "❓ Ajuda"},
            ],
            footer="Ou escreva 'atendente' para falar com uma pessoa",
        )


class TemplateRenderer:
    """Renderiza templates com variáveis"""

    @staticmethod
    def render(template: MessageTemplate, **kwargs) -> Dict[str, Any]:
        """Renderiza template substituindo variáveis {nome}"""
        body = template.body
        header = template.header
        footer = template.footer

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
            'buttons': template.buttons,
        }
