import api from './api';

export interface Notification {
  id: string;
  notification_type: 'message' | 'order' | 'payment' | 'conversation' | 'system' | 'alert';
  priority: 'low' | 'normal' | 'high' | 'urgent';
  title: string;
  message: string;
  data: Record<string, unknown>;
  related_object_type: string;
  related_object_id: string;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
}

export interface NotificationPreference {
  email_enabled: boolean;
  email_messages: boolean;
  email_orders: boolean;
  email_payments: boolean;
  email_system: boolean;
  push_enabled: boolean;
  push_messages: boolean;
  push_orders: boolean;
  push_payments: boolean;
  push_system: boolean;
  inapp_enabled: boolean;
  inapp_sound: boolean;
}

export interface PushSubscription {
  id: string;
  endpoint: string;
  p256dh_key: string;
  auth_key: string;
  user_agent: string;
  is_active: boolean;
  created_at: string;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export const notificationsService = {
  getNotifications: async (params?: Record<string, string>): Promise<PaginatedResponse<Notification>> => {
    const response = await api.get<PaginatedResponse<Notification>>('/notifications/', { params });
    return response.data;
  },

  getNotification: async (id: string): Promise<Notification> => {
    const response = await api.get<Notification>(`/notifications/${id}/`);
    return response.data;
  },

  getUnreadCount: async (): Promise<{ count: number }> => {
    const response = await api.get('/notifications/unread_count/');
    return response.data;
  },

  markAsRead: async (notificationIds?: string[], markAll?: boolean): Promise<{ marked: number }> => {
    const response = await api.post('/notifications/mark_read/', {
      notification_ids: notificationIds,
      mark_all: markAll,
    });
    return response.data;
  },

  deleteNotification: async (id: string): Promise<void> => {
    await api.delete(`/notifications/${id}/remove/`);
  },

  // Preferences
  getPreferences: async (): Promise<NotificationPreference> => {
    const response = await api.get<NotificationPreference>('/notifications/preferences/me/');
    return response.data;
  },

  updatePreferences: async (data: Partial<NotificationPreference>): Promise<NotificationPreference> => {
    const response = await api.patch<NotificationPreference>('/notifications/preferences/update_preferences/', data);
    return response.data;
  },

  // Push subscriptions
  getPushSubscriptions: async (): Promise<PushSubscription[]> => {
    const response = await api.get<PushSubscription[]>('/notifications/push/');
    return response.data;
  },

  registerPushSubscription: async (data: {
    endpoint: string;
    p256dh_key: string;
    auth_key: string;
    user_agent?: string;
  }): Promise<PushSubscription> => {
    const response = await api.post<PushSubscription>('/notifications/push/register/', data);
    return response.data;
  },

  unregisterPushSubscription: async (endpoint: string): Promise<void> => {
    await api.post('/notifications/push/unregister/', { endpoint });
  },
};
