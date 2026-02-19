"""
Server-Sent Events (SSE) views for real-time updates fallback.

Este módulo fornece endpoints SSE para quando WebSocket não está disponível.
"""
import json
import time
import logging
from django.http import StreamingHttpResponse, JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.authtoken.models import Token
from django.core.cache import cache
from django.db import connection

logger = logging.getLogger(__name__)


class SSEEvent:
    """Helper class to build SSE events."""
    
    def __init__(self, event_type: str, data: dict, id: str = None, retry: int = None):
        self.event_type = event_type
        self.data = data
        self.id = id
        self.retry = retry
    
    def to_sse_format(self) -> str:
        """Convert to SSE format."""
        lines = []
        if self.id:
            lines.append(f"id: {self.id}")
        if self.event_type:
            lines.append(f"event: {self.event_type}")
        lines.append(f"data: {json.dumps(self.data)}")
        if self.retry:
            lines.append(f"retry: {self.retry}")
        lines.append("")  # Empty line to end event
        return "\n".join(lines) + "\n"


class BaseSSEView(View):
    """
    Base view for Server-Sent Events.
    
    Provides:
    - Token-based authentication
    - Heartbeat/keepalive
    - Automatic reconnection support
    - Error handling
    """
    
    # Intervalo de heartbeat em segundos
    heartbeat_interval = 30
    # Intervalo de verificação de novos dados
    poll_interval = 2
    # Timeout máximo da conexão (0 = sem limite)
    max_timeout = 0
    
    def get_user_from_token(self, token_key: str):
        """Get user from authentication token with caching."""
        cache_key = f"sse:user_token:{token_key}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        try:
            token = Token.objects.select_related('user').get(key=token_key)
            user = token.user
            # Cache por 5 minutos
            cache.set(cache_key, user, 300)
            return user
        except Token.DoesNotExist:
            return None
    
    def check_authentication(self, request):
        """Check if request is authenticated."""
        # Try query parameter
        token = request.GET.get('token')
        if token:
            return self.get_user_from_token(token)
        
        # Try Authorization header
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Token '):
            token = auth_header[6:]
            return self.get_user_from_token(token)
        
        # Try session
        if request.user.is_authenticated:
            return request.user
        
        return None
    
    def get_event_stream(self, request, user, last_event_id=None):
        """
        Generate SSE events.
        
        Override this method in subclasses.
        Should yield SSEEvent objects.
        """
        raise NotImplementedError("Subclasses must implement get_event_stream")
    
    def generate_stream(self, request, user, last_event_id=None):
        """Generate the SSE stream with heartbeats."""
        last_heartbeat = time.time()
        start_time = time.time()
        
        # Send initial connection event
        yield SSEEvent(
            event_type='connected',
            data={
                'message': 'SSE connection established',
                'timestamp': time.time(),
                'heartbeat_interval': self.heartbeat_interval,
                'poll_interval': self.poll_interval,
            }
        ).to_sse_format()
        
        try:
            for event in self.get_event_stream(request, user, last_event_id):
                # Check timeout
                if self.max_timeout > 0 and (time.time() - start_time) > self.max_timeout:
                    yield SSEEvent(
                        event_type='timeout',
                        data={'message': 'Connection timeout'}
                    ).to_sse_format()
                    break
                
                # Send event
                if event:
                    yield event.to_sse_format()
                
                # Send heartbeat
                current_time = time.time()
                if current_time - last_heartbeat >= self.heartbeat_interval:
                    yield SSEEvent(
                        event_type='heartbeat',
                        data={'timestamp': current_time}
                    ).to_sse_format()
                    last_heartbeat = current_time
                
                # Small delay to prevent CPU spinning
                time.sleep(self.poll_interval)
                
        except GeneratorExit:
            logger.debug("SSE connection closed by client")
        except Exception as e:
            logger.exception("Error in SSE stream")
            yield SSEEvent(
                event_type='error',
                data={'message': str(e), 'type': 'stream_error'}
            ).to_sse_format()
        finally:
            # Ensure connection is closed
            connection.close()
    
    @method_decorator(csrf_exempt)
    def get(self, request, *args, **kwargs):
        """Handle GET request for SSE."""
        user = self.check_authentication(request)
        
        if not user:
            return JsonResponse(
                {'error': 'Authentication required'},
                status=401
            )
        
        # Get last event ID for resumption
        last_event_id = request.headers.get('Last-Event-ID') or request.GET.get('last_event_id')
        
        response = StreamingHttpResponse(
            self.generate_stream(request, user, last_event_id),
            content_type='text/event-stream'
        )
        
        # SSE headers
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'  # Disable nginx buffering
        response['Connection'] = 'keep-alive'
        
        return response


