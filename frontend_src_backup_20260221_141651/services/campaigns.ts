import api from './api';

export interface Campaign {
  id: string;
  account: string;
  name: string;
  description: string;
  campaign_type: 'broadcast' | 'drip' | 'triggered' | 'promotional' | 'transactional';
  status: 'draft' | 'scheduled' | 'running' | 'paused' | 'completed' | 'cancelled';
  template: string | null;
  message_content: Record<string, unknown>;
  audience_type: string;
  audience_filters: Record<string, unknown>;
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  messages_per_minute: number;
  delay_between_messages: number;
  total_recipients: number;
  messages_sent: number;
  messages_delivered: number;
  messages_read: number;
  messages_failed: number;
  delivery_rate: number;
  read_rate: number;
  created_at: string;
  updated_at: string;
}

export interface CampaignRecipient {
  id: string;
  phone_number: string;
  contact_name: string;
  status: 'pending' | 'sent' | 'delivered' | 'read' | 'failed' | 'skipped';
  sent_at: string | null;
  delivered_at: string | null;
  read_at: string | null;
  failed_at: string | null;
  error_code: string;
  error_message: string;
  variables: Record<string, unknown>;
}

export interface ScheduledMessage {
  id: string;
  account: string;
  to_number: string;
  contact_name: string;
  message_type: string;
  content: Record<string, unknown>;
  template: string | null;
  template_variables: Record<string, unknown>;
  scheduled_at: string;
  timezone: string;
  status: 'scheduled' | 'processing' | 'sent' | 'failed' | 'cancelled';
  message_id: string;
  whatsapp_message_id: string;
  sent_at: string | null;
  error_code: string;
  error_message: string;
  is_recurring: boolean;
  recurrence_rule: string;
  next_occurrence: string | null;
  created_at: string;
  updated_at: string;
}

