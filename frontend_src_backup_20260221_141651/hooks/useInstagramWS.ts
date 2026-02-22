/**
 * Hook for real-time Instagram DM updates via WebSocket
 * 
 * Connects to: ws/instagram/{accountId}/
 * 
 * Events received:
 * - message_received: New inbound message
 * - message_sent: Outbound message confirmation
 * - message_seen: Message read status
 * - typing: Typing indicator
 * - conversation_updated: Conversation changes
 * - story_mention: Story mention notification
 * - story_reply: Story reply notification
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import { useAuthStore } from '../stores/authStore';

// Types
export interface InstagramMessage {
  id: string;
  instagram_message_id: string;
  direction: 'inbound' | 'outbound';
  message_type: string;
  status: 'pending' | 'sent' | 'delivered' | 'seen' | 'failed';
  text_content: string;
  media_url?: string;
  media_type?: string;
  created_at: string;
  sent_at?: string;
  seen_at?: string;
}

export interface InstagramSender {
  id: string;
  username: string;
  name: string;
}

export interface InstagramConversation {
  id: string;
  participant_id: string;
  participant_username: string;
  participant_name: string;
  participant_profile_pic: string;
  last_message_at: string;
  last_message_preview: string;
  unread_count: number;
  status: string;
}

export interface MessageReceivedEvent {
  type: 'message_received';
  message: InstagramMessage;
  conversation: InstagramConversation;
  sender: InstagramSender;
}

export interface MessageSentEvent {
  type: 'message_sent';
  message: InstagramMessage;
  conversation_id: string;
}

export interface MessageSeenEvent {
  type: 'message_seen';
  message_id: string;
  conversation_id: string;
  seen_at: string;
}

export interface TypingEvent {
  type: 'typing';
  conversation_id: string;
  user_id: string;
  is_typing: boolean;
}

export interface ConversationUpdatedEvent {
  type: 'conversation_updated';
  conversation: InstagramConversation;
}

export interface StoryMentionEvent {
  type: 'story_mention';
  conversation: InstagramConversation;
  story_url: string;
  sender: InstagramSender;
}

export interface StoryReplyEvent {
  type: 'story_reply';
  message: InstagramMessage;
  conversation: InstagramConversation;
  story_url: string;
  sender: InstagramSender;
}

export type InstagramWSEvent =
  | MessageReceivedEvent
  | MessageSentEvent
  | MessageSeenEvent
  | TypingEvent
  | ConversationUpdatedEvent
  | StoryMentionEvent
  | StoryReplyEvent
  | { type: 'connection_established'; account_id: string; message: string }
  | { type: 'pong' }
  | { type: 'subscribed'; conversation_id: string }
  | { type: 'unsubscribed'; conversation_id: string }
  | { type: 'error'; message: string };

export interface UseInstagramWSOptions {
  accountId: string;
  onMessageReceived?: (event: MessageReceivedEvent) => void;
  onMessageSent?: (event: MessageSentEvent) => void;
  onMessageSeen?: (event: MessageSeenEvent) => void;
  onTyping?: (event: TypingEvent) => void;
  onConversationUpdated?: (event: ConversationUpdatedEvent) => void;
  onStoryMention?: (event: StoryMentionEvent) => void;
  onStoryReply?: (event: StoryReplyEvent) => void;
  onConnected?: () => void;
  onDisconnected?: () => void;
  onError?: (error: string) => void;
  autoReconnect?: boolean;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
}

export interface UseInstagramWSReturn {
  isConnected: boolean;
  isConnecting: boolean;
  error: string | null;
  subscribeToConversation: (conversationId: string) => void;
  unsubscribeFromConversation: (conversationId: string) => void;
  startTyping: (conversationId: string) => void;
  stopTyping: (conversationId: string) => void;
  reconnect: () => void;
  disconnect: () => void;
}

export function useInstagramWS(options: UseInstagramWSOptions): UseInstagramWSReturn {
  const {
    accountId,
    onMessageReceived,
    onMessageSent,
    onMessageSeen,
    onTyping,
    onConversationUpdated,
    onStoryMention,
    onStoryReply,
    onConnected,
    onDisconnected,
    onError,
    autoReconnect = true,
    reconnectInterval = 3000,
    maxReconnectAttempts = 5,
  } = options;

  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { token } = useAuthStore();

  const getWebSocketUrl = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsBaseUrl = import.meta.env.VITE_WS_URL || `${protocol}//${window.location.host}`;
    const baseUrl = wsBaseUrl.replace(/^http/, 'ws');
    return `${baseUrl}/ws/instagram/${accountId}/?token=${token}`;
  }, [accountId, token]);

  const sendMessage = useCallback((data: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  const subscribeToConversation = useCallback((conversationId: string) => {
    sendMessage({ type: 'subscribe_conversation', conversation_id: conversationId });
  }, [sendMessage]);

  const unsubscribeFromConversation = useCallback((conversationId: string) => {
    sendMessage({ type: 'unsubscribe_conversation', conversation_id: conversationId });
  }, [sendMessage]);

  const startTyping = useCallback((conversationId: string) => {
    sendMessage({ type: 'typing_start', conversation_id: conversationId });
  }, [sendMessage]);

  const stopTyping = useCallback((conversationId: string) => {
    sendMessage({ type: 'typing_stop', conversation_id: conversationId });
  }, [sendMessage]);

  const startPingInterval = useCallback(() => {
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
    }
    pingIntervalRef.current = setInterval(() => {
      sendMessage({ type: 'ping' });
    }, 30000); // Ping every 30 seconds
  }, [sendMessage]);

  const connect = useCallback(() => {
    if (!accountId || !token) {
      return;
    }

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    setIsConnecting(true);
    setError(null);

    try {
      const url = getWebSocketUrl();
      wsRef.current = new WebSocket(url);

      wsRef.current.onopen = () => {
        setIsConnected(true);
        setIsConnecting(false);
        setError(null);
        reconnectAttemptsRef.current = 0;
        startPingInterval();
        onConnected?.();
      };

      wsRef.current.onclose = (event) => {
        setIsConnected(false);
        setIsConnecting(false);

        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
        }

        onDisconnected?.();

        // Attempt reconnection if not a normal close
        if (
          autoReconnect &&
          event.code !== 1000 &&
          reconnectAttemptsRef.current < maxReconnectAttempts
        ) {
          reconnectAttemptsRef.current++;
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, reconnectInterval * reconnectAttemptsRef.current);
        }
      };

      wsRef.current.onerror = () => {
        const errorMsg = 'WebSocket connection error';
        setError(errorMsg);
        onError?.(errorMsg);
      };

      wsRef.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as InstagramWSEvent;

          switch (data.type) {
            case 'message_received':
              onMessageReceived?.(data);
              break;
            case 'message_sent':
              onMessageSent?.(data);
              break;
            case 'message_seen':
              onMessageSeen?.(data);
              break;
            case 'typing':
              onTyping?.(data);
              break;
            case 'conversation_updated':
              onConversationUpdated?.(data);
              break;
            case 'story_mention':
              onStoryMention?.(data);
              break;
            case 'story_reply':
              onStoryReply?.(data);
              break;
            case 'connection_established':
              console.log('[Instagram WS] Connected:', data.message);
              break;
            case 'pong':
              // Keep-alive response
              break;
            case 'error':
              setError(data.message);
              onError?.(data.message);
              break;
          }
        } catch (err) {
          console.error('[Instagram WS] Failed to parse message:', err);
        }
      };
    } catch (err) {
      setIsConnecting(false);
      const errorMsg = 'Failed to create WebSocket connection';
      setError(errorMsg);
      onError?.(errorMsg);
    }
  }, [
    accountId,
    token,
    getWebSocketUrl,
    startPingInterval,
    autoReconnect,
    maxReconnectAttempts,
    reconnectInterval,
    onConnected,
    onDisconnected,
    onError,
    onMessageReceived,
    onMessageSent,
    onMessageSeen,
    onTyping,
    onConversationUpdated,
    onStoryMention,
    onStoryReply,
  ]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
    }
    if (wsRef.current) {
      wsRef.current.close(1000, 'User disconnected');
      wsRef.current = null;
    }
    setIsConnected(false);
    setIsConnecting(false);
  }, []);

  const reconnect = useCallback(() => {
    disconnect();
    reconnectAttemptsRef.current = 0;
    setTimeout(connect, 100);
  }, [connect, disconnect]);

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    if (accountId && token) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [accountId, token]); // eslint-disable-line react-hooks/exhaustive-deps

  return {
    isConnected,
    isConnecting,
    error,
    subscribeToConversation,
    unsubscribeFromConversation,
    startTyping,
    stopTyping,
    reconnect,
    disconnect,
  };
}

export default useInstagramWS;