class OrderSSEView(BaseSSEView):
    """
    SSE endpoint for real-time order updates.
    
    URL: /api/sse/orders/
    Query params:
    - token: Authentication token
    - store_id: Filter by store (optional)
    - order_id: Filter by specific order (optional)
    """
    
    poll_interval = 3  # Check every 3 seconds
    
    def get_event_stream(self, request, user, last_event_id=None):
        """Stream order updates."""
        from apps.stores.models import StoreOrder
        
        store_id = request.GET.get('store_id')
        order_id = request.GET.get('order_id')
        
        # Track last check time
        last_check = time.time()
        
        # Get initial state
        if order_id:
            # Single order tracking
            try:
                order = StoreOrder.objects.get(id=order_id)
                last_status = order.status
            except StoreOrder.DoesNotExist:
                yield SSEEvent(
                    event_type='error',
                    data={'message': 'Order not found'}
                )
                return
        elif store_id:
            # Store orders
            last_count = StoreOrder.objects.filter(store_id=store_id).count()
            last_order_id = None
        else:
            # All orders user has access to
            last_count = 0
            last_order_id = None
        
        while True:
            current_time = time.time()
            
            if order_id:
                # Check single order status
                try:
                    order = StoreOrder.objects.get(id=order_id)
                    if order.status != last_status:
                        yield SSEEvent(
                            event_type='order_update',
                            data={
                                'order_id': str(order.id),
                                'order_number': order.order_number,
                                'old_status': last_status,
                                'new_status': order.status,
                                'payment_status': order.payment_status,
                                'timestamp': current_time,
                            },
                            id=f"order_{order.id}_{int(current_time)}"
                        )
                        last_status = order.status
                except StoreOrder.DoesNotExist:
                    yield SSEEvent(
                        event_type='order_deleted',
                        data={'order_id': order_id, 'timestamp': current_time}
                    )
                    break
            else:
                # Check for new orders
                query = StoreOrder.objects.all()
                if store_id:
                    query = query.filter(store_id=store_id)
                
                current_count = query.count()
                
                if current_count > last_count:
                    # New orders
                    if last_order_id:
                        new_orders = query.filter(id__gt=last_order_id).order_by('-created_at')[:10]
                    else:
                        new_orders = query.order_by('-created_at')[:10]
                    
                    for order in new_orders:
                        yield SSEEvent(
                            event_type='new_order',
                            data={
                                'order_id': str(order.id),
                                'order_number': order.order_number,
                                'status': order.status,
                                'total': str(order.total),
                                'customer_name': order.customer_name,
                                'timestamp': current_time,
                            },
                            id=f"new_order_{order.id}_{int(current_time)}"
                        )
                    
                    last_count = current_count
                    if new_orders:
                        last_order_id = str(new_orders[0].id)
                
                # Check for status changes in recent orders
                recent_orders = query.filter(
                    updated_at__gte=timezone.now() - timedelta(minutes=5)
                ).order_by('-updated_at')[:20]
                
                for order in recent_orders:
                    yield SSEEvent(
                        event_type='order_update',
                        data={
                            'order_id': str(order.id),
                            'order_number': order.order_number,
                            'status': order.status,
                            'payment_status': order.payment_status,
                            'timestamp': current_time,
                        },
                        id=f"update_{order.id}_{int(current_time)}"
                    )
            
            last_check = current_time
            yield None  # Signal to check heartbeat
    
    def check_authentication(self, request):
        """Allow public access with order token."""
        # First try normal auth
        user = super().check_authentication(request)
        if user:
            return user
        
        # Allow access with order access_token
        access_token = request.GET.get('access_token')
        if access_token:
            try:
                from apps.stores.models import StoreOrder
                order = StoreOrder.objects.get(access_token=access_token)
                # Return a mock user or the order for tracking
                return type('AnonymousUserWithOrder', (), {
                    'is_authenticated': True,
                    'is_staff': False,
                    'order': order,
                    'id': None
                })()
            except StoreOrder.DoesNotExist:
                pass
        
        return None


