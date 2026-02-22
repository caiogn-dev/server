import api from './api';
import { Payment, PaymentGateway, PaginatedResponse } from '../types';

/**
 * Payment Service
 * 
 * Updated to use the unified stores API:
 * Base URL: /api/v1/stores/payments/
 * 
 * All payment operations are now integrated with the stores app,
 * maintaining compatibility with StoreOrder while supporting
 * multiple payments per order.
 */

const BASE_URL = '/stores/payments';
const GATEWAYS_URL = `${BASE_URL}/gateways`;

export const paymentsService = {
  // ========== PAYMENTS ==========
  
  /**
   * Get all payments with optional filtering
   */
  getPayments: async (params?: Record<string, string>): Promise<PaginatedResponse<Payment>> => {
    const response = await api.get<PaginatedResponse<Payment>>(`${BASE_URL}/`, { params });
    return response.data;
  },

  /**
   * Get a single payment by ID
   */
  getPayment: async (id: string): Promise<Payment> => {
    const response = await api.get<Payment>(`${BASE_URL}/${id}/`);
    return response.data;
  },

  /**
   * Create a new payment for an order
   */
  createPayment: async (data: {
    order_id: string;
    gateway_id?: string;
    amount?: number;
    payment_method?: string;
    payer_email?: string;
    payer_name?: string;
    payer_document?: string;
    metadata?: Record<string, unknown>;
  }): Promise<Payment> => {
    const response = await api.post<Payment>(`${BASE_URL}/`, data);
    return response.data;
  },

  /**
   * Process a payment through the gateway
   */
  processPayment: async (id: string, gatewayType?: string): Promise<Payment> => {
    const response = await api.post<Payment>(`${BASE_URL}/${id}/process/`, {
      gateway_type: gatewayType,
    });
    return response.data;
  },

  /**
   * Confirm a payment as completed
   */
  confirmPayment: async (
    id: string,
    externalId?: string,
    gatewayResponse?: Record<string, unknown>
  ): Promise<Payment> => {
    const response = await api.post<Payment>(`${BASE_URL}/${id}/confirm/`, {
      external_id: externalId,
      gateway_response: gatewayResponse,
    });
    return response.data;
  },

  /**
   * Mark a payment as failed
   */
  failPayment: async (
    id: string,
    errorCode: string,
    errorMessage: string,
    gatewayResponse?: Record<string, unknown>
  ): Promise<Payment> => {
    const response = await api.post<Payment>(`${BASE_URL}/${id}/fail/`, {
      error_code: errorCode,
      error_message: errorMessage,
      gateway_response: gatewayResponse,
    });
    return response.data;
  },

  /**
   * Cancel a payment
   */
  cancelPayment: async (id: string): Promise<Payment> => {
    const response = await api.post<Payment>(`${BASE_URL}/${id}/cancel/`);
    return response.data;
  },

  /**
   * Refund a payment (partial or full)
   */
  refundPayment: async (id: string, amount?: number, reason?: string): Promise<Payment> => {
    const response = await api.post<Payment>(`${BASE_URL}/${id}/refund/`, {
      amount,
      reason,
    });
    return response.data;
  },

  /**
   * Get all payments for a specific order
   */
  getByOrder: async (orderId: string): Promise<Payment[]> => {
    const response = await api.get<Payment[]>(`${BASE_URL}/by_order/`, {
      params: { order_id: orderId },
    });
    return response.data;
  },

  /**
   * Get payment statistics
   */
  getStats: async (period: 'today' | 'week' | 'month' | 'year' = 'month'): Promise<{
    period: string;
    date_from: string;
    total_payments: number;
    status_breakdown: Array<{ status: string; count: number; total: number }>;
    completed: {
      count: number;
      amount: string;
      fees: string;
      net_amount: string;
    };
  }> => {
    const response = await api.get(`${BASE_URL}/stats/`, {
      params: { period },
    });
    return response.data;
  },

  // ========== GATEWAYS ==========
  
  /**
   * Get all payment gateways
   */
  getGateways: async (params?: Record<string, string>): Promise<PaginatedResponse<PaymentGateway>> => {
    const response = await api.get<PaginatedResponse<PaymentGateway>>(`${GATEWAYS_URL}/`, { params });
    return response.data;
  },

  /**
   * Get a single gateway by ID
   */
  getGateway: async (id: string): Promise<PaymentGateway> => {
    const response = await api.get<PaymentGateway>(`${GATEWAYS_URL}/${id}/`);
    return response.data;
  },

  /**
   * Create a new payment gateway
   */
  createGateway: async (data: {
    store: string;
    name: string;
    gateway_type: string;
    is_enabled?: boolean;
    is_sandbox?: boolean;
    is_default?: boolean;
    api_key?: string;
    api_secret?: string;
    access_token?: string;
    public_key?: string;
    webhook_secret?: string;
    endpoint_url?: string;
    webhook_url?: string;
    configuration?: Record<string, unknown>;
  }): Promise<PaymentGateway> => {
    const response = await api.post<PaymentGateway>(`${GATEWAYS_URL}/`, data);
    return response.data;
  },

  /**
   * Update a payment gateway
   */
  updateGateway: async (id: string, data: Partial<PaymentGateway>): Promise<PaymentGateway> => {
    const response = await api.patch<PaymentGateway>(`${GATEWAYS_URL}/${id}/`, data);
    return response.data;
  },

  /**
   * Delete a payment gateway (soft delete)
   */
  deleteGateway: async (id: string): Promise<void> => {
    await api.delete(`${GATEWAYS_URL}/${id}/`);
  },

  /**
   * Set a gateway as the default for its store
   */
  setDefaultGateway: async (id: string): Promise<PaymentGateway> => {
    const response = await api.post<PaymentGateway>(`${GATEWAYS_URL}/${id}/set_default/`);
    return response.data;
  },
};
