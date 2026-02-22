/**
 * WebSocket hooks - DEPRECATED
 * Use useOrdersWebSocket or useWS from WebSocketContext instead
 */
import { useCallback } from 'react';
import { useWS } from '../context/WebSocketContext';

// Re-export useWS for backwards compatibility
export { useWS };

// Stub hooks for backwards compatibility
export const useNotificationWebSocket = () => {
  const { isConnected, on } = useWS();
  return {
    subscribe: on,
    isConnected,
  };
};

export const useDashboardWebSocket = () => {
  const { isConnected, on } = useWS();
  return {
    subscribe: on,
    isConnected,
  };
};

export const useChatWebSocket = (_conversationId: string | null) => {
  const { isConnected } = useWS();
  return {
    sendMessage: useCallback(() => {}, []),
    subscribe: useCallback(() => () => {}, []),
    isConnected,
  };
};
