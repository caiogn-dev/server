import { useState, useCallback, useEffect } from 'react';
import { handoverService, HandoverStatus, HandoverResponse } from '../services/handover';
import toast from 'react-hot-toast';

// ============================================
// HANDOVER STATUS
// ============================================

export const useHandoverStatus = (conversationId: string) => {
  const [status, setStatus] = useState<HandoverStatus | null>(null);
  const [isLoading, setIsLoading] = useState(!!conversationId);

  const fetchStatus = useCallback(async () => {
    if (!conversationId) return;
    setIsLoading(true);
    try {
      const res = await handoverService.getStatus(conversationId);
      setStatus(res);
    } finally {
      setIsLoading(false);
    }
  }, [conversationId]);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 30000); // Poll every 30s
    return () => clearInterval(interval);
  }, [fetchStatus]);

  return { status, isLoading, refetch: fetchStatus };
};

// ============================================
// TRANSFER TO HUMAN
// ============================================

export const useTransferToHuman = () => {
  const [isLoading, setIsLoading] = useState(false);

  const transferToHuman = useCallback(async (conversationId: string) => {
    setIsLoading(true);
    try {
      const res = await handoverService.transferToHuman(conversationId);
      toast.success('Conversa transferida para atendente humano!');
      return res;
    } catch (err) {
      toast.error('Erro ao transferir');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return { transferToHuman, isLoading };
};

// ============================================
// TRANSFER TO BOT
// ============================================

export const useTransferToBot = () => {
  const [isLoading, setIsLoading] = useState(false);

  const transferToBot = useCallback(async (conversationId: string) => {
    setIsLoading(true);
    try {
      const res = await handoverService.transferToBot(conversationId);
      toast.success('Conversa retornada para o bot!');
      return res;
    } catch (err) {
      toast.error('Erro ao retornar para bot');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return { transferToBot, isLoading };
};

// ============================================
// TOGGLE HANDOVER
// ============================================

export const useToggleHandover = () => {
  const [isLoading, setIsLoading] = useState(false);

  const toggle = useCallback(async (
    conversationId: string,
    currentStatus: 'bot' | 'human'
  ) => {
    setIsLoading(true);
    try {
      const res = await handoverService.toggle(conversationId, currentStatus);
      toast.success(
        res.handover_status === 'human' 
          ? 'Transferido para atendimento humano!' 
          : 'Retornado para o bot!'
      );
      return res;
    } catch (err) {
      toast.error('Erro ao transferir conversa');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return { toggle, isLoading };
};

export default {
  useHandoverStatus,
  useTransferToHuman,
  useTransferToBot,
  useToggleHandover,
};
