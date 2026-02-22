/**
 * Intent Detection Service
 * Serviço para estatísticas e logs de detecção de intenções
 */
import api from './api';
import type {
  IntentStats,
  IntentLog,
  AutomationStats,
  AutomationSettings,
  PaginatedResponse,
} from '../types';

export const intentService = {
  // Estatísticas de intenções
  getStats: async (params?: {
    start_date?: string;
    end_date?: string;
    company_id?: string;
  }): Promise<IntentStats> => {
    const response = await api.get('/whatsapp/intents/stats/', { params });
    return response.data;
  },

  // Logs de intenções
  getLogs: async (params?: {
    limit?: number;
    offset?: number;
    intent_type?: string;
    method?: 'regex' | 'llm';
    start_date?: string;
    end_date?: string;
    company_id?: string;
  }): Promise<PaginatedResponse<IntentLog>> => {
    const response = await api.get('/whatsapp/intents/logs/', { params });
    return response.data;
  },

  // Log específico
  getLog: async (id: string): Promise<IntentLog> => {
    const response = await api.get(`/whatsapp/intents/logs/${id}/`);
    return response.data;
  },

  // Exportar logs
  exportLogs: async (params?: {
    start_date?: string;
    end_date?: string;
    format?: 'csv' | 'json';
  }): Promise<Blob> => {
    const response = await api.get('/whatsapp/intents/logs/export/', {
      params,
      responseType: 'blob',
    });
    return response.data;
  },
};

// Automation Dashboard Service
export const automationDashboardService = {
  // Estatísticas gerais de automação
  getStats: async (params?: {
    start_date?: string;
    end_date?: string;
    company_id?: string;
  }): Promise<AutomationStats> => {
    const response = await api.get('/automation/dashboard/stats/', { params });
    return response.data;
  },

  // Configurações de automação
  getSettings: async (companyId?: string): Promise<AutomationSettings> => {
    const response = await api.get('/automation/settings/', {
      params: companyId ? { company_id: companyId } : undefined,
    });
    return response.data;
  },

  updateSettings: async (
    data: Partial<AutomationSettings>,
    companyId?: string
  ): Promise<AutomationSettings> => {
    const response = await api.patch('/automation/settings/', {
      ...data,
      company_id: companyId,
    });
    return response.data;
  },

  // Executar automação manualmente (para testes)
  triggerAutomation: async (
    eventType: string,
    data: {
      phone_number: string;
      company_id?: string;
      context?: Record<string, unknown>;
    }
  ): Promise<{
    success: boolean;
    message: string;
    automation_id?: string;
  }> => {
    const response = await api.post('/automation/trigger/', {
      event_type: eventType,
      ...data,
    });
    return response.data;
  },

  // Status dos cron jobs
  getCronStatus: async (): Promise<{
    check_pending_payments: { last_run: string; status: string };
    check_abandoned_carts: { last_run: string; status: string };
    notify_order_status: { last_run: string; status: string };
  }> => {
    const response = await api.get('/automation/cron-status/');
    return response.data;
  },
};

export default intentService;
