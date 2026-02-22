import { useState, useCallback, useEffect } from 'react';
import { messengerService, MessengerAccount, MessengerConversation, MessengerMessage, MessengerProfile, BroadcastMessage, SponsoredMessage } from '../services/messenger';
import toast from 'react-hot-toast';

// ============================================
// ACCOUNTS
// ============================================

export const useMessengerAccounts = () => {
  const [accounts, setAccounts] = useState<MessengerAccount[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchAccounts = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await messengerService.getAccounts();
      setAccounts(res.data);
    } catch (err) {
      setError(err as Error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  return { accounts, isLoading, error, refetch: fetchAccounts };
};

export const useMessengerAccount = (id: string) => {
  const [account, setAccount] = useState<MessengerAccount | null>(null);
  const [isLoading, setIsLoading] = useState(!!id);
  const [error, setError] = useState<Error | null>(null);

  const fetchAccount = useCallback(async () => {
    if (!id) return;
    setIsLoading(true);
    try {
      const res = await messengerService.getAccount(id);
      setAccount(res.data);
    } catch (err) {
      setError(err as Error);
    } finally {
      setIsLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchAccount();
  }, [fetchAccount]);

  return { account, isLoading, error, refetch: fetchAccount };
};

export const useCreateMessengerAccount = () => {
  const [isLoading, setIsLoading] = useState(false);

  const createAccount = useCallback(async (data: Parameters<typeof messengerService.createAccount>[0]) => {
    setIsLoading(true);
    try {
      const res = await messengerService.createAccount(data);
      toast.success('Conta Messenger criada com sucesso!');
      return res.data;
    } catch (err) {
      toast.error('Erro ao criar conta Messenger');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return { createAccount, isLoading };
};

export const useUpdateMessengerAccount = () => {
  const [isLoading, setIsLoading] = useState(false);

  const updateAccount = useCallback(async (id: string, data: Partial<MessengerAccount>) => {
    setIsLoading(true);
    try {
      const res = await messengerService.updateAccount(id, data);
      toast.success('Conta atualizada!');
      return res.data;
    } catch (err) {
      toast.error('Erro ao atualizar conta');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return { updateAccount, isLoading };
};

export const useDeleteMessengerAccount = () => {
  const [isLoading, setIsLoading] = useState(false);

  const deleteAccount = useCallback(async (id: string) => {
    setIsLoading(true);
    try {
      await messengerService.deleteAccount(id);
      toast.success('Conta removida!');
    } catch (err) {
      toast.error('Erro ao remover conta');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return { deleteAccount, isLoading };
};

// ============================================
// CONVERSATIONS
// ============================================

export const useMessengerConversations = (accountId?: string) => {
  const [conversations, setConversations] = useState<MessengerConversation[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchConversations = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await messengerService.getConversations(accountId);
      setConversations(res.data);
    } catch (err) {
      setError(err as Error);
    } finally {
      setIsLoading(false);
    }
  }, [accountId]);

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  return { conversations, isLoading, error, refetch: fetchConversations };
};

export const useMessengerConversation = (id: string) => {
  const [conversation, setConversation] = useState<MessengerConversation | null>(null);
  const [isLoading, setIsLoading] = useState(!!id);

  const fetchConversation = useCallback(async () => {
    if (!id) return;
    setIsLoading(true);
    try {
      const res = await messengerService.getConversation(id);
      setConversation(res.data);
    } finally {
      setIsLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchConversation();
  }, [fetchConversation]);

  return { conversation, isLoading, refetch: fetchConversation };
};

// ============================================
// MESSAGES
// ============================================

export const useMessengerMessages = (conversationId: string) => {
  const [messages, setMessages] = useState<MessengerMessage[]>([]);
  const [isLoading, setIsLoading] = useState(!!conversationId);

  const fetchMessages = useCallback(async () => {
    if (!conversationId) return;
    setIsLoading(true);
    try {
      const res = await messengerService.getMessages(conversationId);
      setMessages(res.data);
    } finally {
      setIsLoading(false);
    }
  }, [conversationId]);

  useEffect(() => {
    fetchMessages();
  }, [fetchMessages]);

  const sendMessage = useCallback(async (data: { content: string; message_type?: string }) => {
    if (!conversationId) return;
    try {
      const res = await messengerService.sendMessage(conversationId, data);
      await fetchMessages();
      return res.data;
    } catch (err) {
      toast.error('Erro ao enviar mensagem');
      throw err;
    }
  }, [conversationId, fetchMessages]);

  return { messages, isLoading, refetch: fetchMessages, sendMessage };
};

// ============================================
// BROADCAST
// ============================================

export const useMessengerBroadcasts = (accountId?: string) => {
  const [broadcasts, setBroadcasts] = useState<BroadcastMessage[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const fetchBroadcasts = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await messengerService.getBroadcasts(accountId);
      setBroadcasts(res.data);
    } finally {
      setIsLoading(false);
    }
  }, [accountId]);

  useEffect(() => {
    fetchBroadcasts();
  }, [fetchBroadcasts]);

  const createBroadcast = useCallback(async (data: Partial<BroadcastMessage>) => {
    try {
      const res = await messengerService.createBroadcast(data);
      await fetchBroadcasts();
      toast.success('Broadcast criado!');
      return res.data;
    } catch (err) {
      toast.error('Erro ao criar broadcast');
      throw err;
    }
  }, [fetchBroadcasts]);

  return { broadcasts, isLoading, refetch: fetchBroadcasts, createBroadcast };
};

// ============================================
// SPONSORED
// ============================================

export const useMessengerSponsored = (accountId?: string) => {
  const [messages, setMessages] = useState<SponsoredMessage[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const fetchSponsored = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await messengerService.getSponsoredMessages(accountId);
      setMessages(res.data);
    } finally {
      setIsLoading(false);
    }
  }, [accountId]);

  useEffect(() => {
    fetchSponsored();
  }, [fetchSponsored]);

  return { sponsoredMessages: messages, isLoading, refetch: fetchSponsored };
};

export default {
  useMessengerAccounts,
  useMessengerConversations,
  useMessengerMessages,
};
