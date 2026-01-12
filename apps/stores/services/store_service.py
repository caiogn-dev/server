"""
Store service for managing stores and their operations.
"""
import logging
from typing import Dict, Any, Optional, List
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()


class StoreService:
    """Service for store management operations."""
    
    def create_store(
        self,
        owner: User,
        name: str,
        slug: str,
        store_type: str = 'other',
        **kwargs
    ):
        """Create a new store with default settings."""
        from apps.stores.models import Store
        
        store = Store.objects.create(
            owner=owner,
            name=name,
            slug=slug,
            store_type=store_type,
            status=Store.StoreStatus.PENDING,
            **kwargs
        )
        
        # Create default categories based on store type
        self._create_default_categories(store)
        
        logger.info(f"Store created: {store.name} (ID: {store.id})")
        return store
    
    def _create_default_categories(self, store):
        """Create default categories based on store type."""
        from apps.stores.models import StoreCategory
        
        category_templates = {
            'food': ['Pratos Principais', 'Entradas', 'Sobremesas', 'Bebidas', 'Combos'],
            'retail': ['Novidades', 'Promoções', 'Mais Vendidos'],
            'services': ['Serviços', 'Pacotes', 'Consultorias'],
            'digital': ['Cursos', 'E-books', 'Templates', 'Software'],
            'other': ['Produtos', 'Serviços'],
        }
        
        categories = category_templates.get(store.store_type, category_templates['other'])
        
        for i, name in enumerate(categories):
            StoreCategory.objects.create(
                store=store,
                name=name,
                slug=name.lower().replace(' ', '-'),
                sort_order=i
            )
    
    def setup_integration(
        self,
        store,
        integration_type: str,
        name: str,
        credentials: Dict[str, str],
        settings: Dict[str, Any] = None
    ):
        """Set up a new integration for a store."""
        from apps.stores.models import StoreIntegration
        
        integration = StoreIntegration(
            store=store,
            integration_type=integration_type,
            name=name,
            settings=settings or {}
        )
        
        # Set encrypted credentials
        if 'api_key' in credentials:
            integration.api_key = credentials['api_key']
        if 'api_secret' in credentials:
            integration.api_secret = credentials['api_secret']
        if 'access_token' in credentials:
            integration.access_token = credentials['access_token']
        if 'refresh_token' in credentials:
            integration.refresh_token = credentials['refresh_token']
        
        # Set platform-specific IDs
        if 'external_id' in credentials:
            integration.external_id = credentials['external_id']
        if 'phone_number_id' in credentials:
            integration.phone_number_id = credentials['phone_number_id']
        if 'waba_id' in credentials:
            integration.waba_id = credentials['waba_id']
        
        # Set webhook config
        if 'webhook_url' in credentials:
            integration.webhook_url = credentials['webhook_url']
        if 'webhook_secret' in credentials:
            integration.webhook_secret = credentials['webhook_secret']
        if 'webhook_verify_token' in credentials:
            integration.webhook_verify_token = credentials['webhook_verify_token']
        
        integration.status = StoreIntegration.IntegrationStatus.ACTIVE
        integration.save()
        
        logger.info(f"Integration created: {store.name} - {integration_type}")
        return integration
    
    def create_product(
        self,
        store,
        name: str,
        price: Decimal,
        category=None,
        **kwargs
    ):
        """Create a new product for a store."""
        from apps.stores.models import StoreProduct
        from django.utils.text import slugify
        
        slug = kwargs.pop('slug', None) or slugify(name)
        
        # Ensure unique slug
        base_slug = slug
        counter = 1
        while StoreProduct.objects.filter(store=store, slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        product = StoreProduct.objects.create(
            store=store,
            category=category,
            name=name,
            slug=slug,
            price=price,
            **kwargs
        )
        
        logger.info(f"Product created: {store.name} - {product.name}")
        return product
    
    @transaction.atomic
    def create_order(
        self,
        store,
        customer_data: Dict[str, str],
        items: List[Dict[str, Any]],
        delivery_data: Dict[str, Any] = None,
        coupon_code: str = None
    ):
        """Create a new order for a store."""
        from apps.stores.models import StoreOrder, StoreOrderItem, StoreProduct, StoreProductVariant
        from apps.ecommerce.models import Coupon
        
        # Calculate totals
        subtotal = Decimal('0.00')
        order_items = []
        
        for item_data in items:
            product = StoreProduct.objects.get(id=item_data['product_id'], store=store)
            variant = None
            
            if item_data.get('variant_id'):
                variant = StoreProductVariant.objects.get(
                    id=item_data['variant_id'],
                    product=product
                )
            
            unit_price = variant.get_price() if variant else product.price
            quantity = item_data.get('quantity', 1)
            item_subtotal = unit_price * quantity
            subtotal += item_subtotal
            
            order_items.append({
                'product': product,
                'variant': variant,
                'product_name': product.name,
                'variant_name': variant.name if variant else '',
                'sku': variant.sku if variant else product.sku,
                'unit_price': unit_price,
                'quantity': quantity,
                'subtotal': item_subtotal,
                'options': item_data.get('options', {}),
                'notes': item_data.get('notes', '')
            })
        
        # Apply coupon discount
        discount = Decimal('0.00')
        if coupon_code:
            try:
                coupon = Coupon.objects.get(code=coupon_code, is_active=True)
                if coupon.is_valid():
                    discount = coupon.calculate_discount(subtotal)
                    coupon.increment_usage()
            except Coupon.DoesNotExist:
                pass
        
        # Calculate delivery fee
        delivery_fee = Decimal('0.00')
        delivery_method = 'delivery'
        
        if delivery_data:
            delivery_method = delivery_data.get('method', 'delivery')
            if delivery_method == 'delivery':
                delivery_fee = Decimal(str(delivery_data.get('fee', store.default_delivery_fee)))
                
                # Check free delivery threshold
                if store.free_delivery_threshold and subtotal >= store.free_delivery_threshold:
                    delivery_fee = Decimal('0.00')
        
        # Calculate tax
        tax = (subtotal - discount) * (store.tax_rate / 100) if store.tax_rate else Decimal('0.00')
        
        # Calculate total
        total = subtotal - discount + tax + delivery_fee
        
        # Create order
        order = StoreOrder.objects.create(
            store=store,
            customer_name=customer_data.get('name', ''),
            customer_email=customer_data.get('email', ''),
            customer_phone=customer_data.get('phone', ''),
            subtotal=subtotal,
            discount=discount,
            coupon_code=coupon_code or '',
            tax=tax,
            delivery_fee=delivery_fee,
            total=total,
            delivery_method=delivery_method,
            delivery_address=delivery_data.get('address', {}) if delivery_data else {},
            delivery_notes=delivery_data.get('notes', '') if delivery_data else '',
            scheduled_date=delivery_data.get('scheduled_date') if delivery_data else None,
            scheduled_time=delivery_data.get('scheduled_time', '') if delivery_data else '',
            customer_notes=customer_data.get('notes', '')
        )
        
        # Create order items
        for item in order_items:
            StoreOrderItem.objects.create(order=order, **item)
            
            # Decrement stock
            if item['variant']:
                item['variant'].stock_quantity -= item['quantity']
                item['variant'].save(update_fields=['stock_quantity'])
            elif item['product'].track_stock:
                item['product'].decrement_stock(item['quantity'])
        
        # Trigger webhook
        from .webhook_service import webhook_service
        webhook_service.trigger_webhooks(store, 'order.created', {
            'order_id': str(order.id),
            'order_number': order.order_number,
            'customer_name': order.customer_name,
            'customer_phone': order.customer_phone,
            'total': str(order.total),
            'items_count': len(order_items)
        })
        
        logger.info(f"Order created: {store.name} - #{order.order_number}")
        return order
    
    def get_store_stats(self, store) -> Dict[str, Any]:
        """Get comprehensive statistics for a store."""
        from apps.stores.models import StoreOrder, StoreProduct, StoreCustomer
        from django.db.models import Sum, Count, Avg
        from django.db.models.functions import TruncDate
        from datetime import timedelta
        
        now = timezone.now()
        today = now.date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        # Order stats
        orders = StoreOrder.objects.filter(store=store)
        
        total_orders = orders.count()
        orders_today = orders.filter(created_at__date=today).count()
        orders_this_week = orders.filter(created_at__date__gte=week_ago).count()
        orders_this_month = orders.filter(created_at__date__gte=month_ago).count()
        
        # Revenue stats
        paid_orders = orders.filter(payment_status='paid')
        total_revenue = paid_orders.aggregate(total=Sum('total'))['total'] or Decimal('0.00')
        revenue_today = paid_orders.filter(created_at__date=today).aggregate(total=Sum('total'))['total'] or Decimal('0.00')
        revenue_this_week = paid_orders.filter(created_at__date__gte=week_ago).aggregate(total=Sum('total'))['total'] or Decimal('0.00')
        revenue_this_month = paid_orders.filter(created_at__date__gte=month_ago).aggregate(total=Sum('total'))['total'] or Decimal('0.00')
        
        avg_order_value = paid_orders.aggregate(avg=Avg('total'))['avg'] or Decimal('0.00')
        
        # Product stats
        products = StoreProduct.objects.filter(store=store)
        total_products = products.count()
        active_products = products.filter(status='active').count()
        low_stock_products = products.filter(
            track_stock=True,
            stock_quantity__lte=models.F('low_stock_threshold')
        ).count()
        
        # Customer stats
        total_customers = StoreCustomer.objects.filter(store=store).count()
        
        # Order status breakdown
        status_breakdown = orders.values('status').annotate(count=Count('id'))
        
        # Daily orders for chart (last 30 days)
        daily_orders = orders.filter(
            created_at__date__gte=month_ago
        ).annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(
            count=Count('id'),
            revenue=Sum('total')
        ).order_by('date')
        
        return {
            'orders': {
                'total': total_orders,
                'today': orders_today,
                'this_week': orders_this_week,
                'this_month': orders_this_month,
                'status_breakdown': list(status_breakdown)
            },
            'revenue': {
                'total': float(total_revenue),
                'today': float(revenue_today),
                'this_week': float(revenue_this_week),
                'this_month': float(revenue_this_month),
                'average_order': float(avg_order_value)
            },
            'products': {
                'total': total_products,
                'active': active_products,
                'low_stock': low_stock_products
            },
            'customers': {
                'total': total_customers
            },
            'daily_orders': [
                {
                    'date': item['date'].isoformat(),
                    'count': item['count'],
                    'revenue': float(item['revenue'] or 0)
                }
                for item in daily_orders
            ]
        }
    


# Import models at module level to avoid circular imports
from django.db import models

store_service = StoreService()
