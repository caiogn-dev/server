import api from './api';

export interface MessengerAccount {
  id: string;
  name: string;
  page_id: string;
  page_name: string;
  page_access_token?: string;  // write-only, not returned in responses
  status: 'active' | 'inactive' | 'suspended';
  is_active: boolean;
  webhook_verified: boolean;
  auto_response_enabled: boolean;
  human_handoff_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface MessengerConversation {
  id: string;
  account: string;
  account_name?: string;
  sender_id: string;
  sender_name: string;
  status: 'open' | 'closed' | 'pending';
  last_message?: string;
  last_message_at?: string;
  unread_count: number;
  is_bot_active: boolean;
  handover_status: 'bot' | 'human' | 'pending';
  assigned_to?: number;
  created_at: string;
  updated_at: string;
}

export interface MessengerMessage {
  id: string;
  conversation: string;
  sender_id: string;
  sender_name: string;
  content: string;
  message_type: 'text' | 'image' | 'video' | 'audio' | 'file' | 'template';
  media_url?: string;
  attachments?: Array<{
    type: string;
    url: string;
    name?: string;
  }>;
  quick_replies?: Array<{
    title: string;
    payload: string;
  }>;
  buttons?: Array<{
    type: string;
    title: string;
    url?: string;
    payload?: string;
  }>;
  is_from_bot: boolean;
  is_read: boolean;
  mid?: string;  // Messenger message ID
  created_at: string;
}

export interface MessengerProfile {
  greeting?: Array<{
    locale: string;
    text: string;
  }>;
  ice_breakers?: Array<{
    question: string;
    payload: string;
  }>;
  persistent_menu?: Array<{
    locale: string;
    composer_input_disabled: boolean;
    call_to_actions: Array<{
      type: string;
      title: string;
      url?: string;
      payload?: string;
    }>;
  }>;
  whitelisted_domains?: string[];
}

export interface BroadcastMessage {
  id: string;
  account: string;
  name: string;
  content: string;
  message_type: 'text' | 'image' | 'video' | 'template';
  target_audience: 'all' | 'segment';
  segment_criteria?: Record<string, any>;
  status: 'draft' | 'scheduled' | 'sending' | 'sent' | 'failed';
  scheduled_at?: string;
  sent_count: number;
  delivered_count: number;
  failed_count: number;
  created_at: string;
}

export interface SponsoredMessage {
  id: string;
  account: string;
  name: string;
  content: string;
  image_url?: string;
  cta_type: string;
  cta_url?: string;
  budget: number;
  currency: string;
  targeting: Record<string, any>;
  status: 'draft' | 'pending' | 'active' | 'paused' | 'completed';
  created_at: string;
}

export const messengerService = {
  // Accounts
  getAccounts: () => api.get<MessengerAccount[]>('/messenger/accounts/'),
  
  getAccount: (id: string) => api.get<MessengerAccount>(`/messenger/accounts/${id}/`),
  
  createAccount: (data: {
    name: string;
    page_id: string;
    page_name: string;
    page_access_token: string;
  }) => api.post<MessengerAccount>('/messenger/accounts/', data),
  
  updateAccount: (id: string, data: Partial<MessengerAccount>) =>
    api.patch<MessengerAccount>(`/messenger/accounts/${id}/`, data),
  
  deleteAccount: (id: string) => api.delete(`/messenger/accounts/${id}/`),
  
  verifyWebhook: (id: string) => api.post(`/messenger/accounts/${id}/verify_webhook/`),
  
  // Toggle auto-response
  toggleAutoResponse: (id: string, enabled: boolean) =>
    api.patch<MessengerAccount>(`/messenger/accounts/${id}/`, { auto_response_enabled: enabled }),
  
  // Toggle human handoff
  toggleHumanHandoff: (id: string, enabled: boolean) =>
    api.patch<MessengerAccount>(`/messenger/accounts/${id}/`, { human_handoff_enabled: enabled }),
  
  // Conversations
  getConversations: (accountId?: string) =>
    api.get<MessengerConversation[]>('/messenger/conversations/', {
      params: accountId ? { account: accountId } : undefined,
    }),
  
  getConversation: (id: string) =>
    api.get<MessengerConversation>(`/messenger/conversations/${id}/`),
  
  markAsRead: (conversationId: string) =>
    api.post(`/messenger/conversations/${conversationId}/mark-read/`),
  
  // Messages
  getMessages: (conversationId: string, params?: { limit?: number; offset?: number }) =>
    api.get<MessengerMessage[]>(`/messenger/conversations/${conversationId}/messages/`, { params }),
  
  sendMessage: (conversationId: string, data: {
    content: string;
    message_type?: string;
    attachments?: any[];
    quick_replies?: any[];
  }) => api.post<MessengerMessage>(`/messenger/conversations/${conversationId}/send-message/`, data),
  
  // Profile
  getProfile: (accountId: string) =>
    api.get<MessengerProfile>(`/messenger/accounts/${accountId}/profile/`),
  
  updateProfile: (accountId: string, data: MessengerProfile) =>
    api.patch(`/messenger/accounts/${accountId}/profile/`, data),
  
  // Broadcast
  getBroadcasts: (accountId?: string) =>
    api.get<BroadcastMessage[]>('/messenger/broadcasts/', {
      params: accountId ? { account: accountId } : undefined,
    }),
  
  getBroadcast: (id: string) => api.get<BroadcastMessage>(`/messenger/broadcasts/${id}/`),
  
  createBroadcast: (data: Partial<BroadcastMessage>) =>
    api.post<BroadcastMessage>('/messenger/broadcasts/', data),
  
  updateBroadcast: (id: string, data: Partial<BroadcastMessage>) =>
    api.patch<BroadcastMessage>(`/messenger/broadcasts/${id}/`, data),
  
  deleteBroadcast: (id: string) => api.delete(`/messenger/broadcasts/${id}/`),
  
  scheduleBroadcast: (id: string, scheduledAt: string) =>
    api.post(`/messenger/broadcasts/${id}/schedule/`, { scheduled_at: scheduledAt }),
  
  cancelBroadcast: (id: string) =>
    api.post(`/messenger/broadcasts/${id}/cancel/`),
  
  sendBroadcast: (id: string) =>
    api.post(`/messenger/broadcasts/${id}/send/`),
  
  getBroadcastStats: (id: string) =>
    api.get(`/messenger/broadcasts/${id}/stats/`),
  
  // Sponsored Messages
  getSponsoredMessages: (accountId?: string) =>
    api.get<SponsoredMessage[]>('/messenger/sponsored/', {
      params: accountId ? { account: accountId } : undefined,
    }),
  
  getSponsoredMessage: (id: string) =>
    api.get<SponsoredMessage>(`/messenger/sponsored/${id}/`),
  
  createSponsoredMessage: (data: Partial<SponsoredMessage>) =>
    api.post<SponsoredMessage>('/messenger/sponsored/', data),
  
  updateSponsoredMessage: (id: string, data: Partial<SponsoredMessage>) =>
    api.patch<SponsoredMessage>(`/messenger/sponsored/${id}/`, data),
  
  deleteSponsoredMessage: (id: string) => api.delete(`/messenger/sponsored/${id}/`),
  
  publishSponsoredMessage: (id: string) =>
    api.post(`/messenger/sponsored/${id}/publish/`),
  
  pauseSponsoredMessage: (id: string) =>
    api.post(`/messenger/sponsored/${id}/pause/`),
};

export default messengerService;
