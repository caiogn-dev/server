"""
WhatsApp Order Service

Cria pedidos a partir de conversas do WhatsApp,
gera PIX real e transmite para o dashboard.
"""
import logging
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Optional, Dict, Any, List
from django.db.models import F
from django.utils import timezone
from django.db import transaction

from apps.stores.models import Store, StoreCart, StoreCartItem, StoreOrder, StoreOrderItem, StoreProduct
from apps.stores.services.checkout_service import CheckoutService
from apps.stores.services.realtime_service import broadcast_order_event
from apps.core.services.customer_identity import CustomerIdentityService

logger = logging.getLogger(__name__)


class WhatsAppOrderService:
    """
    Serviço para criar pedidos via WhatsApp.
    """
    
    def __init__(self, store: Store, phone_number: str, customer_name: str = ''):
        self.store = store
        self.phone_number = phone_number
        self.customer_name = customer_name or 'Cliente WhatsApp'
        logger.info(f"[WhatsAppOrderService] Inicializado para {phone_number} na loja {store.slug}")
    
    @transaction.atomic
    def create_order_from_cart(
        self,
        items: List[Dict[str, Any]],
        delivery_address: str = '',
        customer_notes: str = '',
        delivery_method: str = 'delivery',
        payment_method: str = 'pix',
        delivery_fee_override: float = None,
        addr_info: dict = None,
    ) -> Dict[str, Any]:
        """Cria pedido a partir dos itens do carrinho.

        payment_method: 'pix' | 'card' | 'cash'
        delivery_fee_override: taxa ja calculada pelo GeoService (sobrescreve cálculo padrão)
        addr_info: dict com lat, lng, distance_km, duration_minutes do geocoding
        """
        logger.info(
            f"[create_order_from_cart] Iniciando para {self.phone_number} "
            f"delivery={delivery_method} payment={payment_method}"
        )

        checkout_result = self._try_create_order_with_checkout_service(
            items=items,
            delivery_address=delivery_address,
            customer_notes=customer_notes,
            delivery_method=delivery_method,
            payment_method=payment_method,
            delivery_fee_override=delivery_fee_override,
            addr_info=addr_info,
        )
        if checkout_result is not None:
            return checkout_result

        try:
            # 1. Valida itens e calcula subtotal
            order_items_data = []
            subtotal = Decimal('0')

            for idx, item in enumerate(items):
                product_id = item.get('product_id')
                try:
                    product = StoreProduct.objects.get(
                        id=product_id,
                        store=self.store,
                        is_active=True
                    )
                except StoreProduct.DoesNotExist:
                    logger.warning(f"[create_order_from_cart] Produto {product_id} não encontrado ou inativo")
                    continue

                quantity = max(int(item.get('quantity', 1)), 1)
                unit_price = product.price
                item_total = unit_price * quantity
                subtotal += item_total
                order_items_data.append({
                    'product': product,
                    'product_name': product.name,
                    'quantity': quantity,
                    'unit_price': unit_price,
                    'total': item_total,
                })
                logger.info(f"[create_order_from_cart] Item: {product.name} x{quantity} = R$ {item_total}")

            if not order_items_data:
                return {'success': False, 'error': 'Nenhum item válido no carrinho'}

            # 2. Taxa de entrega
            if delivery_method == 'pickup':
                delivery_fee = Decimal('0')
            elif delivery_fee_override is not None:
                # Taxa previamente calculada pelo GeoService; usa diretamente.
                delivery_fee = Decimal(str(delivery_fee_override))
                logger.info(f"[create_order_from_cart] Taxa GeoService override: R$ {delivery_fee}")
            else:
                store_fee = Decimal(str(self.store.default_delivery_fee or '0'))
                threshold = self.store.free_delivery_threshold
                if threshold and subtotal >= Decimal(str(threshold)):
                    delivery_fee = Decimal('0')
                else:
                    delivery_fee = store_fee
            total = subtotal + delivery_fee
            logger.info(f"[create_order_from_cart] Subtotal={subtotal} Entrega={delivery_fee} Total={total}")

            # 3. Cria o pedido
            order_number = self._generate_order_number()
            customer_record = CustomerIdentityService.sync_checkout_customer(
                store=self.store,
                customer_name=self.customer_name,
                email=f"whatsapp_{self.phone_number}@whatsapp.bot",
                phone=self.phone_number,
                delivery_method=delivery_method,
                delivery_address=self._build_delivery_address(delivery_address, addr_info),
            )
            customer_user = customer_record.get('user')
            store_customer = customer_record.get('store_customer')
            delivery_address_payload = self._build_delivery_address(delivery_address, addr_info)
            order = StoreOrder.objects.create(
                store=self.store,
                order_number=order_number,
                access_token=str(uuid.uuid4()),
                customer=customer_user,
                customer_name=self.customer_name,
                customer_email=f"whatsapp_{self.phone_number}@whatsapp.bot",
                customer_phone=self.phone_number,
                status=StoreOrder.OrderStatus.PENDING,
                payment_status=StoreOrder.PaymentStatus.PENDING,
                subtotal=subtotal,
                delivery_fee=delivery_fee,
                total=total,
                delivery_method=delivery_method,
                delivery_address=delivery_address_payload,
                customer_notes=customer_notes,
                metadata={
                    'source': 'whatsapp',
                    'created_via': 'whatsapp_automation',
                    'phone_number': self.phone_number,
                    'created_at_whatsapp': timezone.now().isoformat(),
                    'payment_method': payment_method,
                    'customer': {
                        'user_id': str(customer_user.id) if customer_user else '',
                        'store_customer_id': str(store_customer.id) if store_customer else '',
                        'source': 'whatsapp_automation',
                    },
                },
            )
            logger.info(f"[create_order_from_cart] Pedido criado: {order.order_number}")

            # 4. Cria itens do pedido e decrementa estoque atomicamente
            for item_data in order_items_data:
                StoreOrderItem.objects.create(
                    order=order,
                    product=item_data['product'],
                    product_name=item_data['product_name'],
                    quantity=item_data['quantity'],
                    unit_price=item_data['unit_price'],
                    subtotal=item_data['total'],
                )
                product = item_data['product']
                if product.track_stock:
                    StoreProduct.objects.filter(id=product.id).update(
                        stock_quantity=F('stock_quantity') - item_data['quantity'],
                        sold_count=F('sold_count') + item_data['quantity'],
                    )

            # 5. Processa pagamento conforme método escolhido
            if payment_method == 'pix':
                payment_data = self._generate_pix(order)
            elif payment_method == 'card':
                payment_data = self._generate_card_checkout_link(order)
            else:  # cash / pay_on_pickup
                payment_data = self._register_cash_payment(order)

            if payment_data.get('success'):
                logger.info(f"[create_order_from_cart] Pagamento processado: {payment_method}")
            else:
                logger.error(f"[create_order_from_cart] Erro no pagamento: {payment_data.get('error')}")

            # 6. Broadcast dashboard via shared realtime helper (fora do atomic)
            transaction.on_commit(lambda: broadcast_order_event(order, event_type='order.created'))

            # 7. Atualiza sessão
            self._update_session(order, payment_data)

            return {
                'success': True,
                'order': order,
                'order_number': order.order_number,
                'payment_method': payment_method,
                'payment_data': payment_data,
                # Retrocompatibilidade com código que esperava 'pix_data'
                'pix_data': payment_data if payment_method == 'pix' else {'success': False},
                'total': float(total),
            }

        except Exception as e:
            logger.error(f"[create_order_from_cart] ERRO: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def _try_create_order_with_checkout_service(
        self,
        items: List[Dict[str, Any]],
        delivery_address: str = '',
        customer_notes: str = '',
        delivery_method: str = 'delivery',
        payment_method: str = 'pix',
        delivery_fee_override: float = None,
        addr_info: dict = None,
    ) -> Optional[Dict[str, Any]]:
        """Create simple WhatsApp carts through the canonical CheckoutService.

        Returns None when the payload uses legacy-only features that CheckoutService
        cannot represent yet, such as WhatsApp catalog price overrides.
        """
        if not items:
            return {'success': False, 'error': 'Nenhum item válido no carrinho'}

        try:
            product_quantities = {}
            for item in items:
                product_id = item.get('product_id')
                try:
                    product = StoreProduct.objects.get(
                        id=product_id,
                        store=self.store,
                        is_active=True,
                    )
                except StoreProduct.DoesNotExist:
                    logger.warning(f"[create_order_from_cart] Produto {product_id} não encontrado ou inativo")
                    continue

                quantity = max(int(item.get('quantity', 1)), 1)
                product_quantities[product.id] = product_quantities.get(product.id, 0) + quantity

            if not product_quantities:
                return {'success': False, 'error': 'Nenhum item válido no carrinho'}

            cart = StoreCart.objects.create(
                store=self.store,
                session_key=f"whatsapp:{self.phone_number}:{uuid.uuid4()}",
                metadata={
                    'source': 'whatsapp',
                    'phone_number': self.phone_number,
                },
            )
            products = StoreProduct.objects.in_bulk(product_quantities.keys())
            for product_id, quantity in product_quantities.items():
                StoreCartItem.objects.create(
                    cart=cart,
                    product=products[product_id],
                    quantity=quantity,
                )

            address_payload = self._build_delivery_address(delivery_address, addr_info)
            delivery_payload = {
                'method': delivery_method,
                'address': address_payload,
                'notes': customer_notes,
                'metadata': {
                    'source': 'whatsapp',
                    'created_via': 'whatsapp_automation',
                    'phone_number': self.phone_number,
                    'created_at_whatsapp': timezone.now().isoformat(),
                    'payment_method': payment_method,
                },
            }
            if delivery_fee_override is not None:
                delivery_payload['zone_name'] = 'WhatsApp'
            if addr_info:
                if addr_info.get('distance_km') is not None:
                    delivery_payload['distance_km'] = addr_info['distance_km']
                if addr_info.get('duration_minutes') is not None:
                    delivery_payload['duration_minutes'] = addr_info['duration_minutes']
                    delivery_payload['estimated_minutes'] = addr_info['duration_minutes']

            order = CheckoutService.create_order(
                cart=cart,
                customer_data={
                    'name': self.customer_name,
                    'email': f"whatsapp_{self.phone_number}@whatsapp.bot",
                    'phone': self.phone_number,
                },
                delivery_data=delivery_payload,
                notes=customer_notes,
            )

            if payment_method == 'pix':
                payment_data = self._generate_pix(order)
            elif payment_method == 'card':
                payment_data = self._generate_card_checkout_link(order)
            else:
                payment_data = self._register_cash_payment(order)

            if payment_data.get('success'):
                logger.info(f"[create_order_from_cart] Pagamento processado: {payment_method}")
            else:
                logger.error(f"[create_order_from_cart] Erro no pagamento: {payment_data.get('error')}")

            transaction.on_commit(lambda: broadcast_order_event(order, event_type='order.created'))
            self._update_session(order, payment_data)

            return {
                'success': True,
                'order': order,
                'order_number': order.order_number,
                'payment_method': payment_method,
                'payment_data': payment_data,
                'pix_data': payment_data if payment_method == 'pix' else {'success': False},
                'total': float(order.total),
            }
        except Exception as e:
            logger.error(f"[create_order_from_cart] CheckoutService path failed: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def _build_delivery_address(self, raw_address: str, addr_info: dict = None) -> dict:
        """Build delivery_address JSON with structured fields the frontend can render.

        Merges provider address components (from geocode or reverse_geocode) into the
        standard frontend-expected shape: street, number, neighborhood, city, state, zip_code.
        raw_address is always preserved as a display fallback.
        """
        if not raw_address and not addr_info:
            return {}

        data: Dict[str, Any] = {'raw_address': raw_address or ''}

        if addr_info:
            if addr_info.get('lat') is not None:
                data['lat'] = addr_info['lat']
            if addr_info.get('lng') is not None:
                data['lng'] = addr_info['lng']
            if addr_info.get('distance_km') is not None:
                data['distance_km'] = addr_info['distance_km']
            if addr_info.get('duration_minutes') is not None:
                data['duration_minutes'] = addr_info['duration_minutes']

            # Map provider-specific geocode/reverse_geocode components to standard frontend keys.
            components = addr_info.get('address_components') or {}
            if components:
                number = (
                    components.get('houseNumber')
                    or components.get('house_number')
                    or components.get('number', '')
                )
                neighborhood = components.get('district') or components.get('neighborhood', '')
                state = (
                    components.get('stateCode')
                    or components.get('state_code')
                    or components.get('state', '')
                )
                zip_code = components.get('postalCode') or components.get('zip_code', '')

                if components.get('street'):
                    data['street'] = components['street']
                if number:
                    data['number'] = number
                if neighborhood:
                    data['neighborhood'] = neighborhood
                if components.get('city'):
                    data['city'] = components['city']
                if state:
                    data['state'] = state
                if zip_code:
                    data['zip_code'] = zip_code

        return data

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
    
    def _generate_card_checkout_link(self, order: StoreOrder) -> Dict[str, Any]:
        """Gera link de checkout Mercado Pago para cartão de crédito/débito."""
        logger.info(f"[_generate_card_checkout_link] Gerando link MP para {order.order_number}")
        try:
            result = CheckoutService.create_payment(
                order=order,
                payment_method='credit_card',
                payment_data={'allow_redirect': True},
            )
            logger.info(f"[_generate_card_checkout_link] Resultado: {result}")
            if result.get('success'):
                return {
                    'success': True,
                    'payment_method': 'card',
                    'checkout_link': result.get('init_point', ''),
                    'preference_id': result.get('preference_id', ''),
                }
            return {'success': False, 'error': result.get('error', 'Erro ao gerar link de pagamento')}
        except Exception as e:
            logger.error(f"[_generate_card_checkout_link] Exceção: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def _register_cash_payment(self, order: StoreOrder) -> Dict[str, Any]:
        """Registra pedido com pagamento na retirada (cash)."""
        logger.info(f"[_register_cash_payment] Registrando pagamento na retirada para {order.order_number}")
        try:
            result = CheckoutService.create_payment(order=order, payment_method='cash')
            logger.info(f"[_register_cash_payment] Resultado: {result}")
            return {
                'success': True,
                'payment_method': 'cash',
                'message': 'Pagamento na retirada',
            }
        except Exception as e:
            logger.error(f"[_register_cash_payment] Exceção: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def _update_session(self, order: StoreOrder, pix_data: Dict[str, Any]):
        """Atualiza sessão do cliente com dados do pedido"""
        try:
            from apps.automation.services import get_session_manager
            from apps.automation.services.context_service import AutomationContextService

            context = AutomationContextService.resolve(store=self.store, create_profile=True)
            company_profile = context.profile

            if not company_profile:
                logger.warning(f"[_update_session] CompanyProfile não encontrado para loja {self.store.id}")
                return
            
            session_manager = get_session_manager(
                account=company_profile,
                phone_number=self.phone_number
            )
            
            session = session_manager.get_or_create_session()
            if not session:
                logger.warning(f"[_update_session] Sessão não encontrada para {self.phone_number}")
                return

            order_items = [
                {
                    'product_name': item.product_name,
                    'quantity': item.quantity,
                    'unit_price': str(item.unit_price),
                    'subtotal': str(item.subtotal),
                }
                for item in order.items.all()
            ]
            cart_data = dict(session.cart_data or {})
            for key in (
                'pending_items',
                'pending_delivery_method',
                'waiting_for_address',
                'checkout_in_progress',
            ):
                cart_data.pop(key, None)
            cart_data['last_order'] = {
                'id': str(order.id),
                'order_number': order.order_number,
                'items': order_items,
                'subtotal': str(order.subtotal),
                'delivery_fee': str(order.delivery_fee),
                'total': str(order.total),
                'payment_method': order.payment_method,
                'delivery_method': order.delivery_method,
                'delivery_address': order.delivery_address,
                'payment_status': order.payment_status,
                'status': order.status,
            }

            session.order = order
            session.external_order_id = order.order_number
            session.cart_data = cart_data
            session.cart_total = order.total
            session.cart_items_count = len(order_items)
            session.cart_updated_at = timezone.now()

            if pix_data.get('success'):
                session.pix_code = pix_data.get('pix_code', '')
                session.pix_qr_code = pix_data.get('pix_qr_code', '')
                session.payment_id = str(order.id)
                session.pix_expires_at = timezone.now() + timedelta(hours=24)
                session.status = type(session).SessionStatus.PAYMENT_PENDING
                logger.info(f"[_update_session] Sessão atualizada com PIX para {self.phone_number}")
            else:
                session.status = type(session).SessionStatus.ORDER_PLACED

            session.save(update_fields=[
                'order',
                'external_order_id',
                'cart_data',
                'cart_total',
                'cart_items_count',
                'cart_updated_at',
                'pix_code',
                'pix_qr_code',
                'payment_id',
                'pix_expires_at',
                'status',
                'updated_at',
            ])
            
        except Exception as e:
            logger.error(f"[_update_session] Erro ao atualizar sessão: {e}")
    
    def _generate_order_number(self) -> str:
        """Gera número único do pedido"""
        prefix = ''.join(ch for ch in (self.store.slug or '').upper() if ch.isalnum())[:3] or 'ORD'
        timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
        random_suffix = str(uuid.uuid4())[:4].upper()
        return f"{prefix}-{timestamp}-{random_suffix}"


def create_order_from_whatsapp(
    store_slug: str,
    phone_number: str,
    items: List[Dict[str, Any]],
    customer_name: str = '',
    delivery_address: str = '',
    customer_notes: str = '',
    delivery_method: str = 'delivery',
    payment_method: str = 'pix',
    delivery_fee_override: float = None,
    addr_info: dict = None,
) -> Dict[str, Any]:
    """Função utilitária para criar pedido via WhatsApp."""
    logger.info(
        f"[create_order_from_whatsapp] {phone_number} loja={store_slug} "
        f"delivery={delivery_method} payment={payment_method}"
    )

    try:
        store = Store.objects.get(slug=store_slug, is_active=True)

        service = WhatsAppOrderService(
            store=store,
            phone_number=phone_number,
            customer_name=customer_name,
        )

        result = service.create_order_from_cart(
            items=items,
            delivery_address=delivery_address,
            customer_notes=customer_notes,
            delivery_method=delivery_method,
            payment_method=payment_method,
            delivery_fee_override=delivery_fee_override,
            addr_info=addr_info,
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
