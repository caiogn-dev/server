/**
 * Hook for real-time WhatsApp message updates via WebSocket
 * 
 * Connects to: ws/whatsapp/{accountId}/ or ws/whatsapp/dashboard/
 * 
 * Events received:
 * - message_received: New inbound message
 * - message_sent: Outbound message confirmation
 * - status_updated: Message status change (sent, delivered, read)
 * - typing: Typing indicator
 * - conversation_updated: Conversation changes
 * - error: API errors
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import { useAuthStore } from '../stores/authStore';

// Types
export interface WhatsAppMessage {
  id: string;
  whatsapp_message_id: string;
  direction: 'inbound' | 'outbound';
  message_type: string;
  status: 'pending' | 'sent' | 'delivered' | 'read' | 'failed';
  from_number: string;
  to_number: string;
  text_body: string;
  content: Record<string, unknown>;
  media_id?: string;
  media_url?: string;
  created_at: string;
  delivered_at?: string;
  read_at?: string;
}

export interface WhatsAppContact {
  wa_id: string;
  name: string;
}

export interface WhatsAppConversation {
  id: string;
  phone_number: string;
  contact_name: string;
  status: string;
  mode: string;
  created_at: string;
}

export interface MessageReceivedEvent {
  type: 'message_received';
  message: WhatsAppMessage;
  conversation_id?: string;
  contact?: WhatsAppContact;
}

export interface MessageSentEvent {
  type: 'message_sent';
  message: WhatsAppMessage;
  conversation_id?: string;
}

export interface StatusUpdatedEvent {
  type: 'status_updated';
  message_id: string;
  whatsapp_message_id?: string;
  status: 'sent' | 'delivered' | 'read' | 'failed';
  timestamp: string;
}

export interface TypingEvent {
  type: 'typing';
  conversation_id: string;
  is_typing: boolean;
}

export interface ConversationUpdatedEvent {
  type: 'conversation_updated';
  conversation: WhatsAppConversation;
}

export interface ErrorEvent {
  type: 'error';
  error_code: string;
  error_message: string;
  message_id?: string;
}

type WhatsAppEvent = 
  | MessageReceivedEvent 
  | MessageSentEvent 
  | StatusUpdatedEvent 
  | TypingEvent 
  | ConversationUpdatedEvent 
  | ErrorEvent
  | { type: 'pong' }
  | { type: 'connection_established'; account_id?: string; accounts?: string[]; message?: string }
  | { type: 'subscribed'; conversation_id?: string }
  | { type: 'unsubscribed'; conversation_id?: string }
  | { type: 'read_receipt_sent'; message_ids?: string[] };

interface UseWhatsAppWSOptions {
  accountId?: string;
  dashboardMode?: boolean;
  onMessageReceived?: (event: MessageReceivedEvent) => void;
  onMessageSent?: (event: MessageSentEvent) => void;
  onStatusUpdated?: (event: StatusUpdatedEvent) => void;
  onTyping?: (event: TypingEvent) => void;
  onConversationUpdated?: (event: ConversationUpdatedEvent) => void;
  onError?: (event: ErrorEvent) => void;
  onConnectionChange?: (connected: boolean) => void;
  enabled?: boolean;
}

interface UseWhatsAppWSReturn {
  isConnected: boolean;
  connectionError: string | null;
  subscribeToConversation: (conversationId: string) => void;
  unsubscribeFromConversation: (conversationId: string) => void;
  sendTypingIndicator: (conversationId: string, isTyping: boolean) => void;
}

export function useWhatsAppWS(options: UseWhatsAppWSOptions = {}): UseWhatsAppWSReturn {
  const { token } = useAuthStore();
  const ws = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<number | undefined>(undefined);
  const pingTimer = useRef<number | undefined>(undefined);
  const attempts = useRef(0);
  const isConnecting = useRef(false);
  const opts = useRef(options);
  opts.current = options;

  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const {
    accountId,
    dashboardMode = false,
    enabled = true,
  } = options;

  // Build WebSocket URL
  const getWsUrl = useCallback(() => {
    if (!token) return null;
    
    let host = import.meta.env.VITE_WS_HOST;
    if (!host) {
      const api = import.meta.env.VITE_API_URL;
      host = api ? new URL(api).host : window.location.host;
    }
    
    const proto = host.includes('railway') || host.includes('vercel') || location.protocol === 'https:' ? 'wss' : 'ws';
    
    if (dashboardMode) {
      return `${proto}://${host}/ws/whatsapp/dashboard/?token=${token}`;
    }
    
    if (!accountId) return null;
    return `${proto}://${host}/ws/whatsapp/${accountId}/?token=${token}`;
  }, [token, accountId, dashboardMode]);

  // Handle incoming messages
  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data) as WhatsAppEvent & { type: string };
      
      if (data.type === 'pong') return;
      if (data.type === 'connection_established') {
        console.log('[WhatsApp WS] Connection confirmed:', data);
        return;
      }
      if (data.type === 'subscribed' || data.type === 'unsubscribed') {
        console.log(`[WhatsApp WS] ${data.type}:`, data);
        return;
      }
      if (data.type === 'read_receipt_sent') {
        console.log('[WhatsApp WS] Read receipt sent:', data);
        return;
      }

      console.log('[WhatsApp WS] Event received:', data.type, JSON.stringify(data, null, 2));

      switch (data.type) {
        case 'message_received':
          console.log('[WhatsApp WS] Calling onMessageReceived callback');
          opts.current.onMessageReceived?.(data as MessageReceivedEvent);
          break;
        case 'message_sent':
          console.log('[WhatsApp WS] Calling onMessageSent callback');
          opts.current.onMessageSent?.(data as MessageSentEvent);
          break;
        case 'status_updated':
          console.log('[WhatsApp WS] Calling onStatusUpdated callback');
          opts.current.onStatusUpdated?.(data as StatusUpdatedEvent);
          break;
        case 'typing':
          opts.current.onTyping?.(data as TypingEvent);
          break;
        case 'conversation_updated':
          console.log('[WhatsApp WS] Calling onConversationUpdated callback');
          opts.current.onConversationUpdated?.(data as ConversationUpdatedEvent);
          break;
        case 'error':
          console.error('[WhatsApp WS] Error event:', data);
          opts.current.onError?.(data as ErrorEvent);
          break;
        default: {
          // Handle unknown event types
          const unknownData = data as { type: string };
          console.log('[WhatsApp WS] Unknown event type:', unknownData.type, data);
        }
      }
    } catch (err) {
      console.error('[WhatsApp WS] Parse error:', err, 'Raw data:', event.data);
    }
  }, []);

  // Connect to WebSocket
  const connect = useCallback(() => {
    const url = getWsUrl();
    if (!url || !enabled) {
      console.log('[WhatsApp WS] Skipping connection (no URL or disabled)');
      return;
    }

    if (isConnecting.current) {
      console.log('[WhatsApp WS] Already connecting');
      return;
    }

    if (ws.current?.readyState === WebSocket.OPEN) {
      console.log('[WhatsApp WS] Already connected');
      return;
    }

    // Close existing connection
    if (ws.current) {
      ws.current.onclose = null;
      ws.current.close();
      ws.current = null;
    }

    isConnecting.current = true;
    console.log('[WhatsApp WS] Connecting to:', url.replace(/token=.*/, 'token=***'));

    try {
      const socket = new WebSocket(url);
      ws.current = socket;

      socket.onopen = () => {
        console.log('[WhatsApp WS] Connected ✓');
        isConnecting.current = false;
        setIsConnected(true);
        setConnectionError(null);
        attempts.current = 0;
        opts.current.onConnectionChange?.(true);

        // Ping every 25s to keep connection alive
        if (pingTimer.current) window.clearInterval(pingTimer.current);
        pingTimer.current = window.setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'ping' }));
          }
        }, 25000);
      };

      socket.onmessage = handleMessage;

      socket.onclose = (e) => {
        console.log('[WhatsApp WS] Closed:', e.code, e.reason);
        isConnecting.current = false;
        setIsConnected(false);
        opts.current.onConnectionChange?.(false);

        if (pingTimer.current) {
          window.clearInterval(pingTimer.current);
          pingTimer.current = undefined;
        }

        // Reconnect on abnormal close
        if (e.code !== 1000 && attempts.current < 10 && enabled) {
          const delay = Math.min(1000 * Math.pow(1.5, attempts.current), 30000);
          console.log(`[WhatsApp WS] Reconnecting in ${Math.round(delay)}ms (attempt ${attempts.current + 1}/10)`);
          setConnectionError('Reconectando...');

          reconnectTimer.current = window.setTimeout(() => {
            attempts.current++;
            connect();
          }, delay);
        } else if (attempts.current >= 10) {
          setConnectionError('Conexão perdida. Atualize a página.');
        }
      };

      socket.onerror = (e) => {
        console.error('[WhatsApp WS] Error:', e);
        isConnecting.current = false;
      };
    } catch (err) {
      console.error('[WhatsApp WS] Connection error:', err);
      isConnecting.current = false;
    }
  }, [getWsUrl, enabled, handleMessage]);

  // Subscribe to a specific conversation (for typing indicators)
  const subscribeToConversation = useCallback((conversationId: string) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({
        type: 'subscribe_conversation',
        conversation_id: conversationId,
      }));
    }
  }, []);

  // Unsubscribe from a conversation
  const unsubscribeFromConversation = useCallback((conversationId: string) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({
        type: 'unsubscribe_conversation',
        conversation_id: conversationId,
      }));
    }
  }, []);

  // Send typing indicator
  const sendTypingIndicator = useCallback((conversationId: string, isTyping: boolean) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({
        type: 'typing',
        conversation_id: conversationId,
        is_typing: isTyping,
      }));
    }
  }, []);

  // Connect on mount and when dependencies change
  useEffect(() => {
    if (enabled && (accountId || dashboardMode)) {
      connect();
    }

    // Reconnect on tab visibility change
    const onVisible = () => {
      if (document.visibilityState === 'visible' && enabled) {
        if (!ws.current || ws.current.readyState !== WebSocket.OPEN) {
          console.log('[WhatsApp WS] Tab visible, reconnecting...');
          attempts.current = 0;
          connect();
        }
      }
    };
    document.addEventListener('visibilitychange', onVisible);

    return () => {
      document.removeEventListener('visibilitychange', onVisible);
      if (reconnectTimer.current) window.clearTimeout(reconnectTimer.current);
      if (pingTimer.current) window.clearInterval(pingTimer.current);
      if (ws.current) {
        ws.current.onclose = null;
        ws.current.close(1000);
        ws.current = null;
      }
    };
  }, [connect, enabled, accountId, dashboardMode]);

  return {
    isConnected,
    connectionError,
    subscribeToConversation,
    unsubscribeFromConversation,
    sendTypingIndicator,
  };
}

export default useWhatsAppWS;
