/**
 * Global WebSocket Context - SINGLETON
 * Only ONE connection for the entire app
 */
import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';
import { useAuthStore } from '../stores/authStore';
import { useStore } from '../hooks/useStore';

const STORE_SLUG = import.meta.env.VITE_STORE_SLUG || 'pastita';

interface OrderEvent {
  type: string;
  order_id?: string;
  order_number?: string;
  status?: string;
  payment_status?: string;
  [key: string]: unknown;
}

type Callback = (data: OrderEvent) => void;

interface WSContextValue {
  isConnected: boolean;
  error: string | null;
  on: (event: string, cb: Callback) => () => void;
}

const WSContext = createContext<WSContextValue | null>(null);

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const { token } = useAuthStore();
  const { storeSlug, storeId } = useStore();
  const ws = useRef<WebSocket | null>(null);
  const listeners = useRef<Map<string, Set<Callback>>>(new Map());
  const reconnectTimer = useRef<number | undefined>(undefined);
  const pingTimer = useRef<number | undefined>(undefined);
  const attempts = useRef(0);
  const isConnecting = useRef(false);
  
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const effectiveStoreSlug = storeSlug || storeId || STORE_SLUG;

  const emit = useCallback((event: string, data: OrderEvent) => {
    const eventListeners = listeners.current.get(event);
    const wildcardListeners = listeners.current.get('*');
    
    console.log(`[WS] Event: ${event}`, data);
    console.log(`[WS] Listeners for '${event}':`, eventListeners?.size || 0);
    
    eventListeners?.forEach(cb => {
      try {
        cb(data);
      } catch (e) {
        console.error('[WS] Callback error:', e);
      }
    });
    wildcardListeners?.forEach(cb => {
      try {
        cb(data);
      } catch (e) {
        console.error('[WS] Wildcard callback error:', e);
      }
    });
  }, []);

  const connect = useCallback(() => {
    // Use token from store if present, otherwise try to read persisted token
    let effectiveToken = token;
    if (!effectiveToken && typeof window !== 'undefined') {
      try {
        const raw = window.localStorage.getItem('auth-storage');
        if (raw) {
          const parsed = JSON.parse(raw);
          effectiveToken = parsed?.state?.token || undefined;
          if (effectiveToken) console.debug('[WS] using token from localStorage');
        }
      } catch (e) {
        /* ignore */
      }
    }

    if (!effectiveToken) {
      console.log('[WS] No token, skipping connection');
      return;
    }
    
    if (isConnecting.current) {
      console.log('[WS] Already connecting, skipping');
      return;
    }
    
    if (ws.current?.readyState === WebSocket.OPEN) {
      console.log('[WS] Already connected');
      return;
    }

    // Close existing connection if any
    if (ws.current) {
      ws.current.onclose = null;
      ws.current.close();
      ws.current = null;
    }

    isConnecting.current = true;
    
    // Build URL
    let host = import.meta.env.VITE_WS_HOST;
    if (!host) {
      const api = import.meta.env.VITE_API_URL;
      host = api ? new URL(api).host : window.location.host;
    }
    const proto = host.includes('railway') || host.includes('vercel') || location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${proto}://${host}/ws/stores/${effectiveStoreSlug}/orders/?token=${effectiveToken}`;
    
    console.log('[WS] Connecting to:', url.replace(/token=.*/, 'token=***'));
    
    try {
      const socket = new WebSocket(url);
      ws.current = socket;
      
      socket.onopen = () => {
        console.log('[WS] Connected ✓');
        isConnecting.current = false;
        setIsConnected(true);
        setError(null);
        attempts.current = 0;
        
        // Ping every 25s
        if (pingTimer.current) window.clearInterval(pingTimer.current);
        pingTimer.current = window.setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send('{"type":"ping"}');
          }
        }, 25000);
      };
      
      socket.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          
          if (data.type === 'pong') return;
          
          if (data.type === 'connection_established') {
            console.log('[WS] Server confirmed connection');
            return;
          }
          
          // Normalize event names
          const eventMap: Record<string, string> = {
            'order.created': 'order_created',
            'order.updated': 'order_updated', 
            'order.paid': 'payment_received',
            'order.cancelled': 'order_cancelled',
          };
          
          const normalizedEvent = eventMap[data.type] || data.type;
          emit(normalizedEvent, data);
        } catch (err) {
          console.error('[WS] Parse error:', err);
        }
      };
      
      socket.onclose = (e) => {
        console.log('[WS] Closed:', e.code, e.reason);
        isConnecting.current = false;
        setIsConnected(false);
        
        if (pingTimer.current) {
          window.clearInterval(pingTimer.current);
          pingTimer.current = undefined;
        }
        
        // Reconnect on abnormal close
        if (e.code !== 1000 && attempts.current < 10) {
          const delay = Math.min(1000 * Math.pow(1.5, attempts.current), 30000);
          console.log(`[WS] Reconnecting in ${Math.round(delay)}ms (attempt ${attempts.current + 1}/10)`);
          setError('Reconectando...');
          
          reconnectTimer.current = window.setTimeout(() => {
            attempts.current++;
            connect();
          }, delay);
        } else if (attempts.current >= 10) {
          setError('Conexão perdida. Atualize a página.');
        }
      };
      
      socket.onerror = (e) => {
        console.error('[WS] Error:', e);
        isConnecting.current = false;
      };
    } catch (err) {
      console.error('[WS] Connection error:', err);
      isConnecting.current = false;
    }
  }, [token, emit, effectiveStoreSlug]);

  // Subscribe to events
  const on = useCallback((event: string, cb: Callback) => {
    if (!listeners.current.has(event)) {
      listeners.current.set(event, new Set());
    }
    listeners.current.get(event)!.add(cb);
    console.log(`[WS] Subscribed to '${event}' (total: ${listeners.current.get(event)!.size})`);
    
    return () => {
      listeners.current.get(event)?.delete(cb);
      console.log(`[WS] Unsubscribed from '${event}'`);
    };
  }, []);

  // Connect on mount
  useEffect(() => {
    connect();
    
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        if (!ws.current || ws.current.readyState !== WebSocket.OPEN) {
          console.log('[WS] Tab visible, reconnecting...');
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
      }
    };
  }, [connect]);

  return (
    <WSContext.Provider value={{ isConnected, error, on }}>
      {children}
    </WSContext.Provider>
  );
}

export function useWS() {
  const ctx = useContext(WSContext);
  if (!ctx) throw new Error('useWS must be inside WebSocketProvider');
  return ctx;
}
