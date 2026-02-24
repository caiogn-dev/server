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