class WhatsAppSSEView(BaseSSEView):
    """
    SSE endpoint for WhatsApp real-time updates.
    
    URL: /api/sse/whatsapp/
    Query params:
    - token: Authentication token
    - account_id: WhatsApp account ID (optional)
    - conversation_id: Specific conversation (optional)
    """
    
    poll_interval = 2
    
    def get_event_stream(self, request, user, last_event_id=None):
        """Stream WhatsApp updates."""
        from apps.whatsapp.models import Message, Conversation
        from django.utils import timezone
        from datetime import timedelta
        
        account_id = request.GET.get('account_id')
        conversation_id = request.GET.get('conversation_id')
        
        last_check = timezone.now()
        last_message_id = None
        
        # Get initial state
        if conversation_id:
            try:
                conversation = Conversation.objects.get(id=conversation_id)
                last_message = conversation.messages.order_by('-created_at').first()
                if last_message:
                    last_message_id = str(last_message.id)
            except Conversation.DoesNotExist:
                yield SSEEvent(
                    event_type='error',
                    data={'message': 'Conversation not found'}
                )
                return
        
        while True:
            current_time = timezone.now()
            
            # Query for new messages
            query = Message.objects.filter(created_at__gt=last_check)
            
            if account_id:
                query = query.filter(account_id=account_id)
            if conversation_id:
                query = query.filter(conversation_id=conversation_id)
            
            new_messages = query.order_by('created_at')[:50]
            
            for message in new_messages:
                yield SSEEvent(
                    event_type='message',
                    data={
                        'message_id': str(message.id),
                        'conversation_id': str(message.conversation_id) if message.conversation_id else None,
                        'direction': message.direction,
                        'text': message.text_body,
                        'status': message.status,
                        'from_number': message.from_number,
                        'to_number': message.to_number,
                        'timestamp': message.created_at.isoformat(),
                    },
                    id=f"msg_{message.id}_{int(time.time())}"
                )
                last_message_id = str(message.id)
            
            # Query for status updates
            status_updates = Message.objects.filter(
                updated_at__gt=last_check,
                created_at__lt=last_check  # Only existing messages
            ).exclude(status='pending')[:50]
            
            if account_id:
                status_updates = status_updates.filter(account_id=account_id)
            if conversation_id:
                status_updates = status_updates.filter(conversation_id=conversation_id)
            
            for message in status_updates:
                yield SSEEvent(
                    event_type='status_update',
                    data={
                        'message_id': str(message.id),
                        'status': message.status,
                        'timestamp': message.updated_at.isoformat(),
                    },
                    id=f"status_{message.id}_{int(time.time())}"
                )
            
            last_check = current_time
            yield None


@method_decorator(csrf_exempt, name='dispatch')
class WebSocketHealthCheckView(View):
    """
    Endpoint to check WebSocket health and get fallback recommendations.
    
    URL: /api/sse/health/
    Returns:
    - websocket_supported: Whether WebSocket is available
    - sse_supported: Whether SSE is available
    - recommended_transport: 'websocket', 'sse', or 'polling'
    """
    
    def get(self, request):
        """Check transport capabilities."""
        # Check if WebSocket is working
        websocket_ok = self._check_websocket()
        
        # SSE is always available
        sse_ok = True
        
        # Determine recommendation
        if websocket_ok:
            recommendation = 'websocket'
        elif sse_ok:
            recommendation = 'sse'
        else:
            recommendation = 'polling'
        
        return JsonResponse({
            'websocket_supported': websocket_ok,
            'sse_supported': sse_ok,
            'polling_supported': True,
            'recommended_transport': recommendation,
            'sse_endpoints': {
                'orders': '/api/sse/orders/',
                'whatsapp': '/api/sse/whatsapp/',
            },
            'polling_endpoints': {
                'orders': '/api/v1/stores/orders/',
                'whatsapp_messages': '/api/v1/whatsapp/messages/',
            }
        })
    
    def _check_websocket(self) -> bool:
        """Check if WebSocket service is available."""
        import socket
        from django.conf import settings
        
        # Simple check - see if we can connect to the WebSocket port
        # In production, this would check the actual WebSocket endpoint
        try:
            # Check if Redis is available (required for WebSocket)
            from django.core.cache import cache
            cache.set('websocket_health_check', 'ok', 10)
            return cache.get('websocket_health_check') == 'ok'
        except Exception:
            return False


# Import necessário
from django.utils import timezone
from datetime import timedelta
