"""
Tests for Pastita LangGraph Tools.
"""
import pytest
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock

from apps.automation.services.pastita_tools import (
    get_menu,
    get_product_info,
    add_to_cart,
    remove_from_cart,
    view_cart,
    clear_cart,
    calculate_delivery_fee,
    create_order,
    generate_pix,
    check_order_status,
)


@pytest.mark.django_db
class TestGetMenu:
    """Tests for get_menu tool."""
    
    def test_get_menu_success(self):
        """Test getting menu with products."""
        # Arrange
        store = Mock()
        store.id = 'test-store-id'
        store.name = 'Test Store'
        
        with patch('apps.stores.models.Store.objects.filter') as mock_filter:
            mock_filter.return_value.first.return_value = store
            
            with patch('apps.stores.models.StoreProduct.objects.filter') as mock_products:
                mock_products.return_value.select_related.return_value.order_by.return_value = []
                
                # Act
                result = get_menu.invoke({'store_id': 'test-store-id'})
                
                # Assert
                assert 'CARDÁPIO' in result
    
    def test_get_menu_store_not_found(self):
        """Test getting menu for non-existent store."""
        with patch('apps.stores.models.Store.objects.filter') as mock_filter:
            mock_filter.return_value.first.return_value = None
            
            result = get_menu.invoke({'store_id': 'invalid-id'})
            
            assert 'Loja não encontrada' in result


@pytest.mark.django_db
class TestAddToCart:
    """Tests for add_to_cart tool."""
    
    def test_add_to_cart_success(self):
        """Test adding item to cart."""
        # Arrange
        session = Mock()
        session.id = 'test-session-id'
        session.cart_data = {'items': []}
        session.cart_total = 0
        
        product = Mock()
        product.id = 'test-product-id'
        product.name = 'Rondelli de Frango'
        product.price = Decimal('45.00')
        product.track_stock = True
        product.stock_quantity = 10
        
        with patch('apps.automation.models.CustomerSession.objects.filter') as mock_filter:
            mock_filter.return_value.first.return_value = session
            
            with patch('apps.stores.models.StoreProduct.objects.filter') as mock_product:
                mock_product.return_value.filter.return_value.first.return_value = product
                
                # Act
                result = add_to_cart.invoke({
                    'session_id': 'test-session-id',
                    'product_name': 'Rondelli',
                    'quantity': 2
                })
                
                # Assert
                assert 'adicionado' in result.lower()
                assert 'Rondelli' in result
    
    def test_add_to_cart_insufficient_stock(self):
        """Test adding item with insufficient stock."""
        # Arrange
        session = Mock()
        session.id = 'test-session-id'
        
        product = Mock()
        product.name = 'Rondelli'
        product.track_stock = True
        product.stock_quantity = 1
        
        with patch('apps.automation.models.CustomerSession.objects.filter') as mock_filter:
            mock_filter.return_value.first.return_value = session
            
            with patch('apps.stores.models.StoreProduct.objects.filter') as mock_product:
                mock_product.return_value.filter.return_value.first.return_value = product
                
                # Act
                result = add_to_cart.invoke({
                    'session_id': 'test-session-id',
                    'product_name': 'Rondelli',
                    'quantity': 5
                })
                
                # Assert
                assert 'Estoque insuficiente' in result


@pytest.mark.django_db
class TestViewCart:
    """Tests for view_cart tool."""
    
    def test_view_cart_empty(self):
        """Test viewing empty cart."""
        # Arrange
        session = Mock()
        session.id = 'test-session-id'
        session.cart_data = {'items': []}
        session.cart_total = 0
        
        with patch('apps.automation.models.CustomerSession.objects.filter') as mock_filter:
            mock_filter.return_value.first.return_value = session
            
            # Act
            result = view_cart.invoke({'session_id': 'test-session-id'})
            
            # Assert
            assert 'vazio' in result.lower()
    
    def test_view_cart_with_items(self):
        """Test viewing cart with items."""
        # Arrange
        session = Mock()
        session.id = 'test-session-id'
        session.cart_data = {
            'items': [
                {'name': 'Rondelli', 'quantity': 2, 'price': '45.00'}
            ]
        }
        session.cart_total = Decimal('90.00')
        
        with patch('apps.automation.models.CustomerSession.objects.filter') as mock_filter:
            mock_filter.return_value.first.return_value = session
            
            # Act
            result = view_cart.invoke({'session_id': 'test-session-id'})
            
            # Assert
            assert 'Rondelli' in result
            assert 'R$ 90.00' in result


@pytest.mark.django_db
class TestClearCart:
    """Tests for clear_cart tool."""
    
    def test_clear_cart_success(self):
        """Test clearing cart."""
        # Arrange
        session = Mock()
        session.id = 'test-session-id'
        session.cart_data = {'items': [{'name': 'Rondelli', 'quantity': 1}]}
        
        with patch('apps.automation.models.CustomerSession.objects.filter') as mock_filter:
            mock_filter.return_value.first.return_value = session
            
            # Act
            result = clear_cart.invoke({'session_id': 'test-session-id'})
            
            # Assert
            assert 'limpo' in result.lower() or 'vazio' in result.lower()


