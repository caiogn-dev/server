import api from './api';
import { DashboardOverview, DashboardActivity, DashboardCharts } from '../types';

export const dashboardService = {
  getOverview: async (accountId?: string): Promise<DashboardOverview> => {
    const params = accountId ? { account_id: accountId } : {};
    const response = await api.get<DashboardOverview>('/dashboard/overview/', { params });
    return response.data;
  },

  getActivity: async (accountId?: string, limit?: number): Promise<DashboardActivity> => {
    const params: Record<string, string | number> = {};
    if (accountId) params.account_id = accountId;
    if (limit) params.limit = limit;
    const response = await api.get<DashboardActivity>('/dashboard/activity/', { params });
    return response.data;
  },

  getCharts: async (accountId?: string, days?: number): Promise<DashboardCharts> => {
    const params: Record<string, string | number> = {};
    if (accountId) params.account_id = accountId;
    if (days) params.days = days;
    const response = await api.get<DashboardCharts>('/dashboard/charts/', { params });
    return response.data;
  },
};
