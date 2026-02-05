"""
Store service for managing stores and their operations.
"""
import logging
from typing import Dict, Any, Optional, List
from decimal import Decimal, InvalidOperation
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
        from apps.stores.models import StoreOrder, StoreOrderItem, StoreProduct, StoreProductVariant, StoreCoupon
        
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
        
        # Apply coupon discount using unified StoreCoupon model
        discount = Decimal('0.00')
        if coupon_code:
            try:
                coupon = StoreCoupon.objects.get(store=store, code__iexact=coupon_code, is_active=True)
                is_valid, _ = coupon.is_valid(subtotal=subtotal)
                if is_valid:
                    discount = coupon.calculate_discount(subtotal)
                    coupon.increment_usage()
            except StoreCoupon.DoesNotExist:
                pass
        
        # Calculate delivery fee
        delivery_fee = Decimal('0.00')
        delivery_method = 'delivery'
        
        if delivery_data:
            delivery_method = delivery_data.get('method', 'delivery')
            if delivery_method == 'delivery':
                fee_value = delivery_data.get('fee')
                if fee_value is not None and fee_value != '':
                    try:
                        delivery_fee = Decimal(str(fee_value))
                    except (ValueError, InvalidOperation):
                        delivery_fee = store.default_delivery_fee or Decimal('0.00')
                else:
                    delivery_fee = store.default_delivery_fee or Decimal('0.00')
                
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
    
    @transaction.atomic
    def sync_pastita_to_store(self, store) -> Dict[str, Any]:
        """
        Sync Pastita products to a store.
        Copies products from the Pastita template store to the target store.
        """
        from apps.stores.models import Store, StoreProduct, StoreCategory
        
        # Find Pastita source store (template store)
        pastita_store = Store.objects.filter(
            slug__icontains='pastita'
        ).exclude(id=store.id).first()
        
        if not pastita_store:
            # Create default Pastita products if no source store
            return self._create_default_pastita_products(store)
        
        synced_products = 0
        synced_categories = 0
        
        # Sync categories first
        source_categories = StoreCategory.objects.filter(store=pastita_store)
        category_map = {}  # Map source category ID to new category
        
        for src_cat in source_categories:
            new_cat, created = StoreCategory.objects.get_or_create(
                store=store,
                slug=src_cat.slug,
                defaults={
                    'name': src_cat.name,
                    'description': src_cat.description,
                    'sort_order': src_cat.sort_order,
                    'is_active': src_cat.is_active,
                }
            )
            category_map[src_cat.id] = new_cat
            if created:
                synced_categories += 1
        
        # Sync products
        source_products = StoreProduct.objects.filter(store=pastita_store)
        
        for src_product in source_products:
            # Check if product already exists
            existing = StoreProduct.objects.filter(
                store=store,
                slug=src_product.slug
            ).first()
            
            if existing:
                # Update existing product
                existing.name = src_product.name
                existing.description = src_product.description
                existing.price = src_product.price
                existing.compare_at_price = src_product.compare_at_price
                existing.status = src_product.status
                if src_product.category_id and src_product.category_id in category_map:
                    existing.category = category_map[src_product.category_id]
                existing.save()
            else:
                # Create new product
                new_category = None
                if src_product.category_id and src_product.category_id in category_map:
                    new_category = category_map[src_product.category_id]
                
                StoreProduct.objects.create(
                    store=store,
                    category=new_category,
                    name=src_product.name,
                    slug=src_product.slug,
                    description=src_product.description,
                    short_description=src_product.short_description,
                    price=src_product.price,
                    compare_at_price=src_product.compare_at_price,
                    cost_price=src_product.cost_price,
                    sku=src_product.sku,
                    status=src_product.status,
                    is_featured=src_product.is_featured,
                    track_stock=src_product.track_stock,
                    stock_quantity=src_product.stock_quantity,
                    low_stock_threshold=src_product.low_stock_threshold,
                    weight=src_product.weight,
                    dimensions=src_product.dimensions,
                    tags=src_product.tags,
                    metadata=src_product.metadata,
                )
                synced_products += 1
        
        logger.info(f"Synced Pastita to store {store.name}: {synced_products} products, {synced_categories} categories")
        
        return {
            'products_synced': synced_products,
            'categories_synced': synced_categories,
            'source_store': pastita_store.name if pastita_store else 'default'
        }
    
    def _create_default_pastita_products(self, store) -> Dict[str, Any]:
        """Create default Pastita products if no source store exists."""
        from apps.stores.models import StoreProduct, StoreCategory
        from decimal import Decimal
        
        # Create categories
        categories_data = [
            ('massas-frescas', 'Massas Frescas', 'Massas artesanais feitas diariamente'),
            ('molhos', 'Molhos', 'Molhos caseiros para acompanhar'),
            ('combos', 'Combos', 'Combinações especiais com desconto'),
        ]
        
        categories = {}
        for slug, name, desc in categories_data:
            cat, _ = StoreCategory.objects.get_or_create(
                store=store,
                slug=slug,
                defaults={'name': name, 'description': desc}
            )
            categories[slug] = cat
        
        # Create sample products
        products_data = [
            {
                'category': 'massas-frescas',
                'name': 'Tagliatelle Tradicional',
                'slug': 'tagliatelle-tradicional',
                'description': 'Massa fresca de tagliatelle feita com farinha especial',
                'price': Decimal('24.90'),
            },
            {
                'category': 'massas-frescas',
                'name': 'Ravioli de Queijo',
                'slug': 'ravioli-queijo',
                'description': 'Ravioli recheado com blend de queijos',
                'price': Decimal('32.90'),
            },
            {
                'category': 'massas-frescas',
                'name': 'Gnocchi de Batata',
                'slug': 'gnocchi-batata',
                'description': 'Gnocchi artesanal de batata',
                'price': Decimal('28.90'),
            },
            {
                'category': 'molhos',
                'name': 'Molho Pomodoro',
                'slug': 'molho-pomodoro',
                'description': 'Molho de tomate italiano tradicional',
                'price': Decimal('18.90'),
            },
            {
                'category': 'molhos',
                'name': 'Molho Alfredo',
                'slug': 'molho-alfredo',
                'description': 'Molho cremoso com parmesão',
                'price': Decimal('22.90'),
            },
            {
                'category': 'combos',
                'name': 'Combo Família',
                'slug': 'combo-familia',
                'description': '3 massas + 2 molhos para toda família',
                'price': Decimal('89.90'),
                'compare_at_price': Decimal('115.00'),
            },
        ]
        
        created_count = 0
        for prod_data in products_data:
            cat_slug = prod_data.pop('category')
            category = categories.get(cat_slug)
            
            _, created = StoreProduct.objects.get_or_create(
                store=store,
                slug=prod_data['slug'],
                defaults={
                    'category': category,
                    'status': 'active',
                    **prod_data
                }
            )
            if created:
                created_count += 1
        
        return {
            'products_synced': created_count,
            'categories_synced': len(categories),
            'source_store': 'default_template'
        }


# Import models at module level to avoid circular imports
from django.db import models

store_service = StoreService()
