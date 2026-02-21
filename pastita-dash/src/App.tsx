import React, { useEffect, useState, Suspense, lazy } from 'react';
import logger from './services/logger';
import { Routes, Route, Navigate } from 'react-router-dom';
import { MainLayout } from './components/layout';
import { FullPageLoading } from './components/common';
import { useAuthStore } from './stores/authStore';
import { useAccountStore } from './stores/accountStore';
import { whatsappService, setAuthToken } from './services';
import { WebSocketProvider } from './context/WebSocketContext';
import { WhatsAppWsProvider } from './context/WhatsAppWsContext';

// Lazy load pages for better performance
const LoginPage = lazy(() => import('./pages/auth/LoginPage').then(m => ({ default: m.LoginPage })));
const DashboardPage = lazy(() => import('./pages/dashboard/DashboardPage').then(m => ({ default: m.DashboardPage })));
const AccountsPage = lazy(() => import('./pages/accounts/AccountsPage').then(m => ({ default: m.AccountsPage })));
const AccountFormPage = lazy(() => import('./pages/accounts/AccountFormPage').then(m => ({ default: m.AccountFormPage })));
const AccountDetailPage = lazy(() => import('./pages/accounts/AccountDetailPage').then(m => ({ default: m.AccountDetailPage })));
const MessagesPage = lazy(() => import('./pages/messages/MessagesPage').then(m => ({ default: m.MessagesPage })));
const ConversationsPage = lazy(() => import('./pages/conversations/ConversationsPage').then(m => ({ default: m.ConversationsPage })));
const OrdersPage = lazy(() => import('./pages/orders/OrdersPage').then(m => ({ default: m.OrdersPage })));
const OrderDetailPage = lazy(() => import('./pages/orders/OrderDetailPageNew').then(m => ({ default: m.OrderDetailPageNew })));
const PaymentsPage = lazy(() => import('./pages/payments/PaymentsPage').then(m => ({ default: m.PaymentsPage })));
const SettingsPage = lazy(() => import('./pages/settings/SettingsPage').then(m => ({ default: m.SettingsPage })));

// Agents Pages (Langchain AI)
const AgentsPage = lazy(() => import('./pages/agents').then(m => ({ default: m.AgentsPage })));
const AgentDetailPage = lazy(() => import('./pages/agents').then(m => ({ default: m.AgentDetailPage })));
const AgentCreatePage = lazy(() => import('./pages/agents').then(m => ({ default: m.AgentCreatePage })));
const AgentTestPage = lazy(() => import('./pages/agents').then(m => ({ default: m.AgentTestPage })));
const UnifiedOrchestratorTest = lazy(() => import('./pages/agents').then(m => ({ default: m.UnifiedOrchestratorTest })));

// E-commerce Pages
const CouponsPage = lazy(() => import('./pages/coupons').then(m => ({ default: m.CouponsPage })));
const ProductsPage = lazy(() => import('./pages/products/ProductsPageNew').then(m => ({ default: m.ProductsPageNew })));

// Automation Pages
const CompanyProfilesPage = lazy(() => import('./pages/automation').then(m => ({ default: m.CompanyProfilesPage })));
const CompanyProfileDetailPage = lazy(() => import('./pages/automation').then(m => ({ default: m.CompanyProfileDetailPage })));
const AutoMessagesPage = lazy(() => import('./pages/automation').then(m => ({ default: m.AutoMessagesPage })));
const CustomerSessionsPage = lazy(() => import('./pages/automation').then(m => ({ default: m.CustomerSessionsPage })));
const AutomationLogsPage = lazy(() => import('./pages/automation').then(m => ({ default: m.AutomationLogsPage })));
const ScheduledMessagesPage = lazy(() => import('./pages/automation').then(m => ({ default: m.ScheduledMessagesPage })));
const ReportsPage = lazy(() => import('./pages/automation').then(m => ({ default: m.ReportsPage })));

// Intent Detection Pages (Novo Sistema)
const IntentStatsPage = lazy(() => import('./pages/automation').then(m => ({ default: m.IntentStatsPage })));
const IntentLogsPage = lazy(() => import('./pages/automation').then(m => ({ default: m.IntentLogsPage })));

