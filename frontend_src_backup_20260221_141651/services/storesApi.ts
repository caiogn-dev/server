/**
 * Stores API Service
 * Comprehensive API for multi-store management
 */
import api from './api';
import logger from './logger';

// =============================================================================
// TYPES
// =============================================================================

export interface Store {
  id: string;
  name: string;
  slug: string;
  description: string;
  store_type: 'food' | 'retail' | 'services' | 'digital' | 'other';
  status: 'active' | 'inactive' | 'suspended' | 'pending';
  logo?: string;
  logo_url?: string;
  banner?: string;
  banner_url?: string;
  primary_color: string;
  secondary_color: string;
  email: string;
  phone: string;
  whatsapp_number: string;
  address: string;
  city: string;
  state: string;
  zip_code: string;
  country: string;
  latitude?: number;
  longitude?: number;
  currency: string;
  timezone: string;
  tax_rate: number;
  delivery_enabled: boolean;
  pickup_enabled: boolean;
  min_order_value: number;
  free_delivery_threshold?: number;
  default_delivery_fee: number;
  operating_hours: Record<string, { open: string; close: string }>;
  is_open: boolean;
  owner: number;
  metadata: Record<string, unknown>;
  integrations_count: number;
  products_count: number;
  orders_count: number;
  created_at: string;
  updated_at: string;
  is_active: boolean;
}

export interface StoreInput {
  name: string;
  slug: string;
  description?: string;
  store_type?: string;
  email?: string;
  phone?: string;
  whatsapp_number?: string;
  address?: string;
  city?: string;
  state?: string;
  zip_code?: string;
  currency?: string;
  timezone?: string;
  delivery_enabled?: boolean;
  pickup_enabled?: boolean;
  min_order_value?: number;
  default_delivery_fee?: number;
  metadata?: Record<string, unknown>;
}

export interface StoreIntegration {
  id: string;
  store: string;
  integration_type: 'whatsapp' | 'instagram' | 'facebook' | 'twitter' | 'telegram' | 'mercadopago' | 'stripe' | 'email' | 'webhook';
  integration_type_display: string;
  name: string;
  status: 'active' | 'inactive' | 'error' | 'pending';
  status_display: string;
  masked_api_key: string;
  masked_access_token: string;
  external_id: string;
  phone_number_id: string;
  waba_id: string;
  webhook_url: string;
  webhook_verify_token: string;
  settings: Record<string, unknown>;
  token_expires_at?: string;
  last_error: string;
  last_error_at?: string;
  created_at: string;
  updated_at: string;
  is_active: boolean;
}

export interface StoreIntegrationInput {
  store: string;
  integration_type: string;
  name: string;
  api_key?: string;
  api_secret?: string;
  access_token?: string;
  refresh_token?: string;
  external_id?: string;
  phone_number_id?: string;
  waba_id?: string;
  webhook_url?: string;
  webhook_secret?: string;
  webhook_verify_token?: string;
  settings?: Record<string, unknown>;
}

export interface StoreWebhook {
  id: string;
  store: string;
  name: string;
  url: string;
  secret: string;
  events: string[];
  headers: Record<string, string>;
  max_retries: number;
  retry_delay: number;
  total_calls: number;
  successful_calls: number;
  failed_calls: number;
  last_called_at?: string;
  last_success_at?: string;
  last_failure_at?: string;
  last_error: string;
  created_at: string;
  updated_at: string;
  is_active: boolean;
}

export interface StoreCategory {
  id: string;
  store: string;
  name: string;
  slug: string;
  description: string;
  image?: string;
  image_url?: string;
  parent?: string | null;
  children: StoreCategory[];
  sort_order: number;
  is_active: boolean;
  products_count: number;
  created_at: string;
  updated_at: string;
}

export interface StoreCategoryInput {
  store: string;
  name: string;
  slug?: string;
  description?: string;
  image?: File | null;
  parent?: string | null;
  sort_order?: number;
  is_active?: boolean;
}

export interface CustomField {
  name: string;
  label: string;
  type: 'text' | 'number' | 'select' | 'multiselect' | 'boolean' | 'textarea' | 'date' | 'color';
  required?: boolean;
  placeholder?: string;
  default_value?: string | number | boolean;
  options?: Array<{ value: string; label: string }>;
  min?: number;
  max?: number;
  step?: number;
  rows?: number;
}

