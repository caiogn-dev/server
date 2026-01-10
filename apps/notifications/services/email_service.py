# -*- coding: utf-8 -*-
"""
Email service using Resend API.
"""
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import resend, but don't fail if not installed
try:
    import resend
    RESEND_AVAILABLE = True
except ImportError:
    RESEND_AVAILABLE = False
    logger.warning("Resend package not installed. Email notifications will be disabled.")


class EmailService:
    """Service for sending emails via Resend."""
    
    def __init__(self):
        self.api_key = os.getenv('RESEND_API_KEY')
        self.from_email = os.getenv('RESEND_FROM_EMAIL', 'contato@pastita.com.br')
        self.from_name = os.getenv('RESEND_FROM_NAME', 'Pastita')
        
        if RESEND_AVAILABLE and self.api_key:
            resend.api_key = self.api_key
            self.enabled = True
        else:
            self.enabled = False
            if not self.api_key:
                logger.warning("RESEND_API_KEY not configured. Email notifications disabled.")
    
    def send_email(
        self,
        to: str,
        subject: str,
        html: str,
        text: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> dict:
        """Send an email using Resend."""
        if not self.enabled:
            logger.warning(f"Email not sent (disabled): {subject} to {to}")
            return {'success': False, 'error': 'Email service not configured'}
        
        try:
            params = {
                'from': f'{self.from_name} <{self.from_email}>',
                'to': [to],
                'subject': subject,
                'html': html,
            }
            
            if text:
                params['text'] = text
            
            if reply_to:
                params['reply_to'] = reply_to
            
            response = resend.Emails.send(params)
            logger.info(f"Email sent successfully: {subject} to {to}")
            return {'success': True, 'id': response.get('id')}
        
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return {'success': False, 'error': str(e)}
    
    def send_order_confirmation(self, order, customer_email: str) -> dict:
        """Send order confirmation email."""
        subject = f"Pedido #{order.order_number} confirmado - Pastita"
        
        items_html = ""
        for item in order.items.all():
            items_html += f"""
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #eee;">{item.product_name}</td>
                <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: center;">{item.quantity}</td>
                <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: right;">R$ {item.unit_price:.2f}</td>
            </tr>
            """
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #722F37; color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #fff; padding: 30px; border: 1px solid #eee; }}
                .footer {{ background: #f9f9f9; padding: 20px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 10px 10px; }}
                .order-number {{ font-size: 24px; font-weight: bold; color: #C9A050; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th {{ background: #f5f5f5; padding: 10px; text-align: left; }}
                .total {{ font-size: 18px; font-weight: bold; color: #722F37; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0;">🍝 Pastita</h1>
                    <p style="margin: 10px 0 0;">Seu pedido foi confirmado!</p>
                </div>
                <div class="content">
                    <p>Olá, <strong>{order.customer_name}</strong>!</p>
                    <p>Recebemos seu pedido e ele está sendo preparado com carinho.</p>
                    
                    <p class="order-number">Pedido #{order.order_number}</p>
                    
                    <table>
                        <thead>
                            <tr>
                                <th>Produto</th>
                                <th style="text-align: center;">Qtd</th>
                                <th style="text-align: right;">Preço</th>
                            </tr>
                        </thead>
                        <tbody>
                            {items_html}
                        </tbody>
                    </table>
                    
                    <p class="total">Total: R$ {order.total:.2f}</p>
                    
                    <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                    
                    <p><strong>Endereço de entrega:</strong><br>
                    {order.shipping_address.get('address', '')}<br>
                    {order.shipping_address.get('city', '')} - {order.shipping_address.get('state', '')}<br>
                    CEP: {order.shipping_address.get('zip_code', '')}</p>
                    
                    <p>Você receberá atualizações sobre o status do seu pedido.</p>
                </div>
                <div class="footer">
                    <p>Pastita - Massas Artesanais</p>
                    <p>Palmas - TO</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(customer_email, subject, html)
    
    def send_payment_confirmed(self, order, customer_email: str) -> dict:
        """Send payment confirmation email."""
        subject = f"Pagamento confirmado - Pedido #{order.order_number}"
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #16a34a; color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #fff; padding: 30px; border: 1px solid #eee; }}
                .footer {{ background: #f9f9f9; padding: 20px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 10px 10px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0;">✅ Pagamento Confirmado</h1>
                </div>
                <div class="content">
                    <p>Olá, <strong>{order.customer_name}</strong>!</p>
                    <p>O pagamento do seu pedido <strong>#{order.order_number}</strong> foi confirmado com sucesso!</p>
                    <p>Seu pedido está sendo preparado e em breve você receberá mais atualizações.</p>
                    <p><strong>Valor pago:</strong> R$ {order.total:.2f}</p>
                </div>
                <div class="footer">
                    <p>Pastita - Massas Artesanais</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(customer_email, subject, html)
    
    def send_order_shipped(self, order, customer_email: str, tracking_code: str = None) -> dict:
        """Send order shipped/ready notification."""
        subject = f"Pedido #{order.order_number} saiu para entrega!"
        
        tracking_info = ""
        if tracking_code:
            tracking_info = f"<p><strong>Código de rastreio:</strong> {tracking_code}</p>"
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #3b82f6; color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #fff; padding: 30px; border: 1px solid #eee; }}
                .footer {{ background: #f9f9f9; padding: 20px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 10px 10px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0;">🚚 Pedido a Caminho!</h1>
                </div>
                <div class="content">
                    <p>Olá, <strong>{order.customer_name}</strong>!</p>
                    <p>Seu pedido <strong>#{order.order_number}</strong> saiu para entrega!</p>
                    {tracking_info}
                    <p>Em breve você receberá suas deliciosas massas artesanais.</p>
                </div>
                <div class="footer">
                    <p>Pastita - Massas Artesanais</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(customer_email, subject, html)
    
    def send_order_delivered(self, order, customer_email: str) -> dict:
        """Send order delivered confirmation."""
        subject = f"Pedido #{order.order_number} entregue! 🎉"
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #722F37; color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #fff; padding: 30px; border: 1px solid #eee; }}
                .footer {{ background: #f9f9f9; padding: 20px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 10px 10px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0;">🎉 Pedido Entregue!</h1>
                </div>
                <div class="content">
                    <p>Olá, <strong>{order.customer_name}</strong>!</p>
                    <p>Seu pedido <strong>#{order.order_number}</strong> foi entregue com sucesso!</p>
                    <p>Esperamos que você aproveite suas massas artesanais. Bom apetite! 🍝</p>
                    <p>Se tiver qualquer dúvida ou feedback, estamos à disposição.</p>
                    <p style="margin-top: 20px;">
                        <strong>Gostou? Conte para seus amigos!</strong><br>
                        Use o cupom <strong style="color: #722F37;">PASTITA10</strong> na próxima compra e ganhe 10% de desconto.
                    </p>
                </div>
                <div class="footer">
                    <p>Pastita - Massas Artesanais</p>
                    <p>Obrigado por escolher a Pastita!</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(customer_email, subject, html)


# Singleton instance
email_service = EmailService()
