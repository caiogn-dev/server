/**
 * WhatsApp WebSocket Context - Singleton connection for real-time updates
 * 
 * Provides a single WebSocket connection for the entire application,
 * similar to WebSocketContext for orders but for WhatsApp.
 * 
 * Features:
 * - Auto-reconnect with exponential backoff
 * - Connection sharing across components
 * - Integration with chatStore for state management
 * - Dashboard mode for multi-account support
 */
import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';
import { useAuthStore } from '../stores/authStore';
import { useAccountStore } from '../stores/accountStore';
import { useChatStore } from '../stores/chatStore';
import { Message, Conversation } from '../types';
import toast from 'react-hot-toast';

// WebSocket event types
interface WsMessageReceived {
  type: 'message_received';
  message: Message;
  conversation_id?: string;
  contact?: { wa_id: string; name: string };
}

interface WsMessageSent {
  type: 'message_sent';
  message: Message;
  conversation_id?: string;
}

interface WsStatusUpdated {
  type: 'status_updated';
  message_id: string;
  whatsapp_message_id?: string;
  status: 'sent' | 'delivered' | 'read' | 'failed';
  timestamp: string;
}

interface WsTyping {
  type: 'typing';
  conversation_id: string;
  is_typing: boolean;
  user_id?: number;
}

interface WsConversationUpdated {
  type: 'conversation_updated';
  conversation: Conversation;
}

interface WsError {
  type: 'error';
  error_code: string;
  error_message: string;
  message_id?: string;
}

type WsEvent = 
  | WsMessageReceived 
  | WsMessageSent 
  | WsStatusUpdated 
  | WsTyping 
  | WsConversationUpdated 
  | WsError
  | { type: 'pong' }
  | { type: 'connection_established'; account_id?: string; accounts?: string[]; message?: string }
  | { type: 'subscribed'; conversation_id?: string }
  | { type: 'unsubscribed'; conversation_id?: string };

// Context interface
interface WhatsAppWsContextValue {
  isConnected: boolean;
  connectionError: string | null;
  subscribeToConversation: (conversationId: string) => void;
  unsubscribeFromConversation: (conversationId: string) => void;
  sendTypingIndicator: (conversationId: string, isTyping: boolean) => void;
  reconnect: () => void;
}

const WhatsAppWsContext = createContext<WhatsAppWsContextValue | null>(null);

// Hook to use the context
export function useWhatsAppWsContext() {
  const context = useContext(WhatsAppWsContext);
  if (!context) {
    throw new Error('useWhatsAppWsContext must be used within WhatsAppWsProvider');
  }
  return context;
}

// Optional hook that doesn't throw (for components that may be outside provider)
export function useWhatsAppWsContextOptional() {
  return useContext(WhatsAppWsContext);
}

interface WhatsAppWsProviderProps {
  children: React.ReactNode;
  dashboardMode?: boolean; // Connect to dashboard endpoint (multi-account)
}