@pytest.mark.django_db
class TestCalculateDeliveryFee:
    """Tests for calculate_delivery_fee tool."""
    
    def test_calculate_delivery_fee_success(self):
        """Test calculating delivery fee."""
        # Arrange
        store = Mock()
        store.id = 'test-store-id'
        store.latitude = -10.1849
        store.longitude = -48.3346
        store.default_delivery_fee = Decimal('5.00')
        
        geocode_result = {
            'lat': -10.1900,
            'lng': -48.3400,
            'formatted_address': 'Rua Teste, 123'
        }
        
        route_result = {
            'distance_km': 2.5,
            'duration_minutes': 10,
            'polyline': 'test'
        }
        
        with patch('apps.stores.models.Store.objects.filter') as mock_filter:
            mock_filter.return_value.first.return_value = store
            
            with patch('apps.stores.services.here_maps_service.here_maps_service.geocode') as mock_geocode:
                mock_geocode.return_value = geocode_result
                
                with patch('apps.stores.services.here_maps_service.here_maps_service.calculate_route') as mock_route:
                    mock_route.return_value = route_result
                    
                    # Act
                    result = calculate_delivery_fee.invoke({
                        'store_id': 'test-store-id',
                        'address': 'Rua Teste, 123'
                    })
                    
                    # Assert
                    assert result['is_valid'] is True
                    assert result['fee'] is not None
    
    def test_calculate_delivery_fee_out_of_area(self):
        """Test calculating fee for address out of delivery area."""
        # Arrange
        store = Mock()
        store.id = 'test-store-id'
        store.latitude = -10.1849
        store.longitude = -48.3346
        
        geocode_result = {
            'lat': -10.5000,
            'lng': -48.6000,
            'formatted_address': 'Rua Longe, 123'
        }
        
        route_result = {
            'distance_km': 25.0,  # Acima do limite de 20km
            'duration_minutes': 45,
        }
        
        with patch('apps.stores.models.Store.objects.filter') as mock_filter:
            mock_filter.return_value.first.return_value = store
            
            with patch('apps.stores.services.here_maps_service.here_maps_service.geocode') as mock_geocode:
                mock_geocode.return_value = geocode_result
                
                with patch('apps.stores.services.here_maps_service.here_maps_service.calculate_route') as mock_route:
                    mock_route.return_value = route_result
                    
                    # Act
                    result = calculate_delivery_fee.invoke({
                        'store_id': 'test-store-id',
                        'address': 'Rua Longe, 123'
                    })
                    
                    # Assert
                    assert result['is_valid'] is False
                    assert 'fora da área' in result['message'].lower()


@pytest.mark.django_db
class TestCreateOrder:
    """Tests for create_order tool."""
    
    def test_create_order_success(self):
        """Test creating order."""
        # Arrange
        session = Mock()
        session.id = 'test-session-id'
        session.cart_data = {
            'items': [
                {'product_id': 'p1', 'name': 'Rondelli', 'quantity': 2, 'price': '45.00'}
            ]
        }
        session.cart_total = Decimal('90.00')
        session.company.store = Mock()
        session.phone_number = '55999999999'
        session.customer_name = 'Test Customer'
        
        order = Mock()
        order.id = 'order-id'
        order.order_number = 'PAS2502240001'
        order.total = Decimal('90.00')
        order.status = 'confirmed'
        
        with patch('apps.automation.models.CustomerSession.objects.filter') as mock_filter:
            mock_filter.return_value.first.return_value = session
            
            with patch('apps.stores.models.StoreOrder.objects.create') as mock_create:
                mock_create.return_value = order
                
                with patch('apps.stores.models.StoreOrderItem.objects.create'):
                    
                    # Act
                    result = create_order.invoke({
                        'session_id': 'test-session-id',
                        'payment_method': 'cash',
                        'delivery_method': 'pickup'
                    })
                    
                    # Assert
                    assert result['success'] is True
                    assert result['order_number'] == 'PAS2502240001'
    
    def test_create_order_empty_cart(self):
        """Test creating order with empty cart."""
        # Arrange
        session = Mock()
        session.id = 'test-session-id'
        session.cart_data = {'items': []}
        
        with patch('apps.automation.models.CustomerSession.objects.filter') as mock_filter:
            mock_filter.return_value.first.return_value = session
            
            # Act
            result = create_order.invoke({
                'session_id': 'test-session-id',
                'payment_method': 'cash',
                'delivery_method': 'pickup'
            })
            
            # Assert
            assert result['success'] is False
            assert 'vazio' in result['error'].lower()


@pytest.mark.django_db
class TestCheckOrderStatus:
    """Tests for check_order_status tool."""
    
    def test_check_order_status_success(self):
        """Test checking order status."""
        # Arrange
        order = Mock()
        order.order_number = 'PAS2502240001'
        order.status = 'preparing'
        order.payment_status = 'paid'
        order.total = Decimal('90.00')
        order.delivery_method = 'delivery'
        order.tracking_code = 'TRK123'
        
        with patch('apps.stores.models.StoreOrder.objects.filter') as mock_filter:
            mock_filter.return_value.first.return_value = order
            
            # Act
            result = check_order_status.invoke({'order_number': 'PAS2502240001'})
            
            # Assert
            assert 'PAS2502240001' in result
            assert 'Preparo' in result or 'preparo' in result
    
    def test_check_order_status_not_found(self):
        """Test checking status of non-existent order."""
        with patch('apps.stores.models.StoreOrder.objects.filter') as mock_filter:
            mock_filter.return_value.first.return_value = None
            
            # Act
            result = check_order_status.invoke({'order_number': 'INVALID'})
            
            # Assert
            assert 'não encontrado' in result.lower()
