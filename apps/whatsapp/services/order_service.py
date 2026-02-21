"""
WhatsApp Order Service - CORRIGIDO

Cria pedidos a partir de conversas do WhatsApp,
gera PIX real e transmite para o dashboard.
"""
import logging
import uuid
from decimal import Decimal
from typing import Optional, Dict, Any, List
from datetime import datetime
from django.utils import timezone
from django.db import transaction
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from apps.stores.models import Store, StoreOrder, StoreOrderItem, StoreProduct
from apps.stores.services.checkout_service import CheckoutService

logger = logging.getLogger(__name__)


class WhatsAppOrderService:
    """
    Serviço para criar pedidos via WhatsApp.
    """
    
    def __init__(self, store: Store, phone_number: str, customer_name: str = ''):
        self.store = store
        self.phone_number = phone_number
        self.customer_name = customer_name or 'Cliente WhatsApp'
        self.channel_layer = get_channel_layer()
        logger.info(f"[WhatsAppOrderService] Inicializado para {phone_number} na loja {store.slug}")
    
    @transaction.atomic
    def create_order_from_cart(
        self,
        items: List[Dict[str, Any]],
        delivery_address: str = '',
        customer_notes: str = '',
        delivery_method: str = 'delivery'
    ) -> Dict[str, Any]:
        """Cria pedido a partir dos itens do carrinho."""
        
        logger.info(f"[create_order_from_cart] Iniciando criação de pedido para {self.phone_number}")
        logger.info(f"[create_order_from_cart] Itens recebidos: {items}")
        
        try:
            # 1. Valida itens e calcula total
            order_items_data = []
            subtotal = Decimal('0')
            
            for idx, item in enumerate(items):
                product_id = item.get('product_id')
                logger.info(f"[create_order_from_cart] Processando item {idx}: product_id={product_id}")
                
                try:
                    product = StoreProduct.objects.get(
                        id=product_id,
                        store=self.store,
                        is_active=True
                    )
                    logger.info(f"[create_order_from_cart] Produto encontrado: {product.name} (R$ {product.price})")
                except StoreProduct.DoesNotExist:
                    logger.warning(f"[create_order_from_cart] Produto {product_id} não encontrado ou inativo")
                    continue
                
                quantity = int(item.get('quantity', 1))
                if quantity < 1:
                    quantity = 1
                
                item_total = product.price * quantity
                subtotal += item_total
                
                order_items_data.append({
                    'product': product,
                    'product_name': product.name,
                    'quantity': quantity,
                    'unit_price': product.price,
                    'total': item_total
                })
                logger.info(f"[create_order_from_cart] Item adicionado: {product.name} x{quantity} = R$ {item_total}")
            
            if not order_items_data:
                logger.error("[create_order_from_cart] Nenhum item válido no carrinho")
                return {
                    'success': False,
                    'error': 'Nenhum item válido no carrinho'
                }
            
            # 2. Calcula totais
            delivery_fee = Decimal('0') if delivery_method == 'pickup' else Decimal('5.00')
            total = subtotal + delivery_fee
            
            logger.info(f"[create_order_from_cart] Subtotal: R$ {subtotal}, Entrega: R$ {delivery_fee}, Total: R$ {total}")
            
            # 3. Cria o pedido
            order_number = self._generate_order_number()
            logger.info(f"[create_order_from_cart] Criando pedido com número: {order_number}")
            
            order = StoreOrder.objects.create(
                store=self.store,
                order_number=order_number,
                access_token=str(uuid.uuid4()),
                customer_name=self.customer_name,
                customer_email=f"whatsapp_{self.phone_number}@pastita.local",
                customer_phone=self.phone_number,
                status=StoreOrder.OrderStatus.PENDING,
                payment_status=StoreOrder.PaymentStatus.PENDING,
                subtotal=subtotal,
                delivery_fee=delivery_fee,
                total=total,
                delivery_method=delivery_method,
                delivery_address={'raw_address': delivery_address} if delivery_address else {},
                customer_notes=customer_notes,
                metadata={
                    'source': 'whatsapp',
                    'created_via': 'whatsapp_automation',
                    'phone_number': self.phone_number,
                    'created_at_whatsapp': timezone.now().isoformat()
                }
            )
            
            logger.info(f"[create_order_from_cart] Pedido criado: {order.id} - {order.order_number}")
            
            # 4. Cria os itens do pedido
            for item_data in order_items_data:
                StoreOrderItem.objects.create(
                    order=order,
                    product=item_data['product'],
                    product_name=item_data['product_name'],
                    quantity=item_data['quantity'],
                    unit_price=item_data['unit_price'],
                    subtotal=item_data['total']
                )
                logger.info(f"[create_order_from_cart] Item criado: {item_data['product_name']}")
            
            logger.info(f"[create_order_from_cart] {len(order_items_data)} itens criados para o pedido {order.order_number}")
            
            # 5. Gera PIX
            logger.info(f"[create_order_from_cart] Gerando PIX para o pedido {order.order_number}")
            pix_data = self._generate_pix(order)
            
            if pix_data.get('success'):
                logger.info(f"[create_order_from_cart] PIX gerado com sucesso: {pix_data.get('payment_id')}")
            else:
                logger.error(f"[create_order_from_cart] Erro ao gerar PIX: {pix_data.get('error')}")
            
            # 6. Transmite para dashboard via WebSocket
            logger.info(f"[create_order_from_cart] Transmitindo para dashboard via WebSocket")
            self._broadcast_order_created(order)
            
            # 7. Atualiza sessão do cliente
            self._update_session(order, pix_data)
            
            logger.info(f"[create_order_from_cart] Pedido completo criado com sucesso: {order.order_number}")
            
            return {
                'success': True,
                'order': order,
                'order_number': order.order_number,
                'pix_data': pix_data,
                'total': float(total)
            }
            
        except Exception as e:
            logger.error(f"[create_order_from_cart] ERRO ao criar pedido: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    def _generate_pix(self, order: StoreOrder) -> Dict[str, Any]:
        """Gera PIX para o pedido usando Mercado Pago"""
        logger.info(f"[_generate_pix] Iniciando geração de PIX para pedido {order.order_number}")
        
        try:
            # Verifica credenciais antes de chamar
            from django.conf import settings
            mp_token = getattr(settings, 'MERCADO_PAGO_ACCESS_TOKEN', None)
            
            if not mp_token:
                logger.error("[_generate_pix] MERCADO_PAGO_ACCESS_TOKEN não configurado!")
                return {
                    'success': False,
                    'error': 'Token do Mercado Pago não configurado'
                }
            
            logger.info(f"[_generate_pix] Token MP encontrado: {mp_token[:20]}...")
            
            result = CheckoutService.create_payment(
                order=order,
                payment_method='pix'
            )
            
            logger.info(f"[_generate_pix] Resultado do CheckoutService: {result}")
            
            if result.get('success'):
                pix_code = result.get('pix_code', '')
                logger.info(f"[_generate_pix] PIX gerado com sucesso. Código: {pix_code[:30]}...")
                
                # Verifica se o código não é vazio ou fake
                if not pix_code or pix_code == '12345678':
                    logger.error(f"[_generate_pix] Código PIX inválido ou fake: {pix_code}")
                    return {
                        'success': False,
                        'error': 'Código PIX inválido retornado'
                    }
                
                return {
                    'success': True,
                    'pix_code': pix_code,
                    'pix_qr_code': result.get('pix_qr_code', ''),
                    'ticket_url': result.get('ticket_url', ''),
                    'payment_id': result.get('payment_id', ''),
                    'expiration': result.get('expiration', '')
                }
            else:
                error_msg = result.get('error', 'Erro desconhecido ao gerar PIX')
                logger.error(f"[_generate_pix] Falha ao gerar PIX: {error_msg}")
                return {
                    'success': False,
                    'error': error_msg
                }
                
        except Exception as e:
            logger.error(f"[_generate_pix] Exceção ao gerar PIX: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    def _update_session(self, order: StoreOrder, pix_data: Dict[str, Any]):
        """Atualiza sessão do cliente com dados do pedido"""
        try:
            from apps.automation.services import get_session_manager
            from apps.automation.models import CompanyProfile
            
            # Busca CompanyProfile pelo nome da loja
            company_profile = CompanyProfile.objects.filter(
                company_name=self.store.name
            ).first()
            
            if not company_profile:
                logger.warning(f"[_update_session] CompanyProfile não encontrado para {self.store.name}")
                return
            
            session_manager = get_session_manager(
                account=company_profile,
                phone_number=self.phone_number
            )
            
            if pix_data.get('success'):
                session_manager.set_payment_pending(
                    pix_code=pix_data.get('pix_code', ''),
                    payment_id=str(order.id)
                )
                logger.info(f"[_update_session] Sessão atualizada com PIX para {self.phone_number}")
            
            session_manager.update_cart(
                items=[{'order_id': str(order.id)}],
                total=order.total
            )
            
        except Exception as e:
            logger.error(f"[_update_session] Erro ao atualizar sessão: {e}")
    
    def _broadcast_order_created(self, order: StoreOrder):
        """Transmite novo pedido para o dashboard via WebSocket"""
        try:
            event_data = {
                'type': 'order_created',
                'order_id': str(order.id),
                'order_number': order.order_number,
                'customer_name': order.customer_name,
                'customer_phone': order.customer_phone,
                'total': float(order.total),
                'status': order.status,
                'payment_status': order.payment_status,
                'delivery_method': order.delivery_method,
                'created_at': order.created_at.isoformat(),
                'source': 'whatsapp'
            }
            
            group_name = f"store_{self.store.slug}_orders"
            logger.info(f"[_broadcast_order_created] Enviando para grupo: {group_name}")
            logger.info(f"[_broadcast_order_created] Dados: {event_data}")
            
            async_to_sync(self.channel_layer.group_send)(
                group_name,
                event_data
            )
            
            logger.info(f"[_broadcast_order_created] Evento enviado com sucesso para {group_name}")
            
        except Exception as e:
            logger.error(f"[_broadcast_order_created] Erro ao transmitir: {e}", exc_info=True)
    
    def _generate_order_number(self) -> str:
        """Gera número único do pedido"""
        prefix = self.store.slug.upper()[:3]
        timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
        random_suffix = str(uuid.uuid4())[:4].upper()
        return f"{prefix}-{timestamp}-{random_suffix}"


def create_order_from_whatsapp(
    store_slug: str,
    phone_number: str,
    items: List[Dict[str, Any]],
    customer_name: str = '',
    delivery_address: str = '',
    customer_notes: str = ''
) -> Dict[str, Any]:
    """
    Função utilitária para criar pedido via WhatsApp.
    """
    logger.info(f"[create_order_from_whatsapp] Chamada para {phone_number} na loja {store_slug}")
    logger.info(f"[create_order_from_whatsapp] Itens: {items}")
    
    try:
        store = Store.objects.get(slug=store_slug, is_active=True)
        logger.info(f"[create_order_from_whatsapp] Loja encontrada: {store.name}")
        
        service = WhatsAppOrderService(
            store=store,
            phone_number=phone_number,
            customer_name=customer_name
        )
        
        result = service.create_order_from_cart(
            items=items,
            delivery_address=delivery_address,
            customer_notes=customer_notes
        )
        
        logger.info(f"[create_order_from_whatsapp] Resultado: {result.get('success')}")
        return result
        
    except Store.DoesNotExist:
        logger.error(f"[create_order_from_whatsapp] Loja {store_slug} não encontrada")
        return {
            'success': False,
            'error': 'Loja não encontrada'
        }
    except Exception as e:
        logger.error(f"[create_order_from_whatsapp] Erro: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e)
        }
