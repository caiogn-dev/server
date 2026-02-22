import api from './api';

export interface HandoverStatus {
  handover_status: 'bot' | 'human' | 'pending';
  status_display?: string;
  assigned_to?: string;
  assigned_to_name?: string;
  last_transfer_at?: string;
  last_transfer_reason?: string;
}

export interface HandoverResponse {
  success: boolean;
  handover_status: 'bot' | 'human' | 'pending';
  status_display?: string;
  assigned_to?: string;
  assigned_to_name?: string;
  message?: string;
}

export interface HandoverLog {
  id: string;
  conversation: string;
  from_status: string;
  to_status: string;
  performed_by?: string;
  performed_by_name?: string;
  reason?: string;
  created_at: string;
}

export interface HandoverRequest {
  id: string;
  conversation: string;
  status: 'pending' | 'approved' | 'rejected' | 'expired';
  status_display?: string;
  requested_by?: string;
  reason?: string;
  priority: 'low' | 'medium' | 'high' | 'urgent';
  priority_display?: string;
  approved_by?: string;
  approved_at?: string;
  assigned_to?: string;
  created_at: string;
  expires_at?: string;
}

/**
 * Handover Protocol Service
 * 
 * Gerencia a transferência de conversas entre Bot e Atendimento Humano.
 * 
 * Fluxo:
 * 1. Conversa inicia no Bot (handover_status: 'bot')
 * 2. Se cliente pede ou bot não resolve, transferir para 'human'
 * 3. Operador humano atende e pode transferir de volta para 'bot'
 * 
 * Endpoints:
 * - POST /api/v1/handover/conversations/<id>/handover/bot/
 * - POST /api/v1/handover/conversations/<id>/handover/human/
 * - GET  /api/v1/handover/conversations/<id>/handover/status/
 * - GET  /api/v1/handover/conversations/<id>/handover/logs/
 * - POST /api/v1/handover/conversations/<id>/handover/request/
 */
export const handoverService = {
  /**
   * Transferir conversa para o Bot
   */
  transferToBot: async (conversationId: string, reason?: string): Promise<HandoverResponse> => {
    const response = await api.post<HandoverResponse>(
      `/handover/conversations/${conversationId}/handover/bot/`,
      { reason }
    );
    return response.data;
  },

  /**
   * Transferir conversa para Atendimento Humano
   */
  transferToHuman: async (
    conversationId: string, 
    options?: { reason?: string; assigned_to_id?: string }
  ): Promise<HandoverResponse> => {
    const response = await api.post<HandoverResponse>(
      `/handover/conversations/${conversationId}/handover/human/`,
      options
    );
    return response.data;
  },

  /**
   * Obter status atual do handover
   */
  getStatus: async (conversationId: string): Promise<HandoverStatus> => {
    const response = await api.get<HandoverStatus>(
      `/handover/conversations/${conversationId}/handover/status/`
    );
    return response.data;
  },

  /**
   * Obter histórico de transferências
   */
  getLogs: async (conversationId: string): Promise<HandoverLog[]> => {
    const response = await api.get<HandoverLog[]>(
      `/handover/conversations/${conversationId}/handover/logs/`
    );
    return response.data;
  },

  /**
   * Solicitar transferência para atendimento humano
   */
  requestHandover: async (
    conversationId: string,
    options?: { reason?: string; priority?: 'low' | 'medium' | 'high' | 'urgent' }
  ): Promise<{ success: boolean; request_id: string; status: string; message: string }> => {
    const response = await api.post(
      `/handover/conversations/${conversationId}/handover/request/`,
      options
    );
    return response.data;
  },

  /**
   * Listar solicitações de handover pendentes
   */
  getRequests: async (): Promise<HandoverRequest[]> => {
    const response = await api.get<{ results: HandoverRequest[] }>('/handover/requests/');
    return response.data.results || response.data as unknown as HandoverRequest[];
  },

  /**
   * Aprovar solicitação de handover
   */
  approveRequest: async (
    requestId: string,
    assignedToId?: string
  ): Promise<{ success: boolean; message: string; conversation_id: string; assigned_to: string }> => {
    const response = await api.post(`/handover/requests/${requestId}/approve/`, {
      assigned_to_id: assignedToId,
    });
    return response.data;
  },

  /**
   * Rejeitar solicitação de handover
   */
  rejectRequest: async (requestId: string): Promise<{ success: boolean; message: string }> => {
    const response = await api.post(`/handover/requests/${requestId}/reject/`);
    return response.data;
  },

  /**
   * Toggle entre Bot e Humano
   */
  toggle: async (
    conversationId: string, 
    currentStatus: 'bot' | 'human'
  ): Promise<HandoverResponse> => {
    if (currentStatus === 'bot') {
      return handoverService.transferToHuman(conversationId);
    } else {
      return handoverService.transferToBot(conversationId);
    }
  },
};

export default handoverService;
