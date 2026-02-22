/**
 * Hook for real-time order updates via WebSocket
 * Uses global WebSocket context (singleton)
 */
import { useEffect, useRef } from 'react';
import { useWS } from '../context/WebSocketContext';

interface OrderUpdate {
  type: string;
  order_id?: string;
  order_number?: string;
  status?: string;
  payment_status?: string;
  [key: string]: unknown;
}

interface UseOrdersWebSocketOptions {
  onOrderCreated?: (data: OrderUpdate) => void;
  onOrderUpdated?: (data: OrderUpdate) => void;
  onStatusChanged?: (data: OrderUpdate) => void;
  onPaymentReceived?: (data: OrderUpdate) => void;
  enabled?: boolean;
}

export const useOrdersWebSocket = (options: UseOrdersWebSocketOptions = {}) => {
  const { isConnected, error: connectionError, on } = useWS();
  const opts = useRef(options);
  opts.current = options;

  useEffect(() => {
    if (options.enabled === false) return;

    const unsubs = [
      on('order_created', (d) => opts.current.onOrderCreated?.(d)),
      on('order_updated', (d) => {
        opts.current.onOrderUpdated?.(d);
        opts.current.onStatusChanged?.(d);
      }),
      on('order_cancelled', (d) => opts.current.onStatusChanged?.({ ...d, status: 'cancelled' })),
      on('payment_received', (d) => opts.current.onPaymentReceived?.(d)),
    ];

    return () => unsubs.forEach(u => u());
  }, [on, options.enabled]);

  return { isConnected, connectionError };
};

export default useOrdersWebSocket;