// Analytics/Reports Pages
const AnalyticsPage = lazy(() => import('./pages/reports').then(m => ({ default: m.AnalyticsPage })));

// Stores Pages
const StoresPage = lazy(() => import('./pages/stores').then(m => ({ default: m.StoresPage })));
const StoreDetailPage = lazy(() => import('./pages/stores').then(m => ({ default: m.StoreDetailPage })));
const StoreSettingsPage = lazy(() => import('./pages/stores').then(m => ({ default: m.StoreSettingsPage })));

// Marketing Pages
const MarketingPage = lazy(() => import('./pages/marketing').then(m => ({ default: m.MarketingPage })));
const SubscribersPage = lazy(() => import('./pages/marketing').then(m => ({ default: m.SubscribersPage })));
const NewCampaignPage = lazy(() => import('./pages/marketing/email').then(m => ({ default: m.NewCampaignPage })));
const CampaignsListPage = lazy(() => import('./pages/marketing/email').then(m => ({ default: m.CampaignsListPage })));
const NewWhatsAppCampaignPage = lazy(() => import('./pages/marketing/whatsapp').then(m => ({ default: m.NewWhatsAppCampaignPage })));
const WhatsAppCampaignsPage = lazy(() => import('./pages/marketing/whatsapp').then(m => ({ default: m.WhatsAppCampaignsPage })));
const WhatsAppTemplatesPage = lazy(() => import('./pages/marketing/whatsapp/WhatsAppTemplatesPage').then(m => ({ default: m.default })));
const AutomationsPage = lazy(() => import('./pages/marketing/AutomationsPage').then(m => ({ default: m.default })));

// Instagram Pages
const InstagramAccountsPage = lazy(() => import('./pages/instagram').then(m => ({ default: m.InstagramAccountsPage })));
const InstagramDashboardPage = lazy(() => import('./pages/instagram').then(m => ({ default: m.InstagramDashboardPage })));
const InstagramInbox = lazy(() => import('./pages/instagram').then(m => ({ default: m.InstagramInbox })));

// Messenger Pages
const MessengerInbox = lazy(() => import('./pages/messenger').then(m => ({ default: m.MessengerInbox })));
const MessengerAccounts = lazy(() => import('./pages/messenger').then(m => ({ default: m.MessengerAccounts })));

// WhatsApp Pages
const WebhookDiagnosticsPage = lazy(() => import('./pages/whatsapp').then(m => ({ default: m.WebhookDiagnosticsPage })));
const WhatsAppChatPage = lazy(() => import('./pages/whatsapp').then(m => ({ default: m.WhatsAppChatPage })));

// Protected Route wrapper
const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated } = useAuthStore();
  
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  
  return <>{children}</>;
};

