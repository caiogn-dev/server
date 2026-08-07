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
        
        # Faturamento vem do núcleo. Antes filtrava por `created_at`, um eixo
        # diferente do resto do painel: pedido feito 23h40 e pago 00h05 caía em
        # dias distintos conforme a tela, e não conciliava com o extrato.
        from apps.stores import metrics

        paid_orders = metrics.pedidos_de_receita(queryset=orders)
        total_revenue = paid_orders.aggregate(total=Sum('total'))['total'] or Decimal('0.00')
        revenue_today = metrics.totais(store, metrics.hoje())['receita']
        revenue_this_week = metrics.totais(store, metrics.ultimos_dias(8))['receita']
        revenue_this_month = metrics.totais(store, metrics.ultimos_dias(31))['receita']

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
        
        # Daily orders for chart (last 30 days).
        # Usa o SSOT de receita: antes somava `orders` cru e o gráfico da home
        # mostrava R$ 5.056 numa loja que faturou R$ 2.324 — os 21 cancelados
        # entravam como faturamento, e os pedidos de teste do dono também.
        # Série pelo núcleo: agrupa pelo MESMO eixo em que filtra (data do
        # pagamento). Agrupar por `created_at` e filtrar por outro deixava
        # pedido dentro da janela fora do gráfico.
        daily_orders = [
            {'date': p['periodo'], 'count': p['pedidos'], 'revenue': p['receita']}
            for p in metrics.serie_temporal(store, metrics.ultimos_dias(31))
        ]
        
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

    def test_integration(self, integration) -> Dict[str, Any]:
        """
        Test an integration connection.
        Verifies connectivity and authentication for various integration types.
        """
        import requests
        from django.conf import settings
        
        integration_type = integration.integration_type
        result = {
            'success': False,
            'integration_type': integration_type,
            'integration_name': integration.name,
            'message': '',
            'details': {}
        }
        
        try:
            if integration_type == 'whatsapp':
                result = self._test_whatsapp_integration(integration, result)
            elif integration_type == 'mercadopago':
                result = self._test_mercadopago_integration(integration, result)
            elif integration_type == 'instagram':
                result = self._test_instagram_integration(integration, result)
            elif integration_type == 'webhook':
                result = self._test_webhook_integration(integration, result)
            elif integration_type == 'email':
                result = self._test_email_integration(integration, result)
            else:
                result['message'] = f'Testing not implemented for integration type: {integration_type}'
                result['success'] = True  # Consider unknown types as success (no test needed)
            
            # Update integration last_sync_at if successful
            if result['success']:
                integration.last_sync_at = timezone.now()
                integration.save(update_fields=['last_sync_at'])
                
        except Exception as e:
            result['success'] = False
            result['message'] = 'Erro ao testar integração.'
            logger.error('Erro ao testar integração %s: %s', integration.name, e)
        
        return result
    
    def _test_whatsapp_integration(self, integration, result: Dict) -> Dict:
        """Test WhatsApp Business API integration."""
        import requests
        
        access_token = integration.access_token
        phone_number_id = integration.phone_number_id
        
        if not access_token or not phone_number_id:
            result['message'] = 'Missing access_token or phone_number_id'
            return result
        
        # Test by getting phone number info
        url = f"https://graph.facebook.com/v18.0/{phone_number_id}"
        headers = {'Authorization': f'Bearer {access_token}'}
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                result['success'] = True
                result['message'] = 'WhatsApp Business API connection successful'
                result['details'] = {
                    'phone_number': data.get('display_phone_number', 'N/A'),
                    'verified_name': data.get('verified_name', 'N/A'),
                    'quality_rating': data.get('quality_rating', 'N/A'),
                }
            else:
                result['message'] = f'WhatsApp API error: {response.status_code}'
                result['details'] = {'error': response.text[:500]}
        except requests.RequestException as e:
            logger.error('Erro de conexão na integração WhatsApp %s: %s', integration.name, e)
            result['message'] = 'Erro de conexão.'

        return result

    def _test_mercadopago_integration(self, integration, result: Dict) -> Dict:
        """Test Mercado Pago integration."""
        import requests
        
        access_token = integration.access_token
        
        if not access_token:
            result['message'] = 'Missing access_token'
            return result
        
        # Test by getting user info
        url = "https://api.mercadopago.com/users/me"
        headers = {'Authorization': f'Bearer {access_token}'}
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                result['success'] = True
                result['message'] = 'Mercado Pago connection successful'
                result['details'] = {
                    'user_id': data.get('id'),
                    'nickname': data.get('nickname', 'N/A'),
                    'email': data.get('email', 'N/A'),
                    'site_id': data.get('site_id', 'N/A'),
                }
            else:
                result['message'] = f'Mercado Pago API error: {response.status_code}'
                result['details'] = {'error': response.text[:500]}
        except requests.RequestException as e:
            logger.error('Erro de conexão na integração MercadoPago %s: %s', integration.name, e)
            result['message'] = 'Erro de conexão.'

        return result

    def _test_instagram_integration(self, integration, result: Dict) -> Dict:
        """Test Instagram API integration."""
        import requests
        
        access_token = integration.access_token
        instagram_id = integration.external_id
        
        if not access_token:
            result['message'] = 'Missing access_token'
            return result
        
        # Test by getting account info
        url = f"https://graph.facebook.com/v18.0/{instagram_id or 'me'}"
        params = {'fields': 'id,username,name,account_type', 'access_token': access_token}
        
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                result['success'] = True
                result['message'] = 'Instagram API connection successful'
                result['details'] = {
                    'account_id': data.get('id'),
                    'username': data.get('username', 'N/A'),
                    'name': data.get('name', 'N/A'),
                    'account_type': data.get('account_type', 'N/A'),
                }
            else:
                result['message'] = f'Instagram API error: {response.status_code}'
                result['details'] = {'error': response.text[:500]}
        except requests.RequestException as e:
            logger.error('Erro de conexão na integração Instagram %s: %s', integration.name, e)
            result['message'] = 'Erro de conexão.'

        return result

    def _test_webhook_integration(self, integration, result: Dict) -> Dict:
        """Test webhook endpoint connectivity."""
        import requests
        
        webhook_url = integration.webhook_url
        
        if not webhook_url:
            result['message'] = 'Missing webhook_url'
            return result
        
        # Send a test ping to the webhook
        test_payload = {
            'event': 'test.ping',
            'timestamp': timezone.now().isoformat(),
            'store_id': str(integration.store.id),
            'integration_id': str(integration.id),
        }
        
        headers = {'Content-Type': 'application/json'}
        if integration.webhook_secret:
            import hashlib
            import hmac
            import json
            payload_str = json.dumps(test_payload)
            signature = hmac.new(
                integration.webhook_secret.encode(),
                payload_str.encode(),
                hashlib.sha256
            ).hexdigest()
            headers['X-Webhook-Signature'] = signature
        
        try:
            response = requests.post(
                webhook_url,
                json=test_payload,
                headers=headers,
                timeout=10
            )
            
            if response.status_code in [200, 201, 202, 204]:
                result['success'] = True
                result['message'] = 'Webhook endpoint reachable'
                result['details'] = {
                    'status_code': response.status_code,
                    'response_time_ms': response.elapsed.total_seconds() * 1000,
                }
            else:
                result['message'] = f'Webhook returned error: {response.status_code}'
                result['details'] = {
                    'status_code': response.status_code,
                    'response': response.text[:500],
                }
        except requests.RequestException as e:
            logger.error('Erro de conexão com webhook da integração %s: %s', integration.name, e)
            result['message'] = 'Erro de conexão com webhook.'

        return result

    def _test_email_integration(self, integration, result: Dict) -> Dict:
        """Test email service integration."""
        from django.conf import settings
        
        # Check for required settings
        email_settings = integration.settings or {}
        api_key = integration.api_key
        
        if not api_key and not email_settings.get('smtp_host'):
            result['message'] = 'Missing email configuration (API key or SMTP settings)'
            return result
        
        if api_key:
            # Test Resend or similar API
            import requests
            try:
                response = requests.get(
                    "https://api.resend.com/domains",
                    headers={'Authorization': f'Bearer {api_key}'},
                    timeout=10
                )
                if response.status_code == 200:
                    result['success'] = True
                    result['message'] = 'Email API connection successful'
                    result['details'] = {'provider': 'resend'}
                else:
                    result['message'] = f'Email API error: {response.status_code}'
            except requests.RequestException as e:
                logger.error('Erro de conexão com API de email (integração %s): %s', integration.name, e)
                result['message'] = 'Erro de conexão.'
        else:
            # Test SMTP connection
            import smtplib
            try:
                smtp_host = email_settings.get('smtp_host')
                smtp_port = email_settings.get('smtp_port', 587)
                smtp_user = email_settings.get('smtp_user')
                smtp_pass = email_settings.get('smtp_pass')

                with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                    server.starttls()
                    if smtp_user and smtp_pass:
                        server.login(smtp_user, smtp_pass)
                    result['success'] = True
                    result['message'] = 'SMTP connection successful'
                    result['details'] = {'host': smtp_host, 'port': smtp_port}
            except Exception as e:
                logger.error('Erro de conexão SMTP (integração %s): %s', integration.name, e)
                result['message'] = 'Erro de conexão SMTP.'
        
        return result


# Import models at module level to avoid circular imports
from django.db import models

store_service = StoreService()
