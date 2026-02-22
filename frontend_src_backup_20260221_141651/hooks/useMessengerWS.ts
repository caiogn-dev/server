import { useEffect, useRef, useState, useCallback } from 'react';
import { getWebSocketUrl } from '../services/websocket';

interface MessengerMessageEvent {
  type: 'message';
  conversation_id: string;
  message: {
    id: string;
    sender_id: string;
    sender_name: string;
    content: string;
    message_type: string;
    created_at: string;
  };
}

interface MessengerConversationEvent {
  type: 'conversation_update';
  conversation_id: string;
  data: {
    last_message?: string;
    last_message_at?: string;
    unread_count: number;
  };
}

type MessengerWSEvent = MessengerMessageEvent | MessengerConversationEvent;

interface UseMessengerWSOptions {
  accountId?: string;
  onMessage?: (event: MessengerMessageEvent) => void;
  onConversationUpdate?: (event: MessengerConversationEvent) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Event) => void;
}

export const useMessengerWS = (options: UseMessengerWSOptions) => {
  const { accountId, onMessage, onConversationUpdate, onConnect, onDisconnect, onError } = options;
  
  // WebSocket reference
  const wsRef = useRef<WebSocket | null>(null);
  
  // Connection state
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  
  // Reconnection logic refs
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const lastConnectTimeRef = useRef(0);
  const intentionalCloseRef = useRef(false);
  
  // Constants for reconnection
  const MAX_RECONNECT_ATTEMPTS = 5;
  const RECONNECT_DELAY_BASE = 1000; // 1 second
  const MIN_CONNECT_INTERVAL = 5000; // 5 seconds minimum between connection attempts
  
  // Clear any pending reconnect timeout
  const clearReconnectTimeout = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);
  
  // Calculate reconnect delay with exponential backoff
  const getReconnectDelay = useCallback(() => {
    const delay = Math.min(
      RECONNECT_DELAY_BASE * Math.pow(2, reconnectAttemptsRef.current),
      30000 // Max 30 seconds
    );
    return delay;
  }, []);
  
  // Connect to WebSocket
  const connect = useCallback(() => {
    // Prevent multiple simultaneous connection attempts
    if (isConnecting || wsRef.current?.readyState === WebSocket.CONNECTING) {
      console.log('[MessengerWS] Already connecting, skipping...');
      return;
    }
    
    // Prevent connection if already connected
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('[MessengerWS] Already connected, skipping...');
      return;
    }
    
    // Rate limiting: minimum interval between connections
    const now = Date.now();
    const timeSinceLastConnect = now - lastConnectTimeRef.current;
    if (timeSinceLastConnect < MIN_CONNECT_INTERVAL && reconnectAttemptsRef.current > 0) {
      console.log(`[MessengerWS] Rate limited. Waiting ${MIN_CONNECT_INTERVAL - timeSinceLastConnect}ms...`);
      clearReconnectTimeout();
      reconnectTimeoutRef.current = setTimeout(
        connect,
        MIN_CONNECT_INTERVAL - timeSinceLastConnect
      );
      return;
    }
    
    setIsConnecting(true);
    lastConnectTimeRef.current = now;
    intentionalCloseRef.current = false;
    
    try {
      const wsUrl = getWebSocketUrl(`/ws/messenger/${accountId || 'all'}/`);
      console.log('[MessengerWS] Connecting to:', wsUrl);
      
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      
      ws.onopen = () => {
        console.log('[MessengerWS] Connected');
        setIsConnected(true);
        setIsConnecting(false);
        reconnectAttemptsRef.current = 0;
        onConnect?.();
      };
      
      ws.onmessage = (event) => {
        try {
          const data: MessengerWSEvent = JSON.parse(event.data);
          
          switch (data.type) {
            case 'message':
              onMessage?.(data);
              break;
            case 'conversation_update':
              onConversationUpdate?.(data);
              break;
            default:
              console.log('[MessengerWS] Unknown event type:', data);
          }
        } catch (error) {
          console.error('[MessengerWS] Error parsing message:', error);
        }
      };
      
      ws.onclose = (event) => {
        console.log('[MessengerWS] Disconnected:', event.code, event.reason);
        setIsConnected(false);
        setIsConnecting(false);
        wsRef.current = null;
        onDisconnect?.();
        
        // Only reconnect if not intentionally closed and within retry limit
        if (!intentionalCloseRef.current && reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttemptsRef.current++;
          const delay = getReconnectDelay();
          console.log(`[MessengerWS] Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current})`);
          
          clearReconnectTimeout();
          reconnectTimeoutRef.current = setTimeout(connect, delay);
        } else if (reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
          console.error('[MessengerWS] Max reconnection attempts reached');
        }
      };
      
      ws.onerror = (error) => {
        console.error('[MessengerWS] Error:', error);
        setIsConnecting(false);
        onError?.(error);
      };
      
    } catch (error) {
      console.error('[MessengerWS] Connection error:', error);
      setIsConnecting(false);
      wsRef.current = null;
    }
  }, [accountId, onMessage, onConversationUpdate, onConnect, onDisconnect, onError, getReconnectDelay]);
  
  // Disconnect WebSocket
  const disconnect = useCallback(() => {
    intentionalCloseRef.current = true;
    clearReconnectTimeout();
    
    if (wsRef.current) {
      if (wsRef.current.readyState === WebSocket.OPEN ||
          wsRef.current.readyState === WebSocket.CONNECTING) {
        wsRef.current.close();
      }
      wsRef.current = null;
    }
    
    setIsConnected(false);
    setIsConnecting(false);
    reconnectAttemptsRef.current = 0;
  }, [clearReconnectTimeout]);
  
  // Send message through WebSocket
  const sendMessage = useCallback((message: Record<string, any>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
      return true;
    }
    console.warn('[MessengerWS] Cannot send message, not connected');
    return false;
  }, []);
  
  // Mark conversation as typing
  const sendTyping = useCallback((conversationId: string, isTyping: boolean) => {
    return sendMessage({
      type: 'typing',
      conversation_id: conversationId,
      is_typing: isTyping,
    });
  }, [sendMessage]);
  
  // Mark messages as read
  const markAsRead = useCallback((conversationId: string) => {
    return sendMessage({
      type: 'mark_read',
      conversation_id: conversationId,
    });
  }, [sendMessage]);
  
  // Connect on mount, disconnect on unmount
  useEffect(() => {
    connect();
    
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);
  
  // Reconnect when accountId changes
  useEffect(() => {
    // Only reconnect if we were previously connected
    if (isConnected || wsRef.current) {
      disconnect();
      connect();
    }
  }, [accountId]);
  
  return {
    isConnected,
    isConnecting,
    connect,
    disconnect,
    sendMessage,
    sendTyping,
    markAsRead,
  };
};

export default useMessengerWS;