export interface ContactList {
  id: string;
  account: string;
  name: string;
  description: string;
  contacts: Array<{ phone: string; name?: string; variables?: Record<string, unknown> }>;
  contact_count: number;
  source: string;
  imported_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export const campaignsService = {
  // Campaigns (WhatsApp) - usando /campaigns/ endpoint
  getCampaigns: async (params?: Record<string, string>): Promise<PaginatedResponse<Campaign>> => {
    const response = await api.get<PaginatedResponse<Campaign>>('/campaigns/campaigns/', { params });
    return response.data;
  },

  getCampaign: async (id: string): Promise<Campaign> => {
    const response = await api.get<Campaign>(`/campaigns/campaigns/${id}/`);
    return response.data;
  },

  createCampaign: async (data: {
    account_id: string;
    name: string;
    description?: string;
    campaign_type?: string;
    template_id?: string;
    message_content?: Record<string, unknown>;
    audience_filters?: Record<string, unknown>;
    contact_list?: Array<{ phone: string; name?: string; variables?: Record<string, unknown> }>;
    scheduled_at?: string;
  }): Promise<Campaign> => {
    const response = await api.post<Campaign>('/campaigns/campaigns/', data);
    return response.data;
  },

  updateCampaign: async (id: string, data: Partial<Campaign>): Promise<Campaign> => {
    const response = await api.patch<Campaign>(`/campaigns/campaigns/${id}/`, data);
    return response.data;
  },

  deleteCampaign: async (id: string): Promise<void> => {
    await api.delete(`/campaigns/campaigns/${id}/`);
  },

  scheduleCampaign: async (id: string, scheduledAt: string): Promise<Campaign> => {
    const response = await api.post<Campaign>(`/campaigns/campaigns/${id}/schedule/`, {
      scheduled_at: scheduledAt,
    });
    return response.data;
  },

  startCampaign: async (id: string): Promise<Campaign> => {
    const response = await api.post<Campaign>(`/campaigns/campaigns/${id}/start/`);
    return response.data;
  },

  pauseCampaign: async (id: string): Promise<Campaign> => {
    const response = await api.post<Campaign>(`/campaigns/campaigns/${id}/pause/`);
    return response.data;
  },

  resumeCampaign: async (id: string): Promise<Campaign> => {
    const response = await api.post<Campaign>(`/campaigns/campaigns/${id}/resume/`);
    return response.data;
  },

  cancelCampaign: async (id: string): Promise<Campaign> => {
    const response = await api.post<Campaign>(`/campaigns/campaigns/${id}/cancel/`);
    return response.data;
  },

  getCampaignStats: async (id: string): Promise<{
    id: string;
    name: string;
    status: string;
    total_recipients: number;
    messages_sent: number;
    messages_delivered: number;
    messages_read: number;
    messages_failed: number;
    delivery_rate: number;
    read_rate: number;
    pending: number;
    started_at: string | null;
    completed_at: string | null;
  }> => {
    const response = await api.get(`/campaigns/campaigns/${id}/stats/`);
    return response.data;
  },

  getCampaignRecipients: async (id: string, status?: string): Promise<CampaignRecipient[]> => {
    const params: Record<string, string> = {};
    if (status) params.status = status;
    const response = await api.get<CampaignRecipient[]>(`/campaigns/campaigns/${id}/recipients/`, { params });
    return response.data;
  },

  addRecipients: async (
    id: string,
    contacts: Array<{ phone: string; name?: string; variables?: Record<string, unknown> }>
  ): Promise<{ added: number }> => {
    const response = await api.post(`/campaigns/campaigns/${id}/add_recipients/`, { contacts });
    return response.data;
  },

  // Scheduled Messages (WhatsApp) - usando /campaigns/scheduled/ endpoint
  getScheduledMessages: async (params?: Record<string, string>): Promise<PaginatedResponse<ScheduledMessage>> => {
    const response = await api.get<PaginatedResponse<ScheduledMessage>>('/campaigns/scheduled/', { params });
    return response.data;
  },

  getScheduledMessage: async (id: string): Promise<ScheduledMessage> => {
    const response = await api.get<ScheduledMessage>(`/campaigns/scheduled/${id}/`);
    return response.data;
  },

  createScheduledMessage: async (data: {
    account_id: string;
    to_number: string;
    contact_name?: string;
    message_type?: string;
    content?: Record<string, unknown>;
    template_id?: string;
    template_variables?: Record<string, unknown>;
    scheduled_at: string;
    timezone?: string;
    is_recurring?: boolean;
    recurrence_rule?: string;
    metadata?: Record<string, unknown>;
  }): Promise<ScheduledMessage> => {
    const response = await api.post<ScheduledMessage>('/campaigns/scheduled/', data);
    return response.data;
  },

  updateScheduledMessage: async (id: string, data: Partial<ScheduledMessage>): Promise<ScheduledMessage> => {
    const response = await api.patch<ScheduledMessage>(`/campaigns/scheduled/${id}/`, data);
    return response.data;
  },

  cancelScheduledMessage: async (id: string): Promise<ScheduledMessage> => {
    const response = await api.post<ScheduledMessage>(`/campaigns/scheduled/${id}/cancel/`);
    return response.data;
  },

  getScheduledMessagesStats: async (accountId?: string): Promise<{
    total: number;
    scheduled: number;
    sent: number;
    failed: number;
    cancelled: number;
    recurring: number;
  }> => {
    const params: Record<string, string> = {};
    if (accountId) params.account_id = accountId;
    const response = await api.get('/campaigns/scheduled/stats/', { params });
    return response.data;
  },

  // Contact Lists (WhatsApp) - usando /campaigns/contacts/ endpoint
  getContactLists: async (params?: Record<string, string>): Promise<PaginatedResponse<ContactList>> => {
    const response = await api.get<PaginatedResponse<ContactList>>('/campaigns/contacts/', { params });
    return response.data;
  },

  getContactList: async (id: string): Promise<ContactList> => {
    const response = await api.get<ContactList>(`/campaigns/contacts/${id}/`);
    return response.data;
  },

  createContactList: async (data: {
    account_id: string;
    name: string;
    description?: string;
    contacts?: Array<{ phone: string; name?: string; variables?: Record<string, unknown> }>;
  }): Promise<ContactList> => {
    const response = await api.post<ContactList>('/campaigns/contacts/', data);
    return response.data;
  },

  updateContactList: async (id: string, data: Partial<ContactList>): Promise<ContactList> => {
    const response = await api.patch<ContactList>(`/campaigns/contacts/${id}/`, data);
    return response.data;
  },

  deleteContactList: async (id: string): Promise<void> => {
    await api.delete(`/campaigns/contacts/${id}/`);
  },

  importContactsFromCSV: async (data: {
    account_id: string;
    name: string;
    csv_content: string;
  }): Promise<ContactList> => {
    const response = await api.post<ContactList>('/campaigns/contacts/import_csv/', data);
    return response.data;
  },
};
