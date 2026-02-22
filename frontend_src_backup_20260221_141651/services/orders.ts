import api from './api';
import { Order, OrderItem, OrderEvent, CreateOrder, PaginatedResponse } from '../types';

/**
 * Orders Service - Uses ONLY /stores/orders/ API (unified system)
 * No legacy fallbacks - all orders go through the stores system
 */

const BASE_URL = '/stores/orders';

const toNumber = (value: number | string | null | undefined) => {
  if (value === null || value === undefined) return 0;
  return typeof value === 'string' ? Number(value) : value;
};

const normalizeOrder = (order: Order): Order => ({
  ...order,
  subtotal: toNumber(order.subtotal),
  discount: toNumber(order.discount),
  delivery_fee: order.delivery_fee !== undefined && order.delivery_fee !== null
    ? toNumber(order.delivery_fee)
    : order.delivery_fee,
  tax: toNumber(order.tax),
  total: toNumber(order.total),
  items_count: order.items_count ?? order.items?.length ?? 0,
});

export const ordersService = {
  getOrders: async (params?: Record<string, string>): Promise<PaginatedResponse<Order>> => {
    const response = await api.get<PaginatedResponse<Order>>(`${BASE_URL}/`, { params });
    const results = response.data.results?.map(normalizeOrder) || [];
    return { ...response.data, results };
  },

  getOrder: async (id: string): Promise<Order> => {
    const response = await api.get<Order>(`${BASE_URL}/${id}/`);
    return normalizeOrder(response.data);
  },

  createOrder: async (data: CreateOrder): Promise<Order> => {
    const response = await api.post<Order>(`${BASE_URL}/`, data);
    return normalizeOrder(response.data);
  },

  updateOrder: async (id: string, data: Partial<Order>): Promise<Order> => {
    const response = await api.patch<Order>(`${BASE_URL}/${id}/`, data);
    return normalizeOrder(response.data);
  },

  deleteOrder: async (id: string): Promise<void> => {
    await api.delete(`${BASE_URL}/${id}/`);
  },

  confirmOrder: async (id: string): Promise<Order> => {
    const response = await api.post<Order>(`${BASE_URL}/${id}/update_status/`, { status: 'confirmed' });
    return normalizeOrder(response.data);
  },

  markAwaitingPayment: async (id: string): Promise<Order> => {
    const response = await api.post<Order>(`${BASE_URL}/${id}/update_status/`, { status: 'processing' });
    return normalizeOrder(response.data);
  },

  markPaid: async (id: string, paymentReference?: string, paymentMethod?: string): Promise<Order> => {
    const response = await api.post<Order>(`${BASE_URL}/${id}/mark_paid/`, {
      payment_id: paymentReference,
      payment_method: paymentMethod,
    });
    return normalizeOrder(response.data);
  },

  shipOrder: async (id: string, trackingCode?: string, carrier?: string): Promise<Order> => {
    const response = await api.post<Order>(`${BASE_URL}/${id}/add_tracking/`, {
      tracking_code: trackingCode,
      carrier: carrier,
    });
    return normalizeOrder(response.data);
  },

  deliverOrder: async (id: string): Promise<Order> => {
    const response = await api.post<Order>(`${BASE_URL}/${id}/update_status/`, { status: 'delivered' });
    return normalizeOrder(response.data);
  },

  startProcessing: async (id: string): Promise<Order> => {
    const response = await api.post<Order>(`${BASE_URL}/${id}/update_status/`, { status: 'processing' });
    return normalizeOrder(response.data);
  },

  startPreparing: async (id: string): Promise<Order> => {
    const response = await api.post<Order>(`${BASE_URL}/${id}/update_status/`, { status: 'preparing' });
    return normalizeOrder(response.data);
  },

  markReady: async (id: string): Promise<Order> => {
    const response = await api.post<Order>(`${BASE_URL}/${id}/update_status/`, { status: 'ready' });
    return normalizeOrder(response.data);
  },

  markOutForDelivery: async (id: string): Promise<Order> => {
    const response = await api.post<Order>(`${BASE_URL}/${id}/update_status/`, { status: 'out_for_delivery' });
    return normalizeOrder(response.data);
  },

  cancelOrder: async (id: string, reason?: string): Promise<Order> => {
    const response = await api.post<Order>(`${BASE_URL}/${id}/cancel/`, { reason });
    return normalizeOrder(response.data);
  },

  updateStatus: async (id: string, status: string): Promise<Order> => {
    const response = await api.post<Order>(`${BASE_URL}/${id}/update_status/`, { status });
    return normalizeOrder(response.data);
  },

  addItem: async (
    _id: string,
    _item: {
      product_name: string;
      product_id?: string;
      product_sku?: string;
      quantity: number;
      unit_price: number;
      notes?: string;
    }
  ): Promise<OrderItem> => {
    throw new Error('addItem is not supported by the current stores API.');
  },

  removeItem: async (_orderId: string, _itemId: string): Promise<void> => {
    throw new Error('removeItem is not supported by the current stores API.');
  },

  updateShipping: async (
    id: string,
    shippingAddress: Record<string, unknown>,
    shippingCost?: number
  ): Promise<Order> => {
    const response = await api.patch<Order>(`${BASE_URL}/${id}/`, {
      delivery_address: shippingAddress,
      delivery_fee: shippingCost,
    });
    return normalizeOrder(response.data);
  },

  addNote: async (id: string, note: string, isInternal?: boolean): Promise<Order> => {
    const response = await api.post<Order>(`${BASE_URL}/${id}/add_note/`, {
      note,
      is_internal: isInternal,
    });
    return normalizeOrder(response.data);
  },

  getEvents: async (id: string): Promise<OrderEvent[]> => {
    const response = await api.get<OrderEvent[]>(`${BASE_URL}/${id}/history/`);
    return response.data;
  },

  getStats: async (storeId?: string): Promise<Record<string, unknown>> => {
    const params: Record<string, string> = {};
    if (storeId) params.store = storeId;
    const response = await api.get(`${BASE_URL}/stats/`, { params });
    return response.data;
  },

  getByCustomer: async (phone: string, storeId?: string): Promise<Order[]> => {
    const params: Record<string, string> = { search: phone };
    if (storeId) params.store = storeId;
    const response = await api.get<PaginatedResponse<Order>>(`${BASE_URL}/`, { params });
    return response.data.results?.map(normalizeOrder) || [];
  },
};
