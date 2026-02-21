"""
Session Management Service for WhatsApp Automation

Gerencia o estado da sessão do cliente durante fluxos de:
- Pedidos
- Pagamentos
- Carrinho
"""
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from decimal import Decimal
import logging

from apps.automation.models import CustomerSession
from apps.whatsapp.models import WhatsAppAccount

logger = logging.getLogger(__name__)


class SessionContext:
    """Contexto da sessão atual do usuário"""
    
    def __init__(self, session: Optional[CustomerSession] = None):
        self.session = session
        self.current_flow = None  # 'order', 'payment', 'cart', etc
        self.flow_step = 0
        self.temp_data = {}  # Dados temporários do fluxo
        
    def is_in_flow(self) -> bool:
        """Verifica se está em algum fluxo ativo"""
        if not self.session:
            return False
        return self.session.status in [
            CustomerSession.SessionStatus.CART_CREATED,
            CustomerSession.SessionStatus.CHECKOUT,
            CustomerSession.SessionStatus.PAYMENT_PENDING,
        ]
    
    def start_order_flow(self):
        """Inicia fluxo de pedido"""
        self.current_flow = 'order'
        self.flow_step = 1
        if self.session:
            self.session.status = CustomerSession.SessionStatus.CART_CREATED
            self.session.save()
    
    def start_payment_flow(self):
        """Inicia fluxo de pagamento"""
        self.current_flow = 'payment'
        self.flow_step = 1
        if self.session:
            self.session.status = CustomerSession.SessionStatus.PAYMENT_PENDING
            self.session.save()
    
    def complete_flow(self):
        """Completa o fluxo atual"""
        if self.session:
            self.session.status = CustomerSession.SessionStatus.COMPLETED
            self.session.save()
        self.current_flow = None
        self.flow_step = 0
        self.temp_data = {}
    
    def reset(self):
        """Reseta o contexto"""
        if self.session:
            self.session.status = CustomerSession.SessionStatus.ACTIVE
            self.session.cart_data = {}
            self.session.cart_total = 0
            self.session.cart_items_count = 0
            self.session.save()
        self.current_flow = None
        self.flow_step = 0
        self.temp_data = {}


class SessionManager:
    """
    Gerenciador de sessões de clientes
    
    Mantém o estado entre mensagens para fluxos complexos
    como pedidos, pagamentos, etc.
    """
    
    def __init__(self, account: WhatsAppAccount, phone_number: str):
        self.account = account
        self.phone_number = phone_number
        self.company = getattr(account, 'company_profile', None)
        self._session: Optional[CustomerSession] = None
        self._context: Optional[SessionContext] = None
    
    def get_or_create_session(self) -> CustomerSession:
        """Obtém ou cria uma sessão para o cliente"""
        if self._session:
            return self._session
        
        if not self.company:
            logger.error("[SessionManager] No company profile found")
            return None
        
        # Busca sessão ativa existente
        session = CustomerSession.objects.filter(
            company=self.company,
            phone_number=self.phone_number,
            status__in=[
                CustomerSession.SessionStatus.ACTIVE,
                CustomerSession.SessionStatus.CART_CREATED,
                CustomerSession.SessionStatus.CHECKOUT,
                CustomerSession.SessionStatus.PAYMENT_PENDING,
            ]
        ).first()
        
        if session:
            # Atualiza última atividade
            session.last_activity_at = datetime.now()
            session.save(update_fields=['last_activity_at'])
            logger.info(f"[SessionManager] Found existing session: {session.id}")
        else:
            # Cria nova sessão
            session = CustomerSession.objects.create(
                company=self.company,
                phone_number=self.phone_number,
                session_id=f"whatsapp_{self.phone_number}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                status=CustomerSession.SessionStatus.ACTIVE
            )
            logger.info(f"[SessionManager] Created new session: {session.id}")
        
        self._session = session
        return session
    
    def get_context(self) -> SessionContext:
        """Obtém o contexto da sessão"""
        if self._context:
            return self._context
        
        session = self.get_or_create_session()
        self._context = SessionContext(session)
        return self._context
    
    def reset_session(self):
        """Reseta a sessão para estado inicial"""
        context = self.get_context()
        context.reset()
        
        # Limpa dados do carrinho
        if self._session:
            self._session.cart_data = {}
            self._session.cart_total = 0
            self._session.cart_items_count = 0
            self._session.pix_code = ''
            self._session.pix_qr_code = ''
            self._session.payment_id = ''
            self._session.save()
        
        logger.info(f"[SessionManager] Session reset for {self.phone_number}")
    
    def update_cart(self, items: list, total: Decimal):
        """Atualiza dados do carrinho"""
        session = self.get_or_create_session()
        if session:
            session.cart_data = {'items': items}
            session.cart_total = total
            session.cart_items_count = len(items)
            session.cart_updated_at = datetime.now()
            session.status = CustomerSession.SessionStatus.CART_CREATED
            session.save()
            logger.info(f"[SessionManager] Cart updated: {len(items)} items, R$ {total}")
    
    def set_payment_pending(self, pix_code: str, pix_qr_code: str = '', payment_id: str = ''):
        """Define status de pagamento pendente"""
        session = self.get_or_create_session()
        if session:
            session.pix_code = pix_code
            session.pix_qr_code = pix_qr_code
            session.payment_id = payment_id
            session.pix_expires_at = datetime.now() + timedelta(hours=24)
            session.status = CustomerSession.SessionStatus.PAYMENT_PENDING
            session.save()
            logger.info(f"[SessionManager] Payment pending set for {self.phone_number}")
    
    def confirm_payment(self, order_id: str = ''):
        """Confirma pagamento e atualiza sessão"""
        session = self.get_or_create_session()
        if session:
            session.status = CustomerSession.SessionStatus.PAYMENT_CONFIRMED
            if order_id:
                session.external_order_id = order_id
            session.save()
            logger.info(f"[SessionManager] Payment confirmed for {self.phone_number}")
    
    def complete_order(self, order_id: str = ''):
        """Completa pedido e finaliza sessão"""
        session = self.get_or_create_session()
        if session:
            session.status = CustomerSession.SessionStatus.COMPLETED
            if order_id:
                session.external_order_id = order_id
            session.save()
            logger.info(f"[SessionManager] Order completed for {self.phone_number}")
    
    def is_order_in_progress(self) -> bool:
        """Verifica se há pedido em andamento"""
        session = self.get_or_create_session()
        if not session:
            return False
        return session.status in [
            CustomerSession.SessionStatus.CART_CREATED,
            CustomerSession.SessionStatus.CHECKOUT,
            CustomerSession.SessionStatus.PAYMENT_PENDING,
        ]
    
    def is_payment_pending(self) -> bool:
        """Verifica se há pagamento pendente"""
        session = self.get_or_create_session()
        if not session:
            return False
        return session.status == CustomerSession.SessionStatus.PAYMENT_PENDING
    
    def get_session_data(self) -> Dict[str, Any]:
        """Retorna dados da sessão atual"""
        session = self.get_or_create_session()
        if not session:
            return {}
        
        return {
            'session_id': str(session.id),
            'status': session.status,
            'cart_data': session.cart_data,
            'cart_total': float(session.cart_total),
            'cart_items_count': session.cart_items_count,
            'pix_code': session.pix_code,
            'pix_expires_at': session.pix_expires_at.isoformat() if session.pix_expires_at else None,
            'order_id': session.external_order_id,
        }


def get_session_manager(account: WhatsAppAccount, phone_number: str) -> SessionManager:
    """Factory function para criar SessionManager"""
    return SessionManager(account, phone_number)
