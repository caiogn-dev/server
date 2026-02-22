import api from './api';
import { Conversation, ConversationNote, PaginatedResponse } from '../types';

export const conversationsService = {
  getConversations: async (params?: Record<string, string>): Promise<PaginatedResponse<Conversation>> => {
    const response = await api.get<PaginatedResponse<Conversation>>('/conversations/', { params });
    return response.data;
  },

  getConversation: async (id: string): Promise<Conversation> => {
    const response = await api.get<Conversation>(`/conversations/${id}/`);
    return response.data;
  },

  switchToHuman: async (id: string, agentId?: number): Promise<Conversation> => {
    const response = await api.post<Conversation>(`/conversations/${id}/switch_to_human/`, {
      agent_id: agentId,
    });
    return response.data;
  },

  switchToAuto: async (id: string): Promise<Conversation> => {
    const response = await api.post<Conversation>(`/conversations/${id}/switch_to_auto/`);
    return response.data;
  },

  assignAgent: async (id: string, agentId: number): Promise<Conversation> => {
    const response = await api.post<Conversation>(`/conversations/${id}/assign_agent/`, {
      agent_id: agentId,
    });
    return response.data;
  },

  unassignAgent: async (id: string): Promise<Conversation> => {
    const response = await api.post<Conversation>(`/conversations/${id}/unassign_agent/`);
    return response.data;
  },

  closeConversation: async (id: string): Promise<Conversation> => {
    const response = await api.post<Conversation>(`/conversations/${id}/close/`);
    return response.data;
  },

  resolveConversation: async (id: string): Promise<Conversation> => {
    const response = await api.post<Conversation>(`/conversations/${id}/resolve/`);
    return response.data;
  },

  reopenConversation: async (id: string): Promise<Conversation> => {
    const response = await api.post<Conversation>(`/conversations/${id}/reopen/`);
    return response.data;
  },

  getNotes: async (id: string): Promise<ConversationNote[]> => {
    const response = await api.get<ConversationNote[]>(`/conversations/${id}/notes/`);
    return response.data;
  },

  addNote: async (id: string, content: string): Promise<ConversationNote> => {
    const response = await api.post<ConversationNote>(`/conversations/${id}/add_note/`, { content });
    return response.data;
  },

  updateContext: async (id: string, context: Record<string, unknown>): Promise<Conversation> => {
    const response = await api.post<Conversation>(`/conversations/${id}/update_context/`, { context });
    return response.data;
  },

  addTag: async (id: string, tag: string): Promise<Conversation> => {
    const response = await api.post<Conversation>(`/conversations/${id}/add_tag/`, { tag });
    return response.data;
  },

  removeTag: async (id: string, tag: string): Promise<Conversation> => {
    const response = await api.post<Conversation>(`/conversations/${id}/remove_tag/`, { tag });
    return response.data;
  },

  getStats: async (accountId: string): Promise<Record<string, unknown>> => {
    const response = await api.get('/conversations/stats/', { params: { account_id: accountId } });
    return response.data;
  },

  markAsRead: async (id: string): Promise<Conversation> => {
    const response = await api.post<Conversation>(`/conversations/${id}/mark_as_read/`);
    return response.data;
  },
};
