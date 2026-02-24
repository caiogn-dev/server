"""
Integration tests for Pastita LangGraph Orchestrator.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

from apps.automation.services.pastita_langgraph_orchestrator import (
    LangGraphOrchestrator,
    ContextRouter,
    process_whatsapp_message_langgraph,
)
from apps.automation.graphs.pastita_graph import (
    ConversationState,
    IntentType,
    ContextSource,
    create_initial_state,
)


@pytest.mark.django_db
class TestLangGraphOrchestrator:
    """Integration tests for LangGraphOrchestrator."""
    
    @pytest.fixture
    def setup_mocks(self):
        """Setup common mocks."""
        account = Mock()
        account.id = 'account-id'
        
        conversation = Mock()
        conversation.id = 'conv-id'
        conversation.phone_number = '55999999999'
        conversation.contact_name = 'Test User'
        
        company = Mock()
        company.id = 'company-id'
        company.store = Mock()
        company.store.id = 'store-id'
        
        store = Mock()
        store.id = 'store-id'
        store.name = 'Pastita'
        
        return account, conversation, company, store
    
    def test_orchestrator_initialization(self, setup_mocks):
        """Test orchestrator initialization."""
        # Arrange
        account, conversation, company, store = setup_mocks
        
        with patch('apps.automation.models.CustomerSession.objects.get_or_create') as mock_get_or_create:
            mock_session = Mock()
            mock_session.id = 'session-id'
            mock_session.cart_data = {'items': []}
            mock_session.cart_total = 0
            mock_get_or_create.return_value = (mock_session, True)
            
            # Act
            orchestrator = LangGraphOrchestrator(
                account=account,
                conversation=conversation,
                company=company,
                store=store,
                debug=False
            )
            
            # Assert
            assert orchestrator.account == account
            assert orchestrator.conversation == conversation
            assert orchestrator.graph_state is not None
    
    def test_process_message_greeting(self, setup_mocks):
        """Test processing greeting message."""
        # Arrange
        account, conversation, company, store = setup_mocks
        
        with patch('apps.automation.models.CustomerSession.objects.get_or_create') as mock_get_or_create:
            mock_session = Mock()
            mock_session.id = 'session-id'
            mock_session.cart_data = {'items': []}
            mock_session.cart_total = 0
            mock_get_or_create.return_value = (mock_session, True)
            
            orchestrator = LangGraphOrchestrator(
                account=account,
                conversation=conversation,
                company=company,
                store=store,
                debug=False
            )
            
            # Act
            result = orchestrator.process_message("Oi")
            
            # Assert
            assert 'response_text' in result
            assert result['current_state'] == ConversationState.MENU
    
    def test_process_message_menu_request(self, setup_mocks):
        """Test processing menu request."""
        # Arrange
        account, conversation, company, store = setup_mocks
        
        with patch('apps.automation.models.CustomerSession.objects.get_or_create') as mock_get_or_create:
            mock_session = Mock()
            mock_session.id = 'session-id'
            mock_session.cart_data = {'items': []}
            mock_session.cart_total = 0
            mock_get_or_create.return_value = (mock_session, True)
            
            with patch('apps.automation.services.pastita_tools.get_menu') as mock_get_menu:
                mock_get_menu.invoke.return_value = "📋 CARDÁPIO\n\n*Massas*\n• Rondelli - R$ 45.00"
                
                orchestrator = LangGraphOrchestrator(
                    account=account,
                    conversation=conversation,
                    company=company,
                    store=store,
                    debug=False
                )
                
                # Act
                result = orchestrator.process_message("cardápio")
                
                # Assert
                assert 'response_text' in result
                assert result['intent'] == IntentType.MENU_REQUEST
    
    def test_process_message_add_to_cart(self, setup_mocks):
        """Test processing add to cart message."""
        # Arrange
        account, conversation, company, store = setup_mocks
        
        with patch('apps.automation.models.CustomerSession.objects.get_or_create') as mock_get_or_create:
            mock_session = Mock()
            mock_session.id = 'session-id'
            mock_session.cart_data = {'items': []}
            mock_session.cart_total = 0
            mock_get_or_create.return_value = (mock_session, True)
            
            with patch('apps.automation.services.pastita_tools.add_to_cart') as mock_add:
                mock_add.invoke.return_value = "✅ 2x Rondelli adicionado!"
                
                orchestrator = LangGraphOrchestrator(
                    account=account,
                    conversation=conversation,
                    company=company,
                    store=store,
                    debug=False
                )
                
                # Act
                result = orchestrator.process_message("2 rondelli")
                
                # Assert
                assert 'response_text' in result
                assert result['intent'] == IntentType.ADD_TO_CART
    
    def test_reset_orchestrator(self, setup_mocks):
        """Test resetting orchestrator."""
        # Arrange
        account, conversation, company, store = setup_mocks
        
        with patch('apps.automation.models.CustomerSession.objects.get_or_create') as mock_get_or_create:
            mock_session = Mock()
            mock_session.id = 'session-id'
            mock_session.cart_data = {'items': [{'name': 'Rondelli'}]}
            mock_session.cart_total = 45
            mock_get_or_create.return_value = (mock_session, True)
            
            with patch('apps.automation.services.pastita_tools.clear_cart') as mock_clear:
                mock_clear.invoke.return_value = "Carrinho limpo"
                
                orchestrator = LangGraphOrchestrator(
                    account=account,
                    conversation=conversation,
                    company=company,
                    store=store,
                    debug=False
                )
                
                # Act
                orchestrator.reset()
                
                # Assert
                assert orchestrator.graph_state['current_state'] == ConversationState.GREETING
                assert orchestrator.graph_state['cart']['items'] == []


@pytest.mark.django_db
class TestContextRouter:
    """Tests for ContextRouter."""
    
    @pytest.fixture
    def setup_router(self):
        """Setup context router."""
        company = Mock()
        return ContextRouter(company)
    
    def test_route_handler_intents(self, setup_router):
        """Test routing handler intents."""
        # Arrange
        router = setup_router
        state = {
            'last_intent': IntentType.ADD_TO_CART,
            'current_state': ConversationState.MENU,
            'error_count': 0
        }
        
        # Act
        result = router.route(state)
        
        # Assert
        assert result == ContextSource.HANDLER
    
    def test_route_critical_states(self, setup_router):
        """Test routing critical states."""
        # Arrange
        router = setup_router
        state = {
            'last_intent': IntentType.UNKNOWN,
            'current_state': ConversationState.AWAITING_PAYMENT,
            'error_count': 0
        }
        
        # Act
        result = router.route(state)
        
        # Assert
        assert result == ContextSource.HANDLER
    
    def test_route_error_fallback(self, setup_router):
        """Test routing with errors."""
        # Arrange
        router = setup_router
        state = {
            'last_intent': IntentType.ADD_TO_CART,
            'current_state': ConversationState.MENU,
            'error_count': 3
        }
        
        # Act
        result = router.route(state)
        
        # Assert
        assert result == ContextSource.LLM
    
    def test_route_unknown_intent(self, setup_router):
        """Test routing unknown intent."""
        # Arrange
        router = setup_router
        state = {
            'last_intent': IntentType.UNKNOWN,
            'current_state': ConversationState.MENU,
            'error_count': 0
        }
        
        # Act
        result = router.route(state)
        
        # Assert
        assert result == ContextSource.LLM


@pytest.mark.django_db
class TestProcessWhatsAppMessage:
    """Tests for process_whatsapp_message_langgraph function."""
    
    def test_process_message_success(self):
        """Test successful message processing."""
        # Arrange
        account = Mock()
        account.id = 'account-id'
        account.company_profile = Mock()
        account.company_profile.id = 'company-id'
        account.company_profile.store = Mock()
        account.company_profile.store.id = 'store-id'
        
        conversation = Mock()
        conversation.phone_number = '55999999999'
        
        with patch('apps.automation.models.CompanyProfile.objects.filter') as mock_company:
            mock_company.return_value.first.return_value = account.company_profile
            
            with patch('apps.stores.models.Store.objects.filter') as mock_store:
                mock_store.return_value.first.return_value = account.company_profile.store
                
                with patch('apps.automation.models.CustomerSession.objects.get_or_create') as mock_session:
                    mock_session_obj = Mock()
                    mock_session_obj.id = 'session-id'
                    mock_session_obj.cart_data = {'items': []}
                    mock_session_obj.cart_total = 0
                    mock_session.return_value = (mock_session_obj, True)
                    
                    # Act
                    result = process_whatsapp_message_langgraph(
                        account=account,
                        conversation=conversation,
                        message_text="Oi"
                    )
                    
                    # Assert
                    assert result is not None
                    assert 'response_text' in result
    
    def test_process_message_company_not_found(self):
        """Test processing when company not found."""
        # Arrange
        account = Mock()
        conversation = Mock()
        
        with patch('apps.automation.models.CompanyProfile.objects.filter') as mock_company:
            mock_company.return_value.first.return_value = None
            
            # Act
            result = process_whatsapp_message_langgraph(
                account=account,
                conversation=conversation,
                message_text="Oi"
            )
            
            # Assert
            assert result is None


@pytest.mark.django_db
class TestFullFlow:
    """End-to-end flow tests."""
    
    def test_complete_order_flow(self):
        """Test complete order flow from greeting to confirmation."""
        # Este teste simula o fluxo completo de uma conversa
        # Saudação -> Cardápio -> Adicionar -> Carrinho -> Finalizar -> Confirmação
        
        # Arrange
        account = Mock()
        account.id = 'account-id'
        
        conversation = Mock()
        conversation.id = 'conv-id'
        conversation.phone_number = '55999999999'
        
        company = Mock()
        company.id = 'company-id'
        company.store = Mock()
        company.store.id = 'store-id'
        
        store = Mock()
        store.id = 'store-id'
        
        with patch('apps.automation.models.CustomerSession.objects.get_or_create') as mock_get_or_create:
            mock_session = Mock()
            mock_session.id = 'session-id'
            mock_session.cart_data = {'items': []}
            mock_session.cart_total = 0
            mock_get_or_create.return_value = (mock_session, True)
            
            orchestrator = LangGraphOrchestrator(
                account=account,
                conversation=conversation,
                company=company,
                store=store,
                debug=False
            )
            
            # Act - Fluxo completo
            # 1. Saudação
            result1 = orchestrator.process_message("Oi")
            assert result1['current_state'] == ConversationState.MENU
            
            # 2. Ver cardápio
            with patch('apps.automation.services.pastita_tools.get_menu') as mock_menu:
                mock_menu.invoke.return_value = "📋 CARDÁPIO\n• Rondelli - R$ 45.00"
                result2 = orchestrator.process_message("cardápio")
                assert result2['intent'] == IntentType.MENU_REQUEST
            
            # 3. Adicionar ao carrinho
            with patch('apps.automation.services.pastita_tools.add_to_cart') as mock_add:
                mock_add.invoke.return_value = "✅ Adicionado!"
                result3 = orchestrator.process_message("2 rondelli")
                assert result3['intent'] == IntentType.ADD_TO_CART
                assert result3['current_state'] == ConversationState.CART
            
            # 4. Ver carrinho
            with patch('apps.automation.services.pastita_tools.view_cart') as mock_view:
                mock_view.invoke.return_value = "🛒 Carrinho: 2 itens"
                result4 = orchestrator.process_message("carrinho")
                assert result4['intent'] == IntentType.VIEW_CART
            
            # 5. Iniciar checkout
            result5 = orchestrator.process_message("finalizar")
            assert result5['intent'] == IntentType.CREATE_ORDER
            assert result5['current_state'] == ConversationState.DELIVERY_METHOD
            
            # 6. Selecionar retirada
            result6 = orchestrator.process_message("retirada")
            assert result6['intent'] == IntentType.SELECT_PICKUP
            assert result6['current_state'] == ConversationState.PAYMENT_METHOD
