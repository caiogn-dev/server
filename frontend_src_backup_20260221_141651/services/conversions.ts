import api from './api';

export type ConversionEventType = 
  | 'PageView'
  | 'ViewContent'
  | 'Search'
  | 'AddToCart'
  | 'AddToWishlist'
  | 'InitiateCheckout'
  | 'AddPaymentInfo'
  | 'Purchase'
  | 'Lead'
  | 'CompleteRegistration'
  | 'Contact'
  | 'CustomizeProduct'
  | 'Donate'
  | 'FindLocation'
  | 'Schedule'
  | 'StartTrial'
  | 'SubmitApplication'
  | 'Subscribe'
  | 'WhatsAppConversation'
  | 'MessengerConversation'
  | 'InstagramConversation';

export type ConversionEventStatus = 'pending' | 'processing' | 'sent' | 'failed' | 'retrying';

export type ConversionSource = 'website' | 'whatsapp' | 'messenger' | 'instagram' | 'facebook';

export interface ConversionEvent {
  id: string;
  event_type: ConversionEventType;
  event_name: string;
  source: ConversionSource;
  status: ConversionEventStatus;
  payload: Record<string, any>;
  response_data?: Record<string, any>;
  error_message?: string;
  retry_count: number;
  max_retries: number;
  next_retry_at?: string;
  sent_at?: string;
  created_at: string;
  updated_at: string;
  
  // Related data
  customer_id?: string;
  customer_name?: string;
  order_id?: string;
  order_total?: number;
  currency?: string;
  
  // Attribution
  utm_source?: string;
  utm_medium?: string;
  utm_campaign?: string;
  utm_content?: string;
  fb_click_id?: string;
  fb_browser_id?: string;
}

export interface ConversionStats {
  total_events: number;
  by_type: Record<ConversionEventType, number>;
  by_source: Record<ConversionSource, number>;
  by_status: Record<ConversionEventStatus, number>;
  
  // Success rates
  delivery_rate: number;
  failure_rate: number;
  pending_rate: number;
  
  // Time-based stats
  events_today: number;
  events_this_week: number;
  events_this_month: number;
  
  // Retry stats
  avg_retries: number;
  events_needing_retry: number;
  
  // Value tracking (for Purchase events)
  total_revenue_tracked: number;
  avg_order_value: number;
}

export interface ConversionTimelineItem {
  timestamp: string;
  event_type: ConversionEventType;
  count: number;
  success_count: number;
  failure_count: number;
}

export interface ConversionSourceBreakdown {
  source: ConversionSource;
  total_events: number;
  sent_events: number;
  failed_events: number;
  delivery_rate: number;
  revenue?: number;
}

export interface ConversionEventTypeBreakdown {
  event_type: ConversionEventType;
  count: number;
  percentage: number;
  avg_processing_time_ms?: number;
}

export interface RetryPolicy {
  max_retries: number;
  retry_delays: number[]; // in seconds
  exponential_backoff: boolean;
}

export interface ConversionSettings {
  enabled: boolean;
  auto_retry: boolean;
  retry_policy: RetryPolicy;
  batch_size: number;
  batch_interval_seconds: number;
  track_page_view: boolean;
  track_purchase: boolean;
  track_lead: boolean;
  track_custom_events: boolean;
  custom_event_mapping: Record<string, string>;
}

export const conversionsService = {
  // Events
  getEvents: (params?: {
    status?: ConversionEventStatus;
    source?: ConversionSource;
    event_type?: ConversionEventType;
    since?: string;
    until?: string;
    limit?: number;
    offset?: number;
  }) => api.get<{ count: number; results: ConversionEvent[] }>('/marketing/conversions/events/', { params }),
  
  getEvent: (id: string) =>
    api.get<ConversionEvent>(`/marketing/conversions/events/${id}/`),
  
  retryEvent: (id: string) =>
    api.post<ConversionEvent>(`/marketing/conversions/events/${id}/retry/`),
  
  retryFailedEvents: (params?: { source?: ConversionSource; since?: string }) =>
    api.post('/marketing/conversions/events/retry-failed/', null, { params }),
  
  cancelEvent: (id: string) =>
    api.post(`/marketing/conversions/events/${id}/cancel/`),
  
  // Stats & Analytics
  getStats: (params?: { since?: string; until?: string; source?: ConversionSource }) =>
    api.get<ConversionStats>('/marketing/conversions/stats/', { params }),
  
  getTimeline: (params?: {
    since?: string;
    until?: string;
    granularity?: 'hour' | 'day' | 'week';
    event_type?: ConversionEventType;
  }) => api.get<ConversionTimelineItem[]>('/marketing/conversions/timeline/', { params }),
  
  getSourceBreakdown: (params?: { since?: string; until?: string }) =>
    api.get<ConversionSourceBreakdown[]>('/marketing/conversions/sources/', { params }),
  
  getEventTypeBreakdown: (params?: { since?: string; until?: string }) =>
    api.get<ConversionEventTypeBreakdown[]>('/marketing/conversions/event-types/', { params }),
  
  // Manual event creation
  createEvent: (data: {
    event_type: ConversionEventType;
    source: ConversionSource;
    payload: Record<string, any>;
    customer_id?: string;
    order_id?: string;
    utm_params?: {
      source?: string;
      medium?: string;
      campaign?: string;
      content?: string;
    };
  }) => api.post<ConversionEvent>('/marketing/conversions/events/', data),
  
  // Bulk operations
  createBulkEvents: (events: Array<{
    event_type: ConversionEventType;
    source: ConversionSource;
    payload: Record<string, any>;
    timestamp?: string;
  }>) => api.post('/marketing/conversions/events/bulk/', { events }),
  
  // Settings
  getSettings: (storeId?: string) =>
    api.get<ConversionSettings>('/marketing/conversions/settings/', {
      params: storeId ? { store: storeId } : undefined,
    }),
  
  updateSettings: (data: Partial<ConversionSettings>, storeId?: string) =>
    api.patch<ConversionSettings>('/marketing/conversions/settings/', data, {
      params: storeId ? { store: storeId } : undefined,
    }),
  
  // Testing
  testEvent: (data: {
    event_type: ConversionEventType;
    source: ConversionSource;
    payload: Record<string, any>;
  }) => api.post('/marketing/conversions/test/', data),
  
  // Webhook/Pixel verification
  verifyPixel: (platform: 'facebook' | 'google' | 'tiktok', pixelId: string) =>
    api.get(`/marketing/conversions/verify-pixel/`, {
      params: { platform, pixel_id: pixelId },
    }),
  
  // Export
  exportEvents: (params?: {
    since?: string;
    until?: string;
    format?: 'csv' | 'json';
    status?: ConversionEventStatus;
  }) => api.get('/marketing/conversions/export/', { params, responseType: 'blob' }),
  
  // Dashboard summary
  getDashboardSummary: (params?: { store?: string; days?: number }) =>
    api.get<{
      today: { events: number; sent: number; failed: number };
      this_week: { events: number; sent: number; failed: number };
      this_month: { events: number; sent: number; failed: number };
      top_sources: Array<{ source: ConversionSource; count: number }>;
      top_event_types: Array<{ event_type: ConversionEventType; count: number }>;
      recent_failures: ConversionEvent[];
    }>('/marketing/conversions/dashboard-summary/', { params }),
};

export default conversionsService;
