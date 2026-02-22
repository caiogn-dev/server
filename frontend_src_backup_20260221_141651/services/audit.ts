import api from './api';

export interface AuditLog {
  id: string;
  user_email: string;
  user_ip: string;
  action: string;
  action_description: string;
  object_repr: string;
  old_values: Record<string, unknown>;
  new_values: Record<string, unknown>;
  changes: Record<string, { old: unknown; new: unknown }>;
  module: string;
  extra_data: Record<string, unknown>;
  request_path: string;
  request_method: string;
  created_at: string;
}

export interface DataExportLog {
  id: string;
  export_type: string;
  export_format: 'csv' | 'excel' | 'json' | 'pdf';
  status: 'pending' | 'processing' | 'completed' | 'failed';
  filters: Record<string, unknown>;
  total_records: number;
  file_size: number;
  download_url: string;
  started_at: string | null;
  completed_at: string | null;
  expires_at: string | null;
  error_message: string;
  created_at: string;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export const auditService = {
  // Audit Logs
  getAuditLogs: async (params?: Record<string, string>): Promise<PaginatedResponse<AuditLog>> => {
    const response = await api.get<PaginatedResponse<AuditLog>>('/audit/logs/', { params });
    return response.data;
  },

  getAuditLog: async (id: string): Promise<AuditLog> => {
    const response = await api.get<AuditLog>(`/audit/logs/${id}/`);
    return response.data;
  },

  getMyActivity: async (days?: number, limit?: number): Promise<AuditLog[]> => {
    const params: Record<string, string | number> = {};
    if (days) params.days = days;
    if (limit) params.limit = limit;
    const response = await api.get<AuditLog[]>('/audit/logs/my_activity/', { params });
    return response.data;
  },

  getObjectHistory: async (type: string, id: string): Promise<AuditLog[]> => {
    const response = await api.get<AuditLog[]>('/audit/logs/object_history/', {
      params: { type, id },
    });
    return response.data;
  },

  // Exports
  getExports: async (params?: Record<string, string>): Promise<PaginatedResponse<DataExportLog>> => {
    const response = await api.get<PaginatedResponse<DataExportLog>>('/audit/exports/', { params });
    return response.data;
  },

  getExport: async (id: string): Promise<DataExportLog> => {
    const response = await api.get<DataExportLog>(`/audit/exports/${id}/`);
    return response.data;
  },

  exportData: async (data: {
    export_type: 'messages' | 'orders' | 'conversations' | 'payments';
    export_format: 'csv' | 'excel';
    filters?: Record<string, unknown>;
  }): Promise<Blob> => {
    const response = await api.post('/audit/exports/export/', data, {
      responseType: 'blob',
    });
    return response.data;
  },
};