export function WhatsAppWsProvider({ children, dashboardMode = true }: WhatsAppWsProviderProps) {
  const { token } = useAuthStore();
  const { selectedAccount } = useAccountStore();
  const chatStore = useChatStore();
  
  const ws = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<number | null>(null);
  const pingTimer = useRef<number | null>(null);
  const attempts = useRef(0);
  const isConnecting = useRef(false);
  const subscribedConversations = useRef<Set<string>>(new Set());
  
  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  
  // Build WebSocket URL
  const getWsUrl = useCallback(() => {
    if (!token) return null;
    
    let host = import.meta.env.VITE_WS_HOST;
    if (!host) {
      const apiUrl = import.meta.env.VITE_API_URL;
      if (apiUrl) {
        const url = new URL(apiUrl);
        host = url.host;
      } else {
        host = window.location.host;
      }
    }
    
    // Determine protocol
    const protocol = host.includes('localhost') || host.includes('127.0.0.1')
      ? 'ws'
      : 'wss';
    
    // Use dashboard mode for multi-account or specific account
    let endpoint = '/ws/whatsapp/dashboard/';
    if (!dashboardMode && selectedAccount) {
      endpoint = `/ws/whatsapp/${selectedAccount.id}/`;
    }
    
    return `${protocol}://${host}${endpoint}?token=${token}`;
  }, [token, dashboardMode, selectedAccount]);
  
  // Cleanup function
  const cleanup = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    if (pingTimer.current) {
      clearInterval(pingTimer.current);
      pingTimer.current = null;
    }
    if (ws.current) {
      ws.current.onclose = null;
      ws.current.onerror = null;
      ws.current.onmessage = null;
      ws.current.close();
      ws.current = null;
    }
  }, []);
  
  // Handle incoming messages
  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const data: WsEvent = JSON.parse(event.data);
      
      switch (data.type) {
        case 'message_received': {
          const { message, conversation_id, contact } = data;
          
          if (conversation_id) {
            // Add message to cache
            chatStore.addMessage(conversation_id, message);
            
            // Update conversation with new message
            chatStore.updateConversation({
              id: conversation_id,
              last_message_at: message.created_at,
              last_message_preview: message.text_body?.substring(0, 50) || 'Mídia',
            });
            
            // Increment unread if not the selected conversation
            if (chatStore.selectedConversationId !== conversation_id) {
              chatStore.incrementUnreadCount(conversation_id);
              
              // Show toast notification
              const contactName = contact?.name || message.from_number;
              toast(`Nova mensagem de ${contactName}`, { icon: '💬' });
            }
          }
          break;
        }
        
        case 'message_sent': {
          const { message, conversation_id } = data;
          if (conversation_id) {
            chatStore.addMessage(conversation_id, message);
            
            chatStore.updateConversation({
              id: conversation_id,
              last_message_at: message.created_at,
              last_message_preview: message.text_body?.substring(0, 50) || 'Mídia',
            });
          }
          break;
        }
        
        case 'status_updated': {
          chatStore.updateMessageStatus(data.message_id, data.status, data.timestamp);
          break;
        }
        
        case 'conversation_updated': {
          chatStore.updateConversation(data.conversation);
          break;
        }
        
        case 'typing': {
          // Could add typing indicators to store if needed
          break;
        }
        
        case 'error': {
          toast.error(`WhatsApp: ${data.error_message}`);
          break;
        }
        
        case 'connection_established':
          console.log('[WhatsAppWS] Connection established:', data.message);
          break;
          
        case 'pong':
          // Keep-alive response
          break;
      }
    } catch (error) {
      console.error('[WhatsAppWS] Error parsing message:', error);
    }
  }, [chatStore]);
  
  // Connect to WebSocket
  const connect = useCallback(() => {
    if (isConnecting.current || ws.current?.readyState === WebSocket.OPEN) {
      return;
    }
    
    const url = getWsUrl();
    if (!url) {
      setConnectionError('Não autenticado');
      return;
    }
    
    isConnecting.current = true;
    setConnectionError(null);
    
    try {
      ws.current = new WebSocket(url);
      
      ws.current.onopen = () => {
        console.log('[WhatsAppWS] Connected');
        isConnecting.current = false;
        attempts.current = 0;
        setIsConnected(true);
        setConnectionError(null);
        chatStore.setWsConnected(true);
        
        // Re-subscribe to previously subscribed conversations
        subscribedConversations.current.forEach((convId) => {
          ws.current?.send(JSON.stringify({
            type: 'subscribe_conversation',
            conversation_id: convId,
          }));
        });
        
        // Start ping interval
        pingTimer.current = window.setInterval(() => {
          if (ws.current?.readyState === WebSocket.OPEN) {
            ws.current.send(JSON.stringify({ type: 'ping' }));
          }
        }, 30000);
      };
      
      ws.current.onmessage = handleMessage;
      
      ws.current.onclose = (event) => {
        console.log('[WhatsAppWS] Disconnected:', event.code, event.reason);
        isConnecting.current = false;
        setIsConnected(false);
        chatStore.setWsConnected(false);
        
        if (pingTimer.current) {
          clearInterval(pingTimer.current);
          pingTimer.current = null;
        }
        
        // Don't reconnect if intentionally closed (4000-4999 are app codes)
        if (event.code >= 4000 && event.code < 5000) {
          setConnectionError('Conexão recusada pelo servidor');
          return;
        }
        
        // Exponential backoff reconnect
        const delay = Math.min(1000 * Math.pow(2, attempts.current), 30000);
        attempts.current += 1;
        
        if (attempts.current <= 10) {
          console.log(`[WhatsAppWS] Reconnecting in ${delay}ms (attempt ${attempts.current})`);
          reconnectTimer.current = window.setTimeout(connect, delay);
        } else {
          setConnectionError('Falha ao reconectar após várias tentativas');
        }
      };
      
      ws.current.onerror = (error) => {
        console.error('[WhatsAppWS] Error:', error);
        isConnecting.current = false;
      };
      
    } catch (error) {
      console.error('[WhatsAppWS] Connection error:', error);
      isConnecting.current = false;
      setConnectionError('Erro ao conectar');
    }
  }, [getWsUrl, handleMessage, chatStore]);
  
  // Reconnect function (exposed via context)
  const reconnect = useCallback(() => {
    cleanup();
    attempts.current = 0;
    connect();
  }, [cleanup, connect]);
  
  // Subscribe to a conversation
  const subscribeToConversation = useCallback((conversationId: string) => {
    subscribedConversations.current.add(conversationId);
    
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({
        type: 'subscribe_conversation',
        conversation_id: conversationId,
      }));
    }
  }, []);
  
  // Unsubscribe from a conversation
  const unsubscribeFromConversation = useCallback((conversationId: string) => {
    subscribedConversations.current.delete(conversationId);
    
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
  
  // Connect on mount, cleanup on unmount
  // Use a ref to track if we've initiated connection to prevent double connections
  const hasConnected = useRef(false);
  
  useEffect(() => {
    if (token && !hasConnected.current) {
      hasConnected.current = true;
      connect();
    }
    
    return () => {
      hasConnected.current = false;
      cleanup();
    };
  }, [token]); // Only depend on token, not on connect/cleanup to avoid reconnection loops
  
  // Reconnect when account changes (in non-dashboard mode)
  // Use a ref to track the previous account to avoid unnecessary reconnections
  const prevAccountId = useRef<string | null>(null);
  
  useEffect(() => {
    if (!dashboardMode && selectedAccount && token) {
      const newAccountId = selectedAccount.id;
      // Only reconnect if the account actually changed
      if (prevAccountId.current && prevAccountId.current !== newAccountId) {
        reconnect();
      }
      prevAccountId.current = newAccountId;
    }
  }, [dashboardMode, selectedAccount?.id, token]); // Use selectedAccount.id instead of whole object
  
  const value: WhatsAppWsContextValue = {
    isConnected,
    connectionError,
    subscribeToConversation,
    unsubscribeFromConversation,
    sendTypingIndicator,
    reconnect,
  };
  
  return (
    <WhatsAppWsContext.Provider value={value}>
      {children}
    </WhatsAppWsContext.Provider>
  );
}

export default WhatsAppWsProvider;
