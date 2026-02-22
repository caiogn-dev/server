// =============================================================================
// CORE SERVICES
// =============================================================================

export { default as api, getErrorMessage } from './api';
export { setAuthToken } from './api';
export { authService } from './auth';
export { dashboardService } from './dashboard';
export { default as logger } from './logger';

// =============================================================================
// STORE API (Multi-tenant) - PRIMARY API
// =============================================================================

export { 
  storeApi, 
  useStoreApi,
  getActiveStoreSlug,
  type Product,
  type Category,
  type Order,
  type OrderItem,
  type OrderStatus,
  type PaymentStatus,
  type DeliveryMethod,
  type DeliveryAddress,
  type Coupon,
  type DeliveryZone,
  type DashboardStats,
  type ApiParams,
  type PaginatedResponse,
  type ProductType,
  type CustomField,
} from './storeApi';

// =============================================================================
// COMMUNICATION SERVICES
// =============================================================================

export { whatsappService } from './whatsapp';
export { conversationsService } from './conversations';
export { notificationsService } from './notifications';
export {
  notificationWS,
  chatWS,
  dashboardWS,
  getWebSocketUrl,
  initializeWebSockets,
  disconnectWebSockets,
} from './websocket';

// Realtime service with fallback (WebSocket → SSE → Polling)
export {
  RealtimeConnection,
  createRealtimeConnection,
  getGlobalConnection,
  setGlobalConnection,
  detectTransportCapabilities,
  isTransportSupported,
  getWebSocketUrl as getRealtimeUrl,
} from './realtime';
export type { 
  TransportType, 
  ConnectionStatus,
  TransportCapabilities,
} from './realtime';

// =============================================================================
// BUSINESS SERVICES
// =============================================================================

export { ordersService } from './orders';
export { paymentsService } from './payments';
export { couponsService } from './coupons';
export { deliveryService } from './delivery';
export { productsService } from './products';

// =============================================================================
// AUTOMATION & AI AGENTS
// =============================================================================

export { default as agentsService } from './agents';
export { auditService } from './audit';
export {
  companyProfileApi,
  autoMessageApi,
  customerSessionApi,
  automationLogApi,
  eventTypeLabels,
  businessTypeLabels,
  sessionStatusLabels,
  messageVariables,
  intentTypeLabels,
} from './automation';
export {
  scheduledMessagesService,
  reportSchedulesService,
  generatedReportsService,
} from './scheduling';
export { exportService } from './export';

// Intent Detection & Automation Dashboard
export {
  intentService,
  automationDashboardService,
} from './intents';

// =============================================================================
// CATALOG SERVICE
// =============================================================================

export { catalogService } from './catalogService';

// =============================================================================
// MESSENGER PLATFORM
// =============================================================================

export { default as messengerService } from './messenger';
export type {
  MessengerAccount,
  MessengerConversation,
  MessengerMessage,
  MessengerProfile,
  BroadcastMessage,
  SponsoredMessage,
} from './messenger';

// =============================================================================
// INSTAGRAM PLATFORM (Complete - Posts, Stories, Reels, Shopping, Live, Direct)
// =============================================================================

export {
  instagramAccountApi,
  instagramMediaApi,
  instagramShoppingApi,
  instagramLiveApi,
  instagramScheduledPostApi,
  instagramDirectApi,
} from './instagram';

export type {
  InstagramAccount,
  InstagramMedia,
  InstagramInsight,
  InstagramCatalog,
  InstagramProduct,
  InstagramLive,
  InstagramScheduledPost,
} from './instagram';

// =============================================================================
// HANDOVER PROTOCOL (Bot ↔ Human Transfer)
// =============================================================================

export { default as handoverService } from './handover';
export type {
  HandoverStatus,
  HandoverResponse,
  HandoverLog,
  HandoverRequest,
} from './handover';

// =============================================================================
// CONVERSIONS API (Facebook, Google, TikTok Pixel Events)
// =============================================================================

export { default as conversionsService } from './conversions';
