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
import re

from django.utils import timezone

from apps.automation.models import CompanyProfile, CustomerSession
from apps.stores.models import Store
from apps.whatsapp.models import WhatsAppAccount

from .context_service import AutomationContextService

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
        """Inicia fluxo de pedido (update atômico)."""
        self.current_flow = 'order'
        self.flow_step = 1
        if self.session:
            CustomerSession.objects.filter(pk=self.session.pk).update(
                status=CustomerSession.SessionStatus.CART_CREATED,
            )
            self.session.status = CustomerSession.SessionStatus.CART_CREATED

    def start_payment_flow(self):
        """Inicia fluxo de pagamento (update atômico)."""
        self.current_flow = 'payment'
        self.flow_step = 1
        if self.session:
            CustomerSession.objects.filter(pk=self.session.pk).update(
                status=CustomerSession.SessionStatus.PAYMENT_PENDING,
            )
            self.session.status = CustomerSession.SessionStatus.PAYMENT_PENDING

    def complete_flow(self):
        """Completa o fluxo atual (update atômico)."""
        if self.session:
            CustomerSession.objects.filter(pk=self.session.pk).update(
                status=CustomerSession.SessionStatus.COMPLETED,
            )
            self.session.status = CustomerSession.SessionStatus.COMPLETED
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
    
    def __init__(self, account: WhatsAppAccount | CompanyProfile | Store, phone_number: str):
        self.phone_number = phone_number
        digits_only = re.sub(r'\D', '', phone_number or '')
        phone_candidates = [phone_number]
        if digits_only:
            phone_candidates.extend([digits_only, f'+{digits_only}'])
        self.phone_number_variants = [value for value in dict.fromkeys(phone_candidates) if value]
        context_kwargs: Dict[str, Any] = {}
        if isinstance(account, WhatsAppAccount):
            context_kwargs['account'] = account
        elif isinstance(account, CompanyProfile):
            context_kwargs['company'] = account
        elif isinstance(account, Store):
            context_kwargs['store'] = account

        self.context = AutomationContextService.resolve(create_profile=True, **context_kwargs)
        self.account = self.context.account
        self.company = self.context.profile
        self.store = self.context.store
        self._session: Optional[CustomerSession] = None
        self._context: Optional[SessionContext] = None
    
    def get_or_create_session(self) -> Optional[CustomerSession]:
        """Obtém ou cria uma sessão para o cliente"""
        if self._session:
            return self._session
        
        if not self.company:
            logger.error("[SessionManager] No company profile found")
            return None

        active_statuses = [
            CustomerSession.SessionStatus.ACTIVE,
            CustomerSession.SessionStatus.CART_CREATED,
            CustomerSession.SessionStatus.CHECKOUT,
            CustomerSession.SessionStatus.PAYMENT_PENDING,
        ]

        # Busca sessão ativa existente no perfil resolvido.
        session = CustomerSession.objects.filter(
            company=self.company,
            phone_number__in=self.phone_number_variants,
            status__in=active_statuses,
        ).first()

        # Compatibilidade: se houver mais de um CompanyProfile para a mesma Store
        # (ex.: perfil criado pelo signal da conta e perfil raiz da loja), a
        # sessão ainda precisa continuar única no boundary da Store.
        if not session and self.store:
            session = CustomerSession.objects.filter(
                company__store=self.store,
                phone_number__in=self.phone_number_variants,
                status__in=active_statuses,
            ).order_by('-last_activity_at', '-created_at').first()

            if session:
                self.company = session.company
                logger.info(
                    "[SessionManager] Reusing session %s from sibling profile %s for store %s",
                    session.id,
                    session.company_id,
                    self.store.id,
                )

        if session:
            # Atualiza última atividade
            session.last_activity_at = timezone.now()
            session.save(update_fields=['last_activity_at'])
            logger.info(f"[SessionManager] Found existing session: {session.id}")
        else:
            # Cria nova sessão
            session = CustomerSession.objects.create(
                company=self.company,
                phone_number=self.phone_number,
                session_id=f"whatsapp_{self.phone_number}_{timezone.now().strftime('%Y%m%d%H%M%S')}",
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
        """Reseta a sessão para estado inicial de forma atomica."""
        context = self.get_context()
        context.reset()

        if self._session:
            # update() é atômico — evita race condition quando dois workers resetam ao mesmo tempo
            CustomerSession.objects.filter(pk=self._session.pk).update(
                cart_data={},
                cart_total=0,
                cart_items_count=0,
                pix_code='',
                pix_qr_code='',
                payment_id='',
                status=CustomerSession.SessionStatus.ACTIVE,
            )
            # Sincroniza objeto local com os valores gravados
            self._session.refresh_from_db()

        logger.info(f"[SessionManager] Session reset for {self.phone_number}")
    
    def save_pending_order_items(self, items: list) -> None:
        """Salva itens pendentes na sessão enquanto espera escolha de entrega/pagamento."""
        session = self.get_or_create_session()
        if session:
            data = dict(session.cart_data or {})
            data['pending_items'] = items
            session.cart_data = data
            session.save(update_fields=['cart_data'])
            logger.info(f"[SessionManager] Pending items saved: {len(items)} items")

    def get_pending_order_items(self) -> list:
        """Recupera itens pendentes da sessão."""
        session = self.get_or_create_session()
        if session:
            return (session.cart_data or {}).get('pending_items', [])
        return []

    def clear_pending_order_items(self) -> None:
        """Remove itens pendentes da sessão após criar o pedido."""
        session = self.get_or_create_session()
        if session:
            data = dict(session.cart_data or {})
            data.pop('pending_items', None)
            data.pop('pending_delivery_method', None)
            session.cart_data = data
            session.save(update_fields=['cart_data'])

    def save_pending_delivery_method(self, delivery_method: str) -> None:
        """Salva método de entrega enquanto espera escolha de pagamento."""
        session = self.get_or_create_session()
        if session:
            data = dict(session.cart_data or {})
            data['pending_delivery_method'] = delivery_method
            session.cart_data = data
            session.save(update_fields=['cart_data'])
            logger.info(f"[SessionManager] Pending delivery method saved: {delivery_method}")

    def get_pending_delivery_method(self) -> str:
        """Recupera método de entrega pendente."""
        session = self.get_or_create_session()
        if session:
            return (session.cart_data or {}).get('pending_delivery_method', 'delivery')
        return 'delivery'

    def set_waiting_for_address(self, value: bool) -> None:
        """Marca sessão como aguardando endereço de entrega do cliente."""
        session = self.get_or_create_session()
        if session:
            data = dict(session.cart_data or {})
            data['waiting_for_address'] = value
            session.cart_data = data
            session.save(update_fields=['cart_data'])

    def is_waiting_for_address(self) -> bool:
        """Verifica se a sessão está aguardando endereço do cliente."""
        session = self.get_or_create_session()
        if session:
            return bool((session.cart_data or {}).get('waiting_for_address', False))
        return False

    def save_delivery_address_info(
        self,
        address: str,
        fee: float,
        distance_km: float = None,
        duration_minutes: float = None,
        lat: float = None,
        lng: float = None,
        address_components: dict = None,
    ) -> None:
        """Salva endereço geocodificado e taxa calculada pelo HERE."""
        session = self.get_or_create_session()
        if session:
            data = dict(session.cart_data or {})
            data['delivery_address'] = address
            data['delivery_fee_calculated'] = fee
            data['delivery_distance_km'] = distance_km
            data['delivery_duration_minutes'] = duration_minutes
            data['delivery_lat'] = lat
            data['delivery_lng'] = lng
            data['waiting_for_address'] = False
            if address_components:
                data['delivery_address_components'] = address_components
            session.cart_data = data
            session.save(update_fields=['cart_data'])
            logger.info(f"[SessionManager] Delivery address saved: {address[:40]} fee=R${fee} lat={lat} lng={lng}")

    def get_delivery_address_info(self) -> dict:
        """Recupera endereço e taxa de entrega calculados."""
        session = self.get_or_create_session()
        if session:
            d = session.cart_data or {}
            return {
                'address': d.get('delivery_address', ''),
                'fee': d.get('delivery_fee_calculated'),
                'distance_km': d.get('delivery_distance_km'),
                'duration_minutes': d.get('delivery_duration_minutes'),
                'lat': d.get('delivery_lat'),
                'lng': d.get('delivery_lng'),
                'address_components': d.get('delivery_address_components', {}),
            }
        return {
            'address': '', 'fee': None, 'distance_km': None,
            'duration_minutes': None, 'lat': None, 'lng': None, 'address_components': {},
        }

    def update_cart(self, items: list, total: Decimal):
        """Atualiza dados do carrinho"""
        session = self.get_or_create_session()
        if session:
            session.cart_data = {'items': items}
            session.cart_total = total
            session.cart_items_count = len(items)
            session.cart_updated_at = timezone.now()
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
            session.pix_expires_at = timezone.now() + timedelta(hours=24)
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


def get_session_manager(account: WhatsAppAccount | CompanyProfile | Store, phone_number: str) -> SessionManager:
    """Factory function para criar SessionManager"""
    return SessionManager(account, phone_number)
