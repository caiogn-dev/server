/**
 * Reports API Service
 * Endpoints for generating reports and analytics
 */
import api from './api';
import logger from './logger';
import { getStoreSlug } from '../hooks/useStore';

const STORE_SLUG = import.meta.env.VITE_STORE_SLUG || 'pastita';
const BASE_URL = '/stores/reports';
const getStoreParam = () => getStoreSlug() || STORE_SLUG;

// =============================================================================
// TYPES
// =============================================================================

export interface DateRange {
  start_date?: string;
  end_date?: string;
  period?: '7d' | '30d' | '90d' | '1y';
}

export interface RevenueSummary {
  total_revenue: number;
  total_orders: number;
  avg_order_value: number;
  total_delivery_fees: number;
  total_discounts: number;
}

export interface RevenueDataPoint {
  period: string;
  total_revenue: number;
  order_count: number;
  avg_order_value: number;
  total_delivery_fees: number;
  total_discounts: number;
}

export interface RevenueReport {
  period: {
    start: string;
    end: string;
    group_by: 'day' | 'week' | 'month';
  };
  summary: RevenueSummary;
  data: RevenueDataPoint[];
}

export interface TopProduct {
  product_id: string | null;
  product_name: string;
  total_quantity: number;
  total_revenue: number;
  order_count: number;
  current_stock: number | null;
}

export interface ProductsReport {
  period: {
    start: string;
    end: string;
  };
  top_products: TopProduct[];
}

export interface StockProduct {
  id: string;
  name: string;
  sku: string | null;
  stock_quantity: number | null;
  price: number;
  status: string;
  category: string | null;
}

export interface StockReport {
  summary: {
    total_products: number;
    low_stock_count: number;
    out_of_stock_count: number;
    low_stock_threshold: number;
  };
  low_stock_products: StockProduct[];
  out_of_stock_products: Array<{
    id: string;
    name: string;
    sku: string | null;
    category: string | null;
  }>;
}

export interface TopCustomer {
  email: string;
  name: string;
  phone: string;
  total_spent: number;
  order_count: number;
  avg_order_value: number;
}

export interface CustomersReport {
  period: {
    start: string;
    end: string;
  };
  summary: {
    total_customers: number;
    new_customers: number;
    returning_customers: number;
    retention_rate: number;
  };
  top_customers: TopCustomer[];
}

export interface DashboardStats {
  today: {
    orders: number;
    revenue: number;
    revenue_change: number;
    revenue_change_percent: number;
  };
  week: {
    orders: number;
    revenue: number;
    avg_daily_revenue: number;
  };
  month: {
    orders: number;
    revenue: number;
    avg_daily_revenue: number;
  };
  alerts: {
    pending_orders: number;
    low_stock_products: number;
  };
  generated_at?: string;
}

// =============================================================================
// API FUNCTIONS
// =============================================================================

/**
 * Get revenue report with aggregations
 */
export const getRevenueReport = async (
  params: DateRange & { group_by?: 'day' | 'week' | 'month' } = {}
): Promise<RevenueReport> => {
  try {
    const response = await api.get(`${BASE_URL}/revenue/`, {
      params: { store: getStoreParam(), ...params }
    });
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch revenue report', error);
    throw error;
  }
};

/**
 * Get products performance report
 */
export const getProductsReport = async (params: DateRange = {}): Promise<ProductsReport> => {
  try {
    const response = await api.get(`${BASE_URL}/products/`, {
      params: { store: getStoreParam(), ...params }
    });
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch products report', error);
    throw error;
  }
};

/**
 * Get stock/inventory report
 */
export const getStockReport = async (low_stock_threshold?: number): Promise<StockReport> => {
  try {
    const response = await api.get(`${BASE_URL}/stock/`, {
      params: { store: getStoreParam(), low_stock: low_stock_threshold }
    });
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch stock report', error);
    throw error;
  }
};

/**
 * Get customers report
 */
export const getCustomersReport = async (params: DateRange = {}): Promise<CustomersReport> => {
  try {
    const response = await api.get(`${BASE_URL}/customers/`, {
      params: { store: getStoreParam(), ...params }
    });
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch customers report', error);
    throw error;
  }
};

/**
 * Get dashboard stats overview
 */
export const getDashboardStats = async (): Promise<DashboardStats> => {
  try {
    const response = await api.get(`/dashboard-stats/`, {
      params: { store: getStoreParam() }
    });
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch dashboard stats', error);
    throw error;
  }
};

/**
 * Export orders as CSV (returns blob)
 */
export const exportOrdersCSV = async (params: DateRange = {}): Promise<Blob> => {
  try {
    const response = await api.get(`${BASE_URL}/orders/export/`, {
      params: { store: getStoreParam(), ...params },
      responseType: 'blob'
    });
    return response.data;
  } catch (error) {
    logger.error('Failed to export orders', error);
    throw error;
  }
};

/**
 * Download helper - triggers file download
 */
export const downloadBlob = (blob: Blob, filename: string): void => {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};

// Export all functions
export const reportsService = {
  getRevenueReport,
  getProductsReport,
  getStockReport,
  getCustomersReport,
  getDashboardStats,
  exportOrdersCSV,
  downloadBlob
};

export default reportsService;