export interface StoreProductVariant {
  id: string;
  product: string;
  name: string;
  sku: string;
  barcode: string;
  price?: number;
  compare_at_price?: number;
  effective_price: string;
  stock_quantity: number;
  options: Record<string, string>;
  image?: string;
  image_url?: string;
  is_active: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface StoreProduct {
  id: string;
  store: string;
  category?: string;
  category_name?: string;
  product_type?: string | null;
  product_type_name?: string;
  product_type_slug?: string;
  type_attributes?: Record<string, unknown>;
  name: string;
  slug: string;
  description: string;
  short_description: string;
  sku: string;
  barcode: string;
  price: number;
  compare_at_price?: number;
  cost_price?: number;
  is_on_sale: boolean;
  discount_percentage: number;
  track_stock: boolean;
  stock_quantity: number;
  low_stock_threshold: number;
  allow_backorder: boolean;
  is_low_stock: boolean;
  is_in_stock: boolean;
  status: 'active' | 'inactive' | 'out_of_stock' | 'discontinued';
  featured: boolean;
  main_image?: string;
  main_image_url?: string;
  images: string[];
  meta_title: string;
  meta_description: string;
  weight?: number;
  weight_unit: string;
  dimensions: { length?: number; width?: number; height?: number };
  attributes: Record<string, unknown>;
  tags: string[];
  sort_order: number;
  view_count: number;
  sold_count: number;
  variants: StoreProductVariant[];
  created_at: string;
  updated_at: string;
  is_active: boolean;
}

export interface StoreProductInput {
  store: string;
  category?: string | null;
  product_type?: string | null;
  type_attributes?: Record<string, unknown>;
  name: string;
  slug?: string;
  description?: string;
  short_description?: string;
  sku?: string;
  barcode?: string;
  price: number;
  compare_at_price?: number;
  cost_price?: number;
  track_stock?: boolean;
  stock_quantity?: number;
  low_stock_threshold?: number;
  allow_backorder?: boolean;
  status?: string;
  featured?: boolean;
  main_image?: File | null;
  main_image_url?: string;
  images?: string[];
  meta_title?: string;
  meta_description?: string;
  weight?: number;
  weight_unit?: string;
  dimensions?: { length?: number; width?: number; height?: number };
  attributes?: Record<string, unknown>;
  tags?: string[];
  sort_order?: number;
}

export interface StoreOrderItem {
  id: string;
  product?: string;
  variant?: string;
  product_name: string;
  variant_name: string;
  sku: string;
  unit_price: number;
  quantity: number;
  subtotal: number;
  options: Record<string, unknown>;
  notes: string;
  created_at: string;
}

export interface StoreOrder {
  id: string;
  store: string;
  order_number: string;
  customer?: number;
  customer_name: string;
  customer_email: string;
  customer_phone: string;
  status: string;
  status_display: string;
  payment_status: string;
  payment_status_display: string;
  subtotal: number;
  discount: number;
  coupon_code: string;
  tax: number;
  delivery_fee: number;
  total: number;
  payment_method: string;
  payment_id: string;
  payment_preference_id: string;
  pix_code: string;
  pix_qr_code: string;
  delivery_method: 'delivery' | 'pickup' | 'digital';
  delivery_method_display: string;
  delivery_address: Record<string, string>;
  delivery_notes: string;
  scheduled_date?: string;
  scheduled_time: string;
  tracking_code: string;
  tracking_url: string;
  carrier: string;
  customer_notes: string;
  internal_notes: string;
  paid_at?: string;
  shipped_at?: string;
  delivered_at?: string;
  cancelled_at?: string;
  items: StoreOrderItem[];
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  is_active: boolean;
}

export interface StoreCustomer {
  id: string;
  store: string;
  user: number;
  user_email: string;
  user_name: string;
  phone: string;
  whatsapp: string;
  instagram: string;
  twitter: string;
  facebook: string;
  addresses: Array<Record<string, string>>;
  default_address_index: number;
  default_address?: Record<string, string>;
  total_orders: number;
  total_spent: number;
  last_order_at?: string;
  tags: string[];
  notes: string;
  accepts_marketing: boolean;
  marketing_opt_in_at?: string;
  created_at: string;
  updated_at: string;
  is_active: boolean;
}

export interface StoreStats {
  orders: {
    total: number;
    today: number;
    this_week: number;
    this_month: number;
    status_breakdown: Array<{ status: string; count: number }>;
  };
  revenue: {
    total: number;
    today: number;
    this_week: number;
    this_month: number;
    average_order: number;
  };
  products: {
    total: number;
    active: number;
    low_stock: number;
  };
  customers: {
    total: number;
  };
  daily_orders: Array<{ date: string; count: number; revenue: number }>;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// =============================================================================
// API FUNCTIONS
// =============================================================================

const BASE_URL = '/stores';

const generateSlug = (name: string): string => {
  return name
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
};

const isFile = (value: unknown): value is File => {
  return typeof File !== 'undefined' && value instanceof File;
};

const buildFormData = (data: Record<string, unknown>, includeFile = true): FormData => {
  const formData = new FormData();
  Object.entries(data).forEach(([key, value]) => {
    if (value === null || value === undefined) return;
    if (isFile(value) && includeFile) {
      formData.append(key, value);
      return;
    }
    if (typeof value === 'object') {
      formData.append(key, JSON.stringify(value));
      return;
    }
    if (typeof value === 'boolean') {
      formData.append(key, value ? 'true' : 'false');
      return;
    }
    formData.append(key, String(value));
  });
  return formData;
};

// Stores
export const getStores = async (): Promise<PaginatedResponse<Store>> => {
  try {
    const response = await api.get(`${BASE_URL}/stores/`);
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch stores', error);
    throw error;
  }
};

export const getStore = async (id: string): Promise<Store> => {
  try {
    const response = await api.get(`${BASE_URL}/stores/${id}/`);
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch store', error);
    throw error;
  }
};

export const createStore = async (data: StoreInput): Promise<Store> => {
  try {
    const response = await api.post(`${BASE_URL}/stores/`, data);
    return response.data;
  } catch (error) {
    logger.error('Failed to create store', error);
    throw error;
  }
};

export const updateStore = async (id: string, data: Partial<StoreInput>): Promise<Store> => {
  try {
    const response = await api.patch(`${BASE_URL}/stores/${id}/`, data);
    return response.data;
  } catch (error) {
    logger.error('Failed to update store', error);
    throw error;
  }
};

export const deleteStore = async (id: string): Promise<void> => {
  try {
    await api.delete(`${BASE_URL}/stores/${id}/`);
  } catch (error) {
    logger.error('Failed to delete store', error);
    throw error;
  }
};

export const getStoreStats = async (id: string): Promise<StoreStats> => {
  try {
    const response = await api.get(`${BASE_URL}/stores/${id}/stats/`);
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch store stats', error);
    throw error;
  }
};

export const activateStore = async (id: string): Promise<{ status: string }> => {
  try {
    const response = await api.post(`${BASE_URL}/stores/${id}/activate/`);
    return response.data;
  } catch (error) {
    logger.error('Failed to activate store', error);
    throw error;
  }
};

export const deactivateStore = async (id: string): Promise<{ status: string }> => {
  try {
    const response = await api.post(`${BASE_URL}/stores/${id}/deactivate/`);
    return response.data;
  } catch (error) {
    logger.error('Failed to deactivate store', error);
    throw error;
  }
};

export const syncPastitaToStore = async (id: string): Promise<{ message: string; synced: Record<string, number> }> => {
  try {
    const response = await api.post(`${BASE_URL}/stores/${id}/sync_pastita/`);
    return response.data;
  } catch (error) {
    logger.error('Failed to sync Pastita to store', error);
    throw error;
  }
};

// Integrations
export const getIntegrations = async (storeId?: string): Promise<PaginatedResponse<StoreIntegration>> => {
  try {
    const params = storeId ? { store: storeId } : {};
    const response = await api.get(`${BASE_URL}/integrations/`, { params });
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch integrations', error);
    throw error;
  }
};

export const getIntegration = async (id: string): Promise<StoreIntegration> => {
  try {
    const response = await api.get(`${BASE_URL}/integrations/${id}/`);
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch integration', error);
    throw error;
  }
};

export const createIntegration = async (data: StoreIntegrationInput): Promise<StoreIntegration> => {
  try {
    const response = await api.post(`${BASE_URL}/integrations/`, data);
    return response.data;
  } catch (error) {
    logger.error('Failed to create integration', error);
    throw error;
  }
};

export const updateIntegration = async (id: string, data: Partial<StoreIntegrationInput>): Promise<StoreIntegration> => {
  try {
    const response = await api.patch(`${BASE_URL}/integrations/${id}/`, data);
    return response.data;
  } catch (error) {
    logger.error('Failed to update integration', error);
    throw error;
  }
};

export const deleteIntegration = async (id: string): Promise<void> => {
  try {
    await api.delete(`${BASE_URL}/integrations/${id}/`);
  } catch (error) {
    logger.error('Failed to delete integration', error);
    throw error;
  }
};

export const testIntegration = async (id: string): Promise<{ success: boolean; message?: string; error?: string }> => {
  try {
    const response = await api.post(`${BASE_URL}/integrations/${id}/test/`);
    return response.data;
  } catch (error) {
    logger.error('Failed to test integration', error);
    throw error;
  }
};

// Webhooks
export const getWebhooks = async (storeId?: string): Promise<PaginatedResponse<StoreWebhook>> => {
  try {
    const params = storeId ? { store: storeId } : {};
    const response = await api.get(`${BASE_URL}/webhooks/`, { params });
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch webhooks', error);
    throw error;
  }
};

export const createWebhook = async (data: Partial<StoreWebhook>): Promise<StoreWebhook> => {
  try {
    const response = await api.post(`${BASE_URL}/webhooks/`, data);
    return response.data;
  } catch (error) {
    logger.error('Failed to create webhook', error);
    throw error;
  }
};

export const updateWebhook = async (id: string, data: Partial<StoreWebhook>): Promise<StoreWebhook> => {
  try {
    const response = await api.patch(`${BASE_URL}/webhooks/${id}/`, data);
    return response.data;
  } catch (error) {
    logger.error('Failed to update webhook', error);
    throw error;
  }
};

export const deleteWebhook = async (id: string): Promise<void> => {
  try {
    await api.delete(`${BASE_URL}/webhooks/${id}/`);
  } catch (error) {
    logger.error('Failed to delete webhook', error);
    throw error;
  }
};

export const testWebhook = async (id: string): Promise<{ success: boolean; status_code?: number; response?: string; error?: string }> => {
  try {
    const response = await api.post(`${BASE_URL}/webhooks/${id}/test/`);
    return response.data;
  } catch (error) {
    logger.error('Failed to test webhook', error);
    throw error;
  }
};

// Categories
export const getCategories = async (storeId?: string): Promise<PaginatedResponse<StoreCategory>> => {
  try {
    const params = storeId ? { store: storeId, page_size: 100 } : { page_size: 100 };
    const response = await api.get(`${BASE_URL}/categories/`, { params });
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch categories', error);
    throw error;
  }
};

export const createCategory = async (data: StoreCategoryInput): Promise<StoreCategory> => {
  try {
    const payload = { ...data, slug: data.slug || generateSlug(data.name) };
    if (data.image && isFile(data.image)) {
      const formData = buildFormData(payload);
      const response = await api.post(`${BASE_URL}/categories/`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      return response.data;
    }
    const response = await api.post(`${BASE_URL}/categories/`, payload);
    return response.data;
  } catch (error) {
    logger.error('Failed to create category', error);
    throw error;
  }
};

export const updateCategory = async (id: string, data: Partial<StoreCategoryInput>): Promise<StoreCategory> => {
  try {
    if (data.image && isFile(data.image)) {
      const formData = buildFormData(data);
      const response = await api.patch(`${BASE_URL}/categories/${id}/`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      return response.data;
    }
    const response = await api.patch(`${BASE_URL}/categories/${id}/`, data);
    return response.data;
  } catch (error) {
    logger.error('Failed to update category', error);
    throw error;
  }
};

export const deleteCategory = async (id: string): Promise<void> => {
  try {
    await api.delete(`${BASE_URL}/categories/${id}/`);
  } catch (error) {
    logger.error('Failed to delete category', error);
    throw error;
  }
};

// Products
export const getProducts = async (params?: {
  store?: string;
  category?: string;
  product_type?: string;
  status?: string;
  featured?: boolean;
  search?: string;
  ordering?: string;
  page?: number;
  page_size?: number;
}): Promise<PaginatedResponse<StoreProduct>> => {
  try {
    const response = await api.get(`${BASE_URL}/products/`, { params });
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch products', error);
    throw error;
  }
};

export const getProduct = async (id: string): Promise<StoreProduct> => {
  try {
    const response = await api.get(`${BASE_URL}/products/${id}/`);
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch product', error);
    throw error;
  }
};

export const createProduct = async (data: StoreProductInput): Promise<StoreProduct> => {
  try {
    const payload = { ...data, slug: data.slug || generateSlug(data.name) };
    if (data.main_image && isFile(data.main_image)) {
      const formData = buildFormData(payload);
      const response = await api.post(`${BASE_URL}/products/`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      return response.data;
    }
    const response = await api.post(`${BASE_URL}/products/`, payload);
    return response.data;
  } catch (error) {
    logger.error('Failed to create product', error);
    throw error;
  }
};

export const updateProduct = async (id: string, data: Partial<StoreProductInput>): Promise<StoreProduct> => {
  try {
    if (data.main_image && isFile(data.main_image)) {
      const formData = buildFormData(data);
      const response = await api.patch(`${BASE_URL}/products/${id}/`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      return response.data;
    }
    const response = await api.patch(`${BASE_URL}/products/${id}/`, data);
    return response.data;
  } catch (error) {
    logger.error('Failed to update product', error);
    throw error;
  }
};

export const deleteProduct = async (id: string): Promise<void> => {
  try {
    await api.delete(`${BASE_URL}/products/${id}/`);
  } catch (error) {
    logger.error('Failed to delete product', error);
    throw error;
  }
};

export const duplicateProduct = async (id: string): Promise<StoreProduct> => {
  try {
    const response = await api.post(`${BASE_URL}/products/${id}/duplicate/`);
    return response.data;
  } catch (error) {
    logger.error('Failed to duplicate product', error);
    throw error;
  }
};

export const updateProductStock = async (
  id: string,
  quantity: number,
  operation: 'set' | 'add' | 'subtract' = 'set'
): Promise<{ stock_quantity: number; is_low_stock: boolean }> => {
  try {
    const response = await api.post(`${BASE_URL}/products/${id}/update_stock/`, { quantity, operation });
    return response.data;
  } catch (error) {
    logger.error('Failed to update product stock', error);
    throw error;
  }
};

export const getLowStockProducts = async (storeId?: string): Promise<StoreProduct[]> => {
  try {
    const params = storeId ? { store: storeId } : {};
    const response = await api.get(`${BASE_URL}/products/low_stock/`, { params });
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch low stock products', error);
    throw error;
  }
};

export const bulkUpdateProducts = async (
  productIds: string[],
  updates: { status?: string; featured?: boolean; category?: string }
): Promise<{ updated: number }> => {
  try {
    const response = await api.post(`${BASE_URL}/products/bulk_update/`, {
      product_ids: productIds,
      updates
    });
    return response.data;
  } catch (error) {
    logger.error('Failed to bulk update products', error);
    throw error;
  }
};

// Orders
export const getOrders = async (params?: {
  store?: string;
  status?: string;
  payment_status?: string;
  search?: string;
}): Promise<PaginatedResponse<StoreOrder>> => {
  try {
    const response = await api.get(`${BASE_URL}/orders/`, { params });
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch orders', error);
    throw error;
  }
};

export const getOrder = async (id: string): Promise<StoreOrder> => {
  try {
    const response = await api.get(`${BASE_URL}/orders/${id}/`);
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch order', error);
    throw error;
  }
};

export const updateOrderStatus = async (
  id: string,
  status: string,
  notify: boolean = true
): Promise<{ order_number: string; status: string; status_display: string }> => {
  try {
    const response = await api.post(`${BASE_URL}/orders/${id}/update_status/`, { status, notify });
    return response.data;
  } catch (error) {
    logger.error('Failed to update order status', error);
    throw error;
  }
};

export const markOrderPaid = async (
  id: string,
  paymentId?: string,
  paymentMethod?: string
): Promise<{ order_number: string; status: string; payment_status: string }> => {
  try {
    const response = await api.post(`${BASE_URL}/orders/${id}/mark_paid/`, {
      payment_id: paymentId,
      payment_method: paymentMethod
    });
    return response.data;
  } catch (error) {
    logger.error('Failed to mark order as paid', error);
    throw error;
  }
};

export const addOrderTracking = async (
  id: string,
  trackingCode: string,
  trackingUrl?: string,
  carrier?: string,
  markShipped?: boolean
): Promise<{ order_number: string; tracking_code: string; tracking_url: string; carrier: string }> => {
  try {
    const response = await api.post(`${BASE_URL}/orders/${id}/add_tracking/`, {
      tracking_code: trackingCode,
      tracking_url: trackingUrl,
      carrier,
      mark_shipped: markShipped
    });
    return response.data;
  } catch (error) {
    logger.error('Failed to add order tracking', error);
    throw error;
  }
};

export const cancelOrder = async (
  id: string,
  reason?: string
): Promise<{ order_number: string; status: string }> => {
  try {
    const response = await api.post(`${BASE_URL}/orders/${id}/cancel/`, { reason });
    return response.data;
  } catch (error) {
    logger.error('Failed to cancel order', error);
    throw error;
  }
};

export const refundOrder = async (
  id: string,
  amount?: number,
  reason?: string
): Promise<{ order_number: string; status: string; payment_status: string }> => {
  try {
    const response = await api.post(`${BASE_URL}/orders/${id}/refund/`, { amount, reason });
    return response.data;
  } catch (error) {
    logger.error('Failed to refund order', error);
    throw error;
  }
};

export const getOrderStats = async (storeId?: string): Promise<{
  total_orders: number;
  pending_orders: number;
  processing_orders: number;
  completed_orders: number;
  total_revenue: number;
  today_revenue: number;
  week_revenue: number;
}> => {
  try {
    const params = storeId ? { store_id: storeId } : {};
    const response = await api.get(`${BASE_URL}/orders/stats/`, { params });
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch order stats', error);
    throw error;
  }
};

// Customers
export const getCustomers = async (params?: {
  store?: string;
  search?: string;
}): Promise<PaginatedResponse<StoreCustomer>> => {
  try {
    const response = await api.get(`${BASE_URL}/customers/`, { params });
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch customers', error);
    throw error;
  }
};

export const getCustomer = async (id: string): Promise<StoreCustomer> => {
  try {
    const response = await api.get(`${BASE_URL}/customers/${id}/`);
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch customer', error);
    throw error;
  }
};

export const updateCustomer = async (id: string, data: Partial<StoreCustomer>): Promise<StoreCustomer> => {
  try {
    const response = await api.patch(`${BASE_URL}/customers/${id}/`, data);
    return response.data;
  } catch (error) {
    logger.error('Failed to update customer', error);
    throw error;
  }
};

export const getCustomerOrders = async (id: string): Promise<StoreOrder[]> => {
  try {
    const response = await api.get(`${BASE_URL}/customers/${id}/orders/`);
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch customer orders', error);
    throw error;
  }
};

// =============================================================================
// COUPON TYPES AND FUNCTIONS
// =============================================================================

export interface StoreCoupon {
  id: string;
  store: string;
  code: string;
  description: string;
  discount_type: 'percentage' | 'fixed';
  discount_type_display: string;
  discount_value: number;
  min_purchase: number;
  max_discount?: number;
  usage_limit?: number;
  usage_limit_per_user?: number;
  used_count: number;
  is_active: boolean;
  valid_from: string;
  valid_until: string;
  first_order_only: boolean;
  applicable_categories: string[];
  applicable_products: string[];
  is_valid_now: boolean;
  created_at: string;
  updated_at: string;
}

export interface StoreCouponInput {
  store: string;
  code: string;
  description?: string;
  discount_type: 'percentage' | 'fixed';
  discount_value: number;
  min_purchase?: number;
  max_discount?: number;
  usage_limit?: number;
  usage_limit_per_user?: number;
  is_active?: boolean;
  valid_from: string;
  valid_until: string;
  first_order_only?: boolean;
  applicable_categories?: string[];
  applicable_products?: string[];
}

export const getCoupons = async (storeId?: string): Promise<PaginatedResponse<StoreCoupon>> => {
  try {
    const params = storeId ? { store: storeId } : {};
    const response = await api.get(`${BASE_URL}/coupons/`, { params });
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch coupons', error);
    throw error;
  }
};

export const getCoupon = async (id: string): Promise<StoreCoupon> => {
  try {
    const response = await api.get(`${BASE_URL}/coupons/${id}/`);
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch coupon', error);
    throw error;
  }
};

export const createCoupon = async (data: StoreCouponInput): Promise<StoreCoupon> => {
  try {
    const response = await api.post(`${BASE_URL}/coupons/`, data);
    return response.data;
  } catch (error) {
    logger.error('Failed to create coupon', error);
    throw error;
  }
};

export const updateCoupon = async (id: string, data: Partial<StoreCouponInput>): Promise<StoreCoupon> => {
  try {
    const response = await api.patch(`${BASE_URL}/coupons/${id}/`, data);
    return response.data;
  } catch (error) {
    logger.error('Failed to update coupon', error);
    throw error;
  }
};

export const deleteCoupon = async (id: string): Promise<void> => {
  try {
    await api.delete(`${BASE_URL}/coupons/${id}/`);
  } catch (error) {
    logger.error('Failed to delete coupon', error);
    throw error;
  }
};

export const toggleCouponActive = async (id: string): Promise<{ id: string; is_active: boolean; message: string }> => {
  try {
    const response = await api.post(`${BASE_URL}/coupons/${id}/toggle_active/`);
    return response.data;
  } catch (error) {
    logger.error('Failed to toggle coupon', error);
    throw error;
  }
};

export const getCouponStats = async (storeId?: string): Promise<{
  total: number;
  active: number;
  expired: number;
  total_usage: number;
}> => {
  try {
    const params = storeId ? { store: storeId } : {};
    const response = await api.get(`${BASE_URL}/coupons/stats/`, { params });
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch coupon stats', error);
    throw error;
  }
};

// =============================================================================
// DELIVERY ZONE TYPES AND FUNCTIONS
// =============================================================================

export interface StoreDeliveryZone {
  id: string;
  store: string;
  name: string;
  zone_type: 'distance_band' | 'custom_distance' | 'zip_range' | 'polygon' | 'time_based';
  zone_type_display: string;
  distance_band?: string;
  distance_band_display?: string;
  min_km?: number;
  max_km?: number;
  zip_code_start?: string;
  zip_code_end?: string;
  min_minutes?: number;
  max_minutes?: number;
  polygon_coordinates: number[][];
  delivery_fee: number;
  min_fee?: number;
  fee_per_km?: number;
  estimated_minutes: number;
  estimated_days: number;
  color: string;
  is_active: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface StoreDeliveryZoneInput {
  store: string;
  name: string;
  zone_type: 'distance_band' | 'custom_distance' | 'zip_range' | 'polygon' | 'time_based';
  distance_band?: string;
  min_km?: number;
  max_km?: number;
  zip_code_start?: string;
  zip_code_end?: string;
  min_minutes?: number;
  max_minutes?: number;
  polygon_coordinates?: number[][];
  delivery_fee: number;
  min_fee?: number;
  fee_per_km?: number;
  estimated_minutes?: number;
  estimated_days?: number;
  color?: string;
  is_active?: boolean;
  sort_order?: number;
}

export const getDeliveryZones = async (storeId?: string): Promise<PaginatedResponse<StoreDeliveryZone>> => {
  try {
    const params = storeId ? { store: storeId } : {};
    const response = await api.get(`${BASE_URL}/delivery-zones/`, { params });
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch delivery zones', error);
    throw error;
  }
};

export const getDeliveryZone = async (id: string): Promise<StoreDeliveryZone> => {
  try {
    const response = await api.get(`${BASE_URL}/delivery-zones/${id}/`);
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch delivery zone', error);
    throw error;
  }
};

export const createDeliveryZone = async (data: StoreDeliveryZoneInput): Promise<StoreDeliveryZone> => {
  try {
    const response = await api.post(`${BASE_URL}/delivery-zones/`, data);
    return response.data;
  } catch (error) {
    logger.error('Failed to create delivery zone', error);
    throw error;
  }
};

export const updateDeliveryZone = async (id: string, data: Partial<StoreDeliveryZoneInput>): Promise<StoreDeliveryZone> => {
  try {
    const response = await api.patch(`${BASE_URL}/delivery-zones/${id}/`, data);
    return response.data;
  } catch (error) {
    logger.error('Failed to update delivery zone', error);
    throw error;
  }
};

export const deleteDeliveryZone = async (id: string): Promise<void> => {
  try {
    await api.delete(`${BASE_URL}/delivery-zones/${id}/`);
  } catch (error) {
    logger.error('Failed to delete delivery zone', error);
    throw error;
  }
};

export const toggleDeliveryZoneActive = async (id: string): Promise<{ id: string; is_active: boolean; message: string }> => {
  try {
    const response = await api.post(`${BASE_URL}/delivery-zones/${id}/toggle_active/`);
    return response.data;
  } catch (error) {
    logger.error('Failed to toggle delivery zone', error);
    throw error;
  }
};

export const calculateDeliveryFee = async (storeId: string, distanceKm?: number, zipCode?: string): Promise<{
  fee: string;
  zone_id?: string;
  zone_name?: string;
  estimated_minutes?: number;
  available: boolean;
}> => {
  try {
    const response = await api.post(`${BASE_URL}/delivery-zones/calculate_fee/`, {
      store: storeId,
      distance_km: distanceKm,
      zip_code: zipCode,
    });
    return response.data;
  } catch (error) {
    logger.error('Failed to calculate delivery fee', error);
    throw error;
  }
};

export const getDeliveryZoneStats = async (storeId?: string): Promise<{
  total: number;
  active: number;
  by_type: Record<string, number>;
}> => {
  try {
    const params = storeId ? { store: storeId } : {};
    const response = await api.get(`${BASE_URL}/delivery-zones/stats/`, { params });
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch delivery zone stats', error);
    throw error;
  }
};

// =============================================================================
// COMBO TYPES AND FUNCTIONS
// =============================================================================

export interface StoreComboItem {
  id: string;
  product: string;
  product_name: string;
  product_image?: string;
  variant?: string;
  quantity: number;
  allow_customization: boolean;
  customization_options: Record<string, unknown>;
}

export interface StoreCombo {
  id: string;
  store: string;
  name: string;
  slug: string;
  description: string;
  price: number;
  compare_at_price?: number;
  savings: number;
  savings_percentage: number;
  image?: string;
  image_url?: string;
  is_active: boolean;
  featured: boolean;
  track_stock: boolean;
  stock_quantity: number;
  items: StoreComboItem[];
  created_at: string;
  updated_at: string;
}

export interface StoreComboInput {
  store: string;
  name: string;
  slug?: string;
  description?: string;
  price: number;
  compare_at_price?: number;
  image_url?: string;
  is_active?: boolean;
  featured?: boolean;
  track_stock?: boolean;
  stock_quantity?: number;
}

export const getCombos = async (storeId?: string): Promise<PaginatedResponse<StoreCombo>> => {
  try {
    const params = storeId ? { store: storeId } : {};
    const response = await api.get(`${BASE_URL}/combos/`, { params });
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch combos', error);
    throw error;
  }
};

export const getCombo = async (id: string): Promise<StoreCombo> => {
  try {
    const response = await api.get(`${BASE_URL}/combos/${id}/`);
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch combo', error);
    throw error;
  }
};

export const createCombo = async (data: StoreComboInput): Promise<StoreCombo> => {
  try {
    const response = await api.post(`${BASE_URL}/combos/`, data);
    return response.data;
  } catch (error) {
    logger.error('Failed to create combo', error);
    throw error;
  }
};

export const updateCombo = async (id: string, data: Partial<StoreComboInput>): Promise<StoreCombo> => {
  try {
    const response = await api.patch(`${BASE_URL}/combos/${id}/`, data);
    return response.data;
  } catch (error) {
    logger.error('Failed to update combo', error);
    throw error;
  }
};

export const deleteCombo = async (id: string): Promise<void> => {
  try {
    await api.delete(`${BASE_URL}/combos/${id}/`);
  } catch (error) {
    logger.error('Failed to delete combo', error);
    throw error;
  }
};

// =============================================================================
// PRODUCT TYPE FUNCTIONS
// =============================================================================

export interface StoreProductType {
  id: string;
  store: string;
  name: string;
  slug: string;
  description: string;
  icon?: string;
  image?: string;
  custom_fields: CustomField[];
  sort_order: number;
  is_active: boolean;
  show_in_menu: boolean;
  products_count?: number;
  created_at: string;
  updated_at: string;
}

export interface StoreProductTypeInput {
  store: string;
  name: string;
  slug?: string;
  description?: string;
  icon?: string;
  image?: File | null;
  custom_fields?: CustomField[];
  sort_order?: number;
  is_active?: boolean;
  show_in_menu?: boolean;
}

export const getProductTypes = async (storeId?: string): Promise<PaginatedResponse<StoreProductType>> => {
  try {
    const params = storeId ? { store: storeId, page_size: 100 } : { page_size: 100 };
    const response = await api.get(`${BASE_URL}/product-types/`, { params });
    return response.data;
  } catch (error) {
    logger.error('Failed to fetch product types', error);
    throw error;
  }
};

export const createProductType = async (data: StoreProductTypeInput): Promise<StoreProductType> => {
  try {
    const payload = { ...data, slug: data.slug || generateSlug(data.name) };
    if (data.image && isFile(data.image)) {
      const formData = buildFormData(payload);
      const response = await api.post(`${BASE_URL}/product-types/`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      return response.data;
    }
    const response = await api.post(`${BASE_URL}/product-types/`, payload);
    return response.data;
  } catch (error) {
    logger.error('Failed to create product type', error);
    throw error;
  }
};

export const updateProductType = async (id: string, data: Partial<StoreProductTypeInput>): Promise<StoreProductType> => {
  try {
    if (data.image && isFile(data.image)) {
      const formData = buildFormData(data);
      const response = await api.patch(`${BASE_URL}/product-types/${id}/`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      return response.data;
    }
    const response = await api.patch(`${BASE_URL}/product-types/${id}/`, data);
    return response.data;
  } catch (error) {
    logger.error('Failed to update product type', error);
    throw error;
  }
};

export const deleteProductType = async (id: string): Promise<void> => {
  try {
    await api.delete(`${BASE_URL}/product-types/${id}/`);
  } catch (error) {
    logger.error('Failed to delete product type', error);
    throw error;
  }
};

// Export all functions
export default {
  // Stores
  getStores,
  getStore,
  createStore,
  updateStore,
  deleteStore,
  getStoreStats,
  activateStore,
  deactivateStore,
  syncPastitaToStore,
  // Integrations
  getIntegrations,
  getIntegration,
  createIntegration,
  updateIntegration,
  deleteIntegration,
  testIntegration,
  // Webhooks
  getWebhooks,
  createWebhook,
  updateWebhook,
  deleteWebhook,
  testWebhook,
  // Categories
  getCategories,
  createCategory,
  updateCategory,
  deleteCategory,
  // Products
  getProducts,
  getProduct,
  createProduct,
  updateProduct,
  deleteProduct,
  duplicateProduct,
  updateProductStock,
  getLowStockProducts,
  bulkUpdateProducts,
  // Product Types
  getProductTypes,
  createProductType,
  updateProductType,
  deleteProductType,
  // Combos
  getCombos,
  getCombo,
  createCombo,
  updateCombo,
  deleteCombo,
  // Orders
  getOrders,
  getOrder,
  updateOrderStatus,
  markOrderPaid,
  addOrderTracking,
  cancelOrder,
  refundOrder,
  getOrderStats,
  // Customers
  getCustomers,
  getCustomer,
  updateCustomer,
  getCustomerOrders,
  // Coupons
  getCoupons,
  getCoupon,
  createCoupon,
  updateCoupon,
  deleteCoupon,
  toggleCouponActive,
  getCouponStats,
  // Delivery Zones
  getDeliveryZones,
  getDeliveryZone,
  createDeliveryZone,
  updateDeliveryZone,
  deleteDeliveryZone,
  toggleDeliveryZoneActive,
  calculateDeliveryFee,
  getDeliveryZoneStats,
};
