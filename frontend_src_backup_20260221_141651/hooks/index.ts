// Theme hook
export { useTheme } from './useTheme';

// Toast hook
export { useToast } from './useToast';

// Utility hooks
export { useDebounce, useDebouncedCallback } from './useDebounce';
export { useLocalStorage } from './useLocalStorage';
export { useFetch } from './useFetch';
export type { UseFetchResult } from './useFetch';

// WebSocket hooks
export {
  useNotificationWebSocket,
  useDashboardWebSocket,
  useChatWebSocket,
} from './useWebSocket';
export { useAutomationWS } from './useAutomationWS';
export { useOrdersWebSocket } from './useOrdersWebSocket';
export { useWhatsAppWS } from './useWhatsAppWS';
export type {
  WhatsAppMessage,
  WhatsAppContact,
  WhatsAppConversation,
  MessageReceivedEvent,
  MessageSentEvent,
  StatusUpdatedEvent,
  TypingEvent,
  ConversationUpdatedEvent,
  ErrorEvent,
} from './useWhatsAppWS';

// Notification sound hook
export { useNotificationSound } from './useNotificationSound';

// Store context hook
export { 
  useStore, 
  getStoreId, 
  getStoreSlug, 
  getStoreIdWithFallback 
} from './useStore';
export type { UseStoreReturn } from './useStore';

// =============================================================================
// MESSENGER PLATFORM
// =============================================================================

export { default as useMessenger } from './useMessenger';
export { default as useMessengerWS } from './useMessengerWS';

// =============================================================================
// INSTAGRAM PLATFORM
// =============================================================================

export { default as useInstagram } from './useInstagram';

// =============================================================================
// HANDOVER PROTOCOL
// =============================================================================

export { default as useHandover } from './useHandover';
