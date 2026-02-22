/**
 * Hook for playing notification sounds
 * Uses Web Audio API with proper initialization
 */
import { useCallback, useRef, useEffect, useState } from 'react';

const ORDER_FREQUENCIES = [659.25, 783.99, 987.77, 1174.66]; // E5, G5, B5, D6
const SUCCESS_FREQUENCIES = [523.25, 783.99]; // C5, G5

interface NotificationSoundOptions {
  enabled?: boolean;
  volume?: number;
}

export const useNotificationSound = (options: NotificationSoundOptions = {}) => {
  const { enabled = true, volume = 1.0 } = options; // Volume at 100%
  
  const audioCtx = useRef<AudioContext | null>(null);
  const alertIntervalId = useRef<number | undefined>(undefined);
  const [isAlertActive, setIsAlertActive] = useState(false);
  const [isInitialized, setIsInitialized] = useState(false);

  // Initialize AudioContext
  const initAudio = useCallback(() => {
    if (audioCtx.current && audioCtx.current.state !== 'closed') {
      // Resume if suspended
      if (audioCtx.current.state === 'suspended') {
        audioCtx.current.resume().then(() => {
          console.log('[Sound] AudioContext resumed');
        });
      }
      return audioCtx.current;
    }
    
    try {
      audioCtx.current = new (window.AudioContext || (window as any).webkitAudioContext)();
      setIsInitialized(true);
      console.log('[Sound] AudioContext initialized, state:', audioCtx.current.state);
      return audioCtx.current;
    } catch (e) {
      console.error('[Sound] Failed to create AudioContext:', e);
      return null;
    }
  }, []);

  // Request notification permission and init audio on first click
  useEffect(() => {
    const handleInteraction = () => {
      initAudio();
      if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission().then(p => console.log('[Sound] Notification permission:', p));
      }
    };

    document.addEventListener('click', handleInteraction, { once: true });
    document.addEventListener('keydown', handleInteraction, { once: true });
    
    return () => {
      document.removeEventListener('click', handleInteraction);
      document.removeEventListener('keydown', handleInteraction);
      if (alertIntervalId.current) {
        window.clearInterval(alertIntervalId.current);
      }
    };
  }, [initAudio]);

  // Play a single tone
  const playTone = useCallback((freq: number, duration: number, startTime: number, vol: number) => {
    const ctx = audioCtx.current;
    if (!ctx) return;

    try {
      const oscillator = ctx.createOscillator();
      const gainNode = ctx.createGain();

      oscillator.connect(gainNode);
      gainNode.connect(ctx.destination);

      oscillator.type = 'sine';
      oscillator.frequency.setValueAtTime(freq, startTime);

      gainNode.gain.setValueAtTime(0, startTime);
      gainNode.gain.linearRampToValueAtTime(vol, startTime + 0.02);
      gainNode.gain.exponentialRampToValueAtTime(0.001, startTime + duration);

      oscillator.start(startTime);
      oscillator.stop(startTime + duration);
    } catch (e) {
      console.error('[Sound] playTone error:', e);
    }
  }, []);

  // Play order sound (arpeggio)
  const playOrderSoundOnce = useCallback(async () => {
    let ctx = audioCtx.current;
    if (!ctx) {
      ctx = initAudio();
      if (!ctx) {
        console.error('[Sound] No AudioContext available');
        return;
      }
    }

    // MUST resume if suspended (browser requirement)
    if (ctx.state === 'suspended') {
      console.log('[Sound] Resuming suspended AudioContext...');
      await ctx.resume();
      console.log('[Sound] AudioContext resumed, state:', ctx.state);
    }

    const now = ctx.currentTime;
    console.log('[Sound] Playing at time:', now, 'state:', ctx.state);
    
    // First wave - ascending (louder)
    ORDER_FREQUENCIES.forEach((freq, i) => {
      playTone(freq, 0.3, now + i * 0.12, volume * 0.7);
    });
    
    // Second wave - ascending (delayed)
    ORDER_FREQUENCIES.forEach((freq, i) => {
      playTone(freq, 0.25, now + 0.7 + i * 0.1, volume * 0.5);
    });
    
    console.log('[Sound] Order sound scheduled');
  }, [initAudio, playTone, volume]);

  // Stop the repeating alert
  const stopAlert = useCallback(() => {
    if (alertIntervalId.current) {
      window.clearInterval(alertIntervalId.current);
      alertIntervalId.current = undefined;
    }
    setIsAlertActive(false);
    console.log('[Sound] Alert stopped');
  }, []);

  // Play order sound with optional repeat
  const playOrderSound = useCallback(() => {
    if (!enabled) {
      console.log('[Sound] Disabled, not playing');
      return;
    }

    console.log('[Sound] playOrderSound called');
    playOrderSoundOnce();

    // Start repeating if not already active
    if (!isAlertActive) {
      setIsAlertActive(true);
      alertIntervalId.current = window.setInterval(playOrderSoundOnce, 4000);
      
      // Auto-stop after 30 seconds
      window.setTimeout(() => {
        stopAlert();
      }, 30000);
    }

    // Browser notification
    if ('Notification' in window && Notification.permission === 'granted') {
      try {
        new Notification('🍝 Novo Pedido!', {
          body: 'Você tem um novo pedido para processar',
          icon: '/favicon.ico',
          tag: 'new-order',
          requireInteraction: true,
        });
      } catch (e) {
        console.error('[Sound] Notification error:', e);
      }
    }
  }, [enabled, playOrderSoundOnce, isAlertActive, stopAlert]);

  // Play success sound
  const playSuccessSound = useCallback(() => {
    if (!enabled) return;

    let ctx = audioCtx.current;
    if (!ctx) {
      ctx = initAudio();
      if (!ctx) return;
    }

    if (ctx.state === 'suspended') {
      ctx.resume();
    }

    const now = ctx.currentTime;
    playTone(SUCCESS_FREQUENCIES[0], 0.15, now, volume * 0.4);
    playTone(SUCCESS_FREQUENCIES[1], 0.3, now + 0.15, volume * 0.45);
    
    console.log('[Sound] Playing success sound');
  }, [enabled, initAudio, playTone, volume]);

  // Alias for compatibility
  const playNotificationSound = playOrderSound;

  return {
    playOrderSound,
    playSuccessSound,
    playNotificationSound,
    stopAlert,
    isAlertActive,
    isInitialized,
    initAudio,
  };
};

export default useNotificationSound;
