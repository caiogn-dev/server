/**
 * Automation WebSocket hook - DEPRECATED
 * Use useWS from WebSocketContext instead
 */
import { useState, useCallback } from 'react';

interface UseAutomationWSOptions {
  onSessionStart?: () => void;
  onSessionEnd?: () => void;
  onMessageSent?: () => void;
  onError?: () => void;
}

export function useAutomationWS(_options: UseAutomationWSOptions = {}) {
  const [isConnected] = useState(false);
  const [lastEvent] = useState(null);

  return {
    isConnected,
    lastEvent,
    connect: useCallback(() => {}, []),
    disconnect: useCallback(() => {}, []),
    startSession: useCallback(() => {}, []),
    endSession: useCallback(() => {}, []),
    sendMessage: useCallback(() => {}, []),
  };
}

export default useAutomationWS;
