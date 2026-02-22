import api from './api';
import { ExportParams } from '../types';
import { getStoreSlug } from '../hooks/useStore';

export const exportService = {
  exportMessages: async (params: ExportParams = {}): Promise<Blob> => {
    const response = await api.get('/export/messages/', {
      params,
      responseType: 'blob',
    });
    return response.data;
  },

  exportOrders: async (params: ExportParams = {}): Promise<Blob> => {
    const store = params.store || getStoreSlug();
    const response = await api.get('/stores/reports/orders/export/', {
      params: { ...params, store: store || params.store },
      responseType: 'blob',
    });
    return response.data;
  },

  exportSessions: async (params: ExportParams = {}): Promise<Blob> => {
    const response = await api.get('/export/sessions/', {
      params,
      responseType: 'blob',
    });
    return response.data;
  },

  exportAutomationLogs: async (params: ExportParams = {}): Promise<Blob> => {
    const response = await api.get('/export/automation-logs/', {
      params,
      responseType: 'blob',
    });
    return response.data;
  },

  exportConversations: async (params: ExportParams = {}): Promise<Blob> => {
    const response = await api.get('/export/conversations/', {
      params,
      responseType: 'blob',
    });
    return response.data;
  },

  downloadBlob: (blob: Blob, filename: string) => {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
};

export default exportService;