// Inner app content
const AppContent: React.FC = () => {
  const { isAuthenticated, token } = useAuthStore();
  const { setAccounts } = useAccountStore();
  const [isInitializing, setIsInitializing] = useState(true);

  useEffect(() => {
    const initialize = async () => {
      // Ensure axios has the Authorization header from persisted token
      if (token) {
        setAuthToken(token as string);
      }

      if (isAuthenticated && token) {
        try {
          const response = await whatsappService.getAccounts();
          setAccounts(response.results);
        } catch (error) {
          logger.error('Error loading accounts:', error);
        }
      }
      setIsInitializing(false);
    };
    initialize();
  }, [isAuthenticated, token, setAccounts]);

  if (isInitializing) {
    return <FullPageLoading />;
  }

  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={
        isAuthenticated ? <Navigate to="/" replace /> : (
          <Suspense fallback={<FullPageLoading />}>
            <LoginPage />
          </Suspense>
        )
      } />

      {/* Protected routes */}
      <Route path="/" element={
        <ProtectedRoute>
          <MainLayout />
        </ProtectedRoute>
      }>
        <Route index element={<Suspense fallback={<FullPageLoading />}><DashboardPage /></Suspense>} />
        <Route path="accounts" element={<Suspense fallback={<FullPageLoading />}><AccountsPage /></Suspense>} />
        <Route path="accounts/new" element={<Suspense fallback={<FullPageLoading />}><AccountFormPage /></Suspense>} />
        <Route path="accounts/:id" element={<Suspense fallback={<FullPageLoading />}><AccountDetailPage /></Suspense>} />
        <Route path="accounts/:id/edit" element={<Suspense fallback={<FullPageLoading />}><AccountFormPage /></Suspense>} />
        <Route path="messages" element={<Suspense fallback={<FullPageLoading />}><MessagesPage /></Suspense>} />
        <Route path="conversations" element={<Suspense fallback={<FullPageLoading />}><ConversationsPage /></Suspense>} />
        {/* Store-scoped routes for orders and payments */}
        
        {/* AI Agents Routes (Langchain) */}
        <Route path="agents" element={<Suspense fallback={<FullPageLoading />}><AgentsPage /></Suspense>} />
        <Route path="agents/new" element={<Suspense fallback={<FullPageLoading />}><AgentCreatePage /></Suspense>} />
        <Route path="agents/:id" element={<Suspense fallback={<FullPageLoading />}><AgentDetailPage /></Suspense>} />
        <Route path="agents/:id/test" element={<Suspense fallback={<FullPageLoading />}><AgentTestPage /></Suspense>} />
        <Route path="agents/:id/conversations" element={<Suspense fallback={<FullPageLoading />}><AgentDetailPage /></Suspense>} />
        
        {/* Unified Orchestrator Test */}
        <Route path="agents/test/orchestrator" element={<Suspense fallback={<FullPageLoading />}><UnifiedOrchestratorTest /></Suspense>} />
        
        {/* Settings */}
        <Route path="settings" element={<Suspense fallback={<FullPageLoading />}><SettingsPage /></Suspense>} />
        
        {/* Automation Routes */}
        <Route path="automation/companies" element={<Suspense fallback={<FullPageLoading />}><CompanyProfilesPage /></Suspense>} />
        <Route path="automation/companies/new" element={<Suspense fallback={<FullPageLoading />}><CompanyProfileDetailPage /></Suspense>} />
        <Route path="automation/companies/:id" element={<Suspense fallback={<FullPageLoading />}><CompanyProfileDetailPage /></Suspense>} />
        <Route path="automation/companies/:companyId/messages" element={<Suspense fallback={<FullPageLoading />}><AutoMessagesPage /></Suspense>} />
        <Route path="automation/sessions" element={<Suspense fallback={<FullPageLoading />}><CustomerSessionsPage /></Suspense>} />
        <Route path="automation/logs" element={<Suspense fallback={<FullPageLoading />}><AutomationLogsPage /></Suspense>} />
        <Route path="automation/scheduled" element={<Suspense fallback={<FullPageLoading />}><ScheduledMessagesPage /></Suspense>} />
        <Route path="automation/reports" element={<Suspense fallback={<FullPageLoading />}><ReportsPage /></Suspense>} />

        {/* Intent Detection Routes (Novo Sistema) */}
        <Route path="automation/intents" element={<Suspense fallback={<FullPageLoading />}><IntentStatsPage /></Suspense>} />
        <Route path="automation/intents/stats" element={<Suspense fallback={<FullPageLoading />}><IntentStatsPage /></Suspense>} />
        <Route path="automation/intents/logs" element={<Suspense fallback={<FullPageLoading />}><IntentLogsPage /></Suspense>} />
        
        {/* Analytics/Reports Routes */}
        <Route path="analytics" element={<Suspense fallback={<FullPageLoading />}><AnalyticsPage /></Suspense>} />
        <Route path="reports" element={<Suspense fallback={<FullPageLoading />}><AnalyticsPage /></Suspense>} />
        
        {/* Stores Routes */}
        <Route path="stores" element={<Suspense fallback={<FullPageLoading />}><StoresPage /></Suspense>} />
        <Route path="stores/:storeId" element={<Suspense fallback={<FullPageLoading />}><StoreDetailPage /></Suspense>} />
        <Route path="stores/:storeId/products" element={<Suspense fallback={<FullPageLoading />}><ProductsPage /></Suspense>} />
        <Route path="stores/:storeId/orders" element={<Suspense fallback={<FullPageLoading />}><OrdersPage /></Suspense>} />
        <Route path="stores/:storeId/orders/:id" element={<Suspense fallback={<FullPageLoading />}><OrderDetailPage /></Suspense>} />
        <Route path="stores/:storeId/coupons" element={<Suspense fallback={<FullPageLoading />}><CouponsPage /></Suspense>} />
        <Route path="stores/:storeId/analytics" element={<Suspense fallback={<FullPageLoading />}><AnalyticsPage /></Suspense>} />
        <Route path="stores/:storeId/payments" element={<Suspense fallback={<FullPageLoading />}><PaymentsPage /></Suspense>} />
        <Route path="stores/:storeId/settings" element={<Suspense fallback={<FullPageLoading />}><StoreSettingsPage /></Suspense>} />
        
        {/* Marketing Routes */}
        <Route path="marketing" element={<Suspense fallback={<FullPageLoading />}><MarketingPage /></Suspense>} />
        <Route path="marketing/subscribers" element={<Suspense fallback={<FullPageLoading />}><SubscribersPage /></Suspense>} />
        <Route path="marketing/automations" element={<Suspense fallback={<FullPageLoading />}><AutomationsPage /></Suspense>} />
        <Route path="marketing/email" element={<Suspense fallback={<FullPageLoading />}><CampaignsListPage /></Suspense>} />
        <Route path="marketing/email/campaigns" element={<Suspense fallback={<FullPageLoading />}><CampaignsListPage /></Suspense>} />
        <Route path="marketing/email/new" element={<Suspense fallback={<FullPageLoading />}><NewCampaignPage /></Suspense>} />
        <Route path="marketing/email/templates" element={<Suspense fallback={<FullPageLoading />}><MarketingPage /></Suspense>} />
        <Route path="marketing/whatsapp" element={<Suspense fallback={<FullPageLoading />}><WhatsAppCampaignsPage /></Suspense>} />
        <Route path="marketing/whatsapp/new" element={<Suspense fallback={<FullPageLoading />}><NewWhatsAppCampaignPage /></Suspense>} />
        <Route path="marketing/whatsapp/templates" element={<Suspense fallback={<FullPageLoading />}><WhatsAppTemplatesPage /></Suspense>} />
        
        {/* Instagram Routes */}
        <Route path="instagram" element={<Suspense fallback={<FullPageLoading />}><InstagramAccountsPage /></Suspense>} />
        <Route path="instagram/accounts" element={<Suspense fallback={<FullPageLoading />}><InstagramAccountsPage /></Suspense>} />
        <Route path="instagram/:accountId" element={<Suspense fallback={<FullPageLoading />}><InstagramDashboardPage /></Suspense>} />
        <Route path="instagram/inbox" element={<Suspense fallback={<FullPageLoading />}><InstagramInbox /></Suspense>} />
        
        {/* Messenger Routes */}
        <Route path="messenger" element={<Suspense fallback={<FullPageLoading />}><MessengerInbox /></Suspense>} />
        <Route path="messenger/inbox" element={<Suspense fallback={<FullPageLoading />}><MessengerInbox /></Suspense>} />
        <Route path="messenger/accounts" element={<Suspense fallback={<FullPageLoading />}><MessengerAccounts /></Suspense>} />
        
        {/* WhatsApp Routes */}
        <Route path="whatsapp/chat" element={<Suspense fallback={<FullPageLoading />}><WhatsAppChatPage /></Suspense>} />
        <Route path="whatsapp/diagnostics" element={<Suspense fallback={<FullPageLoading />}><WebhookDiagnosticsPage /></Suspense>} />
      </Route>

      {/* Catch all */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};

// Main App with WebSocket Providers (singleton)
const App: React.FC = () => {
  const { isAuthenticated } = useAuthStore();
  
  if (!isAuthenticated) {
    return <AppContent />;
  }
  
  return (
    <WebSocketProvider>
      <WhatsAppWsProvider dashboardMode={true}>
        <AppContent />
      </WhatsAppWsProvider>
    </WebSocketProvider>
  );
};

export default App;
