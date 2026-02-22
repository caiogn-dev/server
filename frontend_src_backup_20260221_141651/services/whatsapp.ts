import api from './api';
import {
  WhatsAppAccount,
  CreateWhatsAppAccount,
  Message,
  MessageTemplate,
  PaginatedResponse,
  SendTextMessage,
  SendTemplateMessage,
  SendInteractiveButtons,
  SendInteractiveList,
  Conversation,
} from '../types';

/**
 * WhatsApp Service
 * 
 * Handles WhatsApp-specific operations:
 * - Account management
 * - Message sending
 * - Template management
 * 
 * NOTE: Campaigns, scheduled messages, and contact lists have been moved to campaigns.ts
 * to avoid duplication and use the unified marketing API endpoints.
 */
export const whatsappService = {
  // Accounts
  getAccounts: async (): Promise<PaginatedResponse<WhatsAppAccount>> => {
    const response = await api.get<PaginatedResponse<WhatsAppAccount>>('/whatsapp/accounts/');
    return response.data;
  },

  getAccount: async (id: string): Promise<WhatsAppAccount> => {
    const response = await api.get<WhatsAppAccount>(`/whatsapp/accounts/${id}/`);
    return response.data;
  },

  createAccount: async (data: CreateWhatsAppAccount): Promise<WhatsAppAccount> => {
    const response = await api.post<WhatsAppAccount>('/whatsapp/accounts/', data);
    return response.data;
  },

  updateAccount: async (id: string, data: Partial<CreateWhatsAppAccount>): Promise<WhatsAppAccount> => {
    const response = await api.patch<WhatsAppAccount>(`/whatsapp/accounts/${id}/`, data);
    return response.data;
  },

  deleteAccount: async (id: string): Promise<void> => {
    await api.delete(`/whatsapp/accounts/${id}/`);
  },

  activateAccount: async (id: string): Promise<WhatsAppAccount> => {
    const response = await api.post<WhatsAppAccount>(`/whatsapp/accounts/${id}/activate/`);
    return response.data;
  },

  deactivateAccount: async (id: string): Promise<WhatsAppAccount> => {
    const response = await api.post<WhatsAppAccount>(`/whatsapp/accounts/${id}/deactivate/`);
    return response.data;
  },

  rotateToken: async (id: string, accessToken: string): Promise<{ message: string; token_version: number }> => {
    const response = await api.post(`/whatsapp/accounts/${id}/rotate_token/`, { access_token: accessToken });
    return response.data;
  },

  // Messages
  getMessages: async (accountId?: string, params?: Record<string, string>): Promise<PaginatedResponse<Message>> => {
    const queryParams: Record<string, string> = { ...params };
    if (accountId) queryParams.account = accountId;
    const response = await api.get<PaginatedResponse<Message>>('/whatsapp/messages/', { params: queryParams });
    return response.data;
  },

  getMessage: async (id: string): Promise<Message> => {
    const response = await api.get<Message>(`/whatsapp/messages/${id}/`);
    return response.data;
  },

  sendTextMessage: async (data: SendTextMessage): Promise<Message> => {
    const response = await api.post<Message>('/whatsapp/messages/send_text/', data);
    return response.data;
  },

  sendTemplateMessage: async (data: SendTemplateMessage): Promise<Message> => {
    const response = await api.post<Message>('/whatsapp/messages/send_template/', data);
    return response.data;
  },

  sendInteractiveButtons: async (data: SendInteractiveButtons): Promise<Message> => {
    const response = await api.post<Message>('/whatsapp/messages/send_interactive_buttons/', data);
    return response.data;
  },

  sendInteractiveList: async (data: SendInteractiveList): Promise<Message> => {
    const response = await api.post<Message>('/whatsapp/messages/send_interactive_list/', data);
    return response.data;
  },

  markAsRead: async (messageId: string): Promise<void> => {
    await api.post(`/whatsapp/messages/${messageId}/mark_as_read/`);
  },

  // Templates
  getTemplates: async (accountId?: string): Promise<PaginatedResponse<MessageTemplate>> => {
    const params: Record<string, string> = {};
    if (accountId) params.account = accountId;
    const response = await api.get<PaginatedResponse<MessageTemplate>>('/whatsapp/templates/', { params });
    return response.data;
  },

  getTemplate: async (id: string): Promise<MessageTemplate> => {
    const response = await api.get<MessageTemplate>(`/whatsapp/templates/${id}/`);
    return response.data;
  },

  syncTemplates: async (accountId: string): Promise<{ message: string; synced: number }> => {
    const response = await api.post('/whatsapp/templates/sync/', { account_id: accountId });
    return response.data;
  },

  // Business Profile
  getBusinessProfile: async (accountId: string): Promise<Record<string, unknown>> => {
    const response = await api.get<Record<string, unknown>>(`/whatsapp/accounts/${accountId}/business_profile/`);
    return response.data;
  },

  // Message Stats
  getMessageStats: async (accountId: string, startDate?: string, endDate?: string): Promise<Record<string, number>> => {
    const params: Record<string, string> = {};
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    const response = await api.get<Record<string, number>>('/whatsapp/messages/stats/', { 
      params: { ...params, account_id: accountId }
    });
    return response.data;
  },

  // Conversation History
  getConversationHistory: async (accountId: string, phoneNumber: string, limit: number = 100): Promise<Message[]> => {
    const response = await api.get<PaginatedResponse<Message> | Message[]>('/whatsapp/messages/', {
      params: {
        account: accountId,
        phone_number: phoneNumber,
        limit: limit.toString(),
        ordering: '-created_at',
      },
    });
    // Handle both paginated and array responses
    if (response.data && 'results' in response.data) {
      return response.data.results || [];
    }
    return Array.isArray(response.data) ? response.data : [];
  },

  // Send Media Message
  sendMediaMessage: async (data: {
    account_id: string;
    to: string;
    file: File;
    caption?: string;
  }): Promise<Message> => {
    const formData = new FormData();
    formData.append('account_id', data.account_id);
    formData.append('to', data.to);
    formData.append('file', data.file);
    if (data.caption) {
      formData.append('caption', data.caption);
    }

    const response = await api.post<Message>('/whatsapp/messages/send_media/', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
};

export default whatsappService;
