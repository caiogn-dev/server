import api from './api';
import {
  ScheduledMessage,
  CreateScheduledMessage,
  ScheduledMessageStats,
  ReportSchedule,
  CreateReportSchedule,
  GeneratedReport,
  GenerateReportRequest,
  PaginatedResponse,
} from '../types';

const BASE_URL = '/automation';

// Scheduled Messages API
export const scheduledMessagesService = {
  list: async (params: Record<string, string> = {}): Promise<PaginatedResponse<ScheduledMessage>> => {
    const response = await api.get(`${BASE_URL}/scheduled-messages/`, { params });
    return response.data;
  },

  get: async (id: string): Promise<ScheduledMessage> => {
    const response = await api.get(`${BASE_URL}/scheduled-messages/${id}/`);
    return response.data;
  },

  create: async (data: CreateScheduledMessage): Promise<ScheduledMessage> => {
    const response = await api.post(`${BASE_URL}/scheduled-messages/`, data);
    return response.data;
  },

  update: async (id: string, data: Partial<CreateScheduledMessage>): Promise<ScheduledMessage> => {
    const response = await api.patch(`${BASE_URL}/scheduled-messages/${id}/`, data);
    return response.data;
  },

  delete: async (id: string): Promise<void> => {
    await api.delete(`${BASE_URL}/scheduled-messages/${id}/`);
  },

  cancel: async (id: string): Promise<{ success: boolean; message: string }> => {
    const response = await api.post(`${BASE_URL}/scheduled-messages/${id}/cancel/`);
    return response.data;
  },

  reschedule: async (id: string, scheduledAt: string): Promise<ScheduledMessage> => {
    const response = await api.post(`${BASE_URL}/scheduled-messages/${id}/reschedule/`, {
      scheduled_at: scheduledAt,
    });
    return response.data;
  },

  getStats: async (accountId?: string): Promise<ScheduledMessageStats> => {
    const params = accountId ? { account_id: accountId } : {};
    const response = await api.get(`${BASE_URL}/scheduled-messages/stats/`, { params });
    return response.data;
  },
};

// Report Schedules API
export const reportSchedulesService = {
  list: async (params: Record<string, string> = {}): Promise<PaginatedResponse<ReportSchedule>> => {
    const response = await api.get(`${BASE_URL}/report-schedules/`, { params });
    return response.data;
  },

  get: async (id: string): Promise<ReportSchedule> => {
    const response = await api.get(`${BASE_URL}/report-schedules/${id}/`);
    return response.data;
  },

  create: async (data: CreateReportSchedule): Promise<ReportSchedule> => {
    const response = await api.post(`${BASE_URL}/report-schedules/`, data);
    return response.data;
  },

  update: async (id: string, data: Partial<CreateReportSchedule>): Promise<ReportSchedule> => {
    const response = await api.patch(`${BASE_URL}/report-schedules/${id}/`, data);
    return response.data;
  },

  delete: async (id: string): Promise<void> => {
    await api.delete(`${BASE_URL}/report-schedules/${id}/`);
  },

  runNow: async (id: string): Promise<{ success: boolean; message: string; task_id: string }> => {
    const response = await api.post(`${BASE_URL}/report-schedules/${id}/run_now/`);
    return response.data;
  },

  pause: async (id: string): Promise<{ success: boolean; message: string }> => {
    const response = await api.post(`${BASE_URL}/report-schedules/${id}/pause/`);
    return response.data;
  },

  resume: async (id: string): Promise<{ success: boolean; message: string }> => {
    const response = await api.post(`${BASE_URL}/report-schedules/${id}/resume/`);
    return response.data;
  },
};

// Generated Reports API
export const generatedReportsService = {
  list: async (params: Record<string, string> = {}): Promise<PaginatedResponse<GeneratedReport>> => {
    const response = await api.get(`${BASE_URL}/reports/`, { params });
    return response.data;
  },

  get: async (id: string): Promise<GeneratedReport> => {
    const response = await api.get(`${BASE_URL}/reports/${id}/`);
    return response.data;
  },

  generate: async (data: GenerateReportRequest): Promise<{ success: boolean; message: string; task_id: string }> => {
    const response = await api.post(`${BASE_URL}/reports/generate/`, data);
    return response.data;
  },

  download: async (id: string): Promise<Blob> => {
    const response = await api.get(`${BASE_URL}/reports/${id}/download/`, {
      responseType: 'blob',
    });
    return response.data;
  },

  resendEmail: async (id: string, recipients?: string[]): Promise<{ success: boolean; message: string }> => {
    const response = await api.post(`${BASE_URL}/reports/${id}/resend_email/`, {
      recipients,
    });
    return response.data;
  },
};

export default {
  scheduledMessages: scheduledMessagesService,
  reportSchedules: reportSchedulesService,
  generatedReports: generatedReportsService,
};
