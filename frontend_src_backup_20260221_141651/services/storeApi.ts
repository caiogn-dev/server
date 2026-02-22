/**
 * Store API Service - Multi-tenant API client
 * 
 * This is the main API service for store operations.
 * All requests are scoped to the currently selected store.
 * 
 * Architecture:
 * - Uses Zustand store for global state (selected store)
 * - All API calls automatically include store context
 * - Supports explicit store override via parameter
 * 
 * @module services/storeApi
 */

import api from './api';
import logger from './logger';
import { useStoreContextStore } from '../stores/storeContextStore';

// =============================================================================
// CONFIGURATION
// =============================================================================

const API_BASE = '/stores';
const DEFAULT_STORE = import.meta.env.VITE_STORE_SLUG || 'pastita';

// =============================================================================
// STORE CONTEXT HELPERS
// =============================================================================

/**
 * Get current store slug from global state or fallback
 */
export function getActiveStoreSlug(): string {
  const state = useStoreContextStore.getState();
  return state.selectedStore?.slug || DEFAULT_STORE;
}

/**
 * Get store slug - uses provided value or active store
 */
function resolveStore(storeSlug?: string): string {
  return storeSlug || getActiveStoreSlug();
}

// =============================================================================
// TYPES
// =============================================================================

export interface Product {
  id: number;
  name: string;
  description: string;
  price: string;
  sale_price: string | null;
  image: string | null;
  image_url: string | null;
  is_active: boolean;
  is_featured: boolean;
  stock_quantity: number;
  category: number | null;
  category_name: string;
  sort_order: number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Category {
  id: number;
  name: string;
  slug: string;
  description: string;
  image: string | null;
  sort_order: number;
  is_active: boolean;
  products_count: number;
}

export interface Order {
  id: string;
  order_number: string;
  access_token: string;
  status: OrderStatus;
  payment_status: PaymentStatus;
  payment_method: string;
  delivery_method: DeliveryMethod;
  subtotal: string;
  delivery_fee: string;
  discount: string;
  total: string;
  customer_name: string;
  customer_email: string;
  customer_phone: string;
  delivery_address: DeliveryAddress | null;
  customer_notes: string;
  delivery_notes: string;
  items: OrderItem[];
  pix_code?: string;
  pix_qr_code?: string;
  pix_ticket_url?: string;
  payment_url?: string;
  payment_link?: string;
  init_point?: string;
  payment_preference_id?: string;
  created_at: string;
  updated_at: string;
  
  // Legacy field aliases (Portuguese) - for backwards compatibility
  /** @deprecated Use customer_name instead */
  cliente_nome?: string;
  /** @deprecated Use customer_phone instead */
  cliente_telefone?: string;
  /** @deprecated Use delivery_address instead */
  endereco_entrega?: DeliveryAddress | null;
  /** @deprecated Use delivery_fee instead */
  taxa_entrega?: string;
  /** @deprecated Use discount instead */
  desconto?: string;
  /** @deprecated Use customer_notes instead */
  observacoes?: string;
}

export interface OrderItem {
  id: number;
  product_id: number;
  product_name: string;
  quantity: number;
  unit_price: string;
  total_price: string;
  notes: string;
}

export interface DeliveryAddress {
  street: string;
  number: string;
  complement: string;
  neighborhood: string;
  city: string;
  state: string;
  zip: string;
  latitude?: number;
  longitude?: number;
}

export type OrderStatus = 
  | 'pending' 
  | 'confirmed' 
  | 'preparing' 
  | 'ready' 
  | 'out_for_delivery' 
  | 'delivered' 
  | 'cancelled';

export type PaymentStatus = 
  | 'pending' 
  | 'processing'
  | 'paid' 
  | 'failed' 
  | 'refunded';

export type DeliveryMethod = 
  | 'delivery' 
  | 'pickup';

export interface Coupon {
  id: number;
  code: string;
  description: string;
  discount_type: 'percentage' | 'fixed';
  discount_value: string;
  min_order_value: string | null;
  max_discount: string | null;
  usage_limit: number | null;
  usage_count: number;
  valid_from: string;
  valid_until: string | null;
  is_active: boolean;
}

export interface DeliveryZone {
  id: number;
  name: string;
  description: string;
  zone_type: 'radius' | 'polygon' | 'isoline';
  delivery_fee: string;
  min_order_value: string;
  estimated_time_minutes: number;
  is_active: boolean;
  polygon_data: unknown;
}

export interface DashboardStats {
  total_orders: number;
  pending_orders: number;
  total_revenue: number;
  total_products: number;
  orders_today: number;
  revenue_today: number;
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

export interface ProductType {
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

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface ApiParams {
  page?: number;
  page_size?: number;
  search?: string;
  ordering?: string;
  [key: string]: unknown;
}

// =============================================================================
// API CLIENT CLASS
// =============================================================================

class StoreApiClient {
  private baseUrl = API_BASE;

  // ---------------------------------------------------------------------------
  // PRODUCTS
  // ---------------------------------------------------------------------------

  async getProducts(params: ApiParams = {}, storeSlug?: string): Promise<Product[]> {
    const store = resolveStore(storeSlug);
    try {
      const response = await api.get(`${this.baseUrl}/products/`, {
        params: { store, ...params }
      });
      return response.data.results || response.data;
    } catch (error) {
      logger.error('Failed to fetch products', { store, error });
      throw error;
    }
  }

  async getProduct(id: number, storeSlug?: string): Promise<Product> {
    const store = resolveStore(storeSlug);
    try {
      const response = await api.get(`${this.baseUrl}/products/${id}/`);
      return response.data;
    } catch (error) {
      logger.error('Failed to fetch product', { id, store, error });
      throw error;
    }
  }

  async createProduct(data: Partial<Product>, storeSlug?: string): Promise<Product> {
    const store = resolveStore(storeSlug);
    try {
      const response = await api.post(`${this.baseUrl}/products/`, {
        store,
        ...data
      });
      return response.data;
    } catch (error) {
      logger.error('Failed to create product', { store, error });
      throw error;
    }
  }

  async updateProduct(id: number, data: Partial<Product>): Promise<Product> {
    try {
      const response = await api.patch(`${this.baseUrl}/products/${id}/`, data);
      return response.data;
    } catch (error) {
      logger.error('Failed to update product', { id, error });
      throw error;
    }
  }

  async deleteProduct(id: number): Promise<void> {
    try {
      await api.delete(`${this.baseUrl}/products/${id}/`);
    } catch (error) {
      logger.error('Failed to delete product', { id, error });
      throw error;
    }
  }

  // ---------------------------------------------------------------------------
  // CATEGORIES
  // ---------------------------------------------------------------------------

  async getCategories(params: ApiParams = {}, storeSlug?: string): Promise<Category[]> {
    const store = resolveStore(storeSlug);
    try {
      const response = await api.get(`${this.baseUrl}/categories/`, {
        params: { store, ...params }
      });
      return response.data.results || response.data;
    } catch (error) {
      logger.error('Failed to fetch categories', { store, error });
      throw error;
    }
  }

  async getCategory(id: number): Promise<Category> {
    try {
      const response = await api.get(`${this.baseUrl}/categories/${id}/`);
      return response.data;
    } catch (error) {
      logger.error('Failed to fetch category', { id, error });
      throw error;
    }
  }

  async createCategory(data: Partial<Category>, storeSlug?: string): Promise<Category> {
    const store = resolveStore(storeSlug);
    try {
      const response = await api.post(`${this.baseUrl}/categories/`, {
        store,
        ...data
      });
      return response.data;
    } catch (error) {
      logger.error('Failed to create category', { store, error });
      throw error;
    }
  }

  async updateCategory(id: number, data: Partial<Category>): Promise<Category> {
    try {
      const response = await api.patch(`${this.baseUrl}/categories/${id}/`, data);
      return response.data;
    } catch (error) {
      logger.error('Failed to update category', { id, error });
      throw error;
    }
  }

  async deleteCategory(id: number): Promise<void> {
    try {
      await api.delete(`${this.baseUrl}/categories/${id}/`);
    } catch (error) {
      logger.error('Failed to delete category', { id, error });
      throw error;
    }
  }

  // ---------------------------------------------------------------------------
  // ORDERS
  // ---------------------------------------------------------------------------

  async getOrders(params: ApiParams = {}, storeSlug?: string): Promise<Order[]> {
    const store = resolveStore(storeSlug);
    try {
      const response = await api.get(`${this.baseUrl}/orders/`, {
        params: { store, ...params }
      });
      return response.data.results || response.data;
    } catch (error) {
      logger.error('Failed to fetch orders', { store, error });
      throw error;
    }
  }

  async getOrder(id: string): Promise<Order> {
    try {
      const response = await api.get(`${this.baseUrl}/orders/${id}/`);
      return response.data;
    } catch (error) {
      logger.error('Failed to fetch order', { id, error });
      throw error;
    }
  }

  async updateOrderStatus(id: string, status: OrderStatus): Promise<Order> {
    try {
      const response = await api.patch(`${this.baseUrl}/orders/${id}/`, { status });
      return response.data;
    } catch (error) {
      logger.error('Failed to update order status', { id, status, error });
      throw error;
    }
  }

  async getOrderPaymentStatus(id: string): Promise<{ status: string; payment_status: string }> {
    try {
      const response = await api.get(`${this.baseUrl}/orders/${id}/payment-status/`);
      return response.data;
    } catch (error) {
      logger.error('Failed to fetch order payment status', { id, error });
      throw error;
    }
  }

  // ---------------------------------------------------------------------------
  // COUPONS
  // ---------------------------------------------------------------------------

  async getCoupons(params: ApiParams = {}, storeSlug?: string): Promise<Coupon[]> {
    const store = resolveStore(storeSlug);
    try {
      const response = await api.get(`${this.baseUrl}/coupons/`, {
        params: { store, ...params }
      });
      return response.data.results || response.data;
    } catch (error) {
      logger.error('Failed to fetch coupons', { store, error });
      throw error;
    }
  }

  async getCoupon(id: number): Promise<Coupon> {
    try {
      const response = await api.get(`${this.baseUrl}/coupons/${id}/`);
      return response.data;
    } catch (error) {
      logger.error('Failed to fetch coupon', { id, error });
      throw error;
    }
  }

  async createCoupon(data: Partial<Coupon>, storeSlug?: string): Promise<Coupon> {
    const store = resolveStore(storeSlug);
    try {
      const response = await api.post(`${this.baseUrl}/coupons/`, {
        store,
        ...data
      });
      return response.data;
    } catch (error) {
      logger.error('Failed to create coupon', { store, error });
      throw error;
    }
  }

  async updateCoupon(id: number, data: Partial<Coupon>): Promise<Coupon> {
    try {
      const response = await api.patch(`${this.baseUrl}/coupons/${id}/`, data);
      return response.data;
    } catch (error) {
      logger.error('Failed to update coupon', { id, error });
      throw error;
    }
  }

  async deleteCoupon(id: number): Promise<void> {
    try {
      await api.delete(`${this.baseUrl}/coupons/${id}/`);
    } catch (error) {
      logger.error('Failed to delete coupon', { id, error });
      throw error;
    }
  }

  async validateCoupon(code: string, storeSlug?: string): Promise<Coupon> {
    const store = resolveStore(storeSlug);
    try {
      const response = await api.post(`${this.baseUrl}/coupons/validate/`, {
        code,
        store
      });
      return response.data;
    } catch (error) {
      logger.error('Failed to validate coupon', { code, store, error });
      throw error;
    }
  }

  // ---------------------------------------------------------------------------
  // DELIVERY ZONES
  // ---------------------------------------------------------------------------

  async getDeliveryZones(params: ApiParams = {}, storeSlug?: string): Promise<DeliveryZone[]> {
    const store = resolveStore(storeSlug);
    try {
      const response = await api.get(`${this.baseUrl}/delivery-zones/`, {
        params: { store, ...params }
      });
      return response.data.results || response.data;
    } catch (error) {
      logger.error('Failed to fetch delivery zones', { store, error });
      throw error;
    }
  }

  async getDeliveryZone(id: number): Promise<DeliveryZone> {
    try {
      const response = await api.get(`${this.baseUrl}/delivery-zones/${id}/`);
      return response.data;
    } catch (error) {
      logger.error('Failed to fetch delivery zone', { id, error });
      throw error;
    }
  }

  async createDeliveryZone(data: Partial<DeliveryZone>, storeSlug?: string): Promise<DeliveryZone> {
    const store = resolveStore(storeSlug);
    try {
      const response = await api.post(`${this.baseUrl}/delivery-zones/`, {
        store,
        ...data
      });
      return response.data;
    } catch (error) {
      logger.error('Failed to create delivery zone', { store, error });
      throw error;
    }
  }

  async updateDeliveryZone(id: number, data: Partial<DeliveryZone>): Promise<DeliveryZone> {
    try {
      const response = await api.patch(`${this.baseUrl}/delivery-zones/${id}/`, data);
      return response.data;
    } catch (error) {
      logger.error('Failed to update delivery zone', { id, error });
      throw error;
    }
  }

  async deleteDeliveryZone(id: number): Promise<void> {
    try {
      await api.delete(`${this.baseUrl}/delivery-zones/${id}/`);
    } catch (error) {
      logger.error('Failed to delete delivery zone', { id, error });
      throw error;
    }
  }

  // ---------------------------------------------------------------------------
  // DASHBOARD & STATS
  // ---------------------------------------------------------------------------

  async getDashboardStats(storeSlug?: string): Promise<DashboardStats> {
    const store = resolveStore(storeSlug);
    try {
      const response = await api.get(`${this.baseUrl}/dashboard/stats/`, {
        params: { store }
      });
      return response.data;
    } catch (error) {
      logger.error('Failed to fetch dashboard stats', { store, error });
      throw error;
    }
  }

  async getCatalog(storeSlug?: string): Promise<{ categories: Category[]; products: Product[] }> {
    const store = resolveStore(storeSlug);
    try {
      const response = await api.get(`${this.baseUrl}/s/${store}/catalog/`);
      return response.data;
    } catch (error) {
      logger.error('Failed to fetch catalog', { store, error });
      throw error;
    }
  }

  // ---------------------------------------------------------------------------
  // PRODUCT TYPES
  // ---------------------------------------------------------------------------

  async getProductTypes(params: ApiParams = {}, storeSlug?: string): Promise<ProductType[]> {
    const store = resolveStore(storeSlug);
    try {
      const response = await api.get(`${this.baseUrl}/s/${store}/product-types/`, { params });
      return response.data.results || response.data;
    } catch (error) {
      logger.error('Failed to fetch product types', { store, error });
      throw error;
    }
  }

  async getProductType(id: string, storeSlug?: string): Promise<ProductType> {
    const store = resolveStore(storeSlug);
    try {
      const response = await api.get(`${this.baseUrl}/s/${store}/product-types/${id}/`);
      return response.data;
    } catch (error) {
      logger.error('Failed to fetch product type', { id, error });
      throw error;
    }
  }

  async createProductType(data: Partial<ProductType>, storeSlug?: string): Promise<ProductType> {
    const store = resolveStore(storeSlug);
    try {
      const response = await api.post(`${this.baseUrl}/s/${store}/product-types/`, data);
      logger.info('Product type created', { id: response.data.id });
      return response.data;
    } catch (error) {
      logger.error('Failed to create product type', { error });
      throw error;
    }
  }

  async updateProductType(id: string, data: Partial<ProductType>): Promise<ProductType> {
    try {
      const response = await api.patch(`${this.baseUrl}/product-types/${id}/`, data);
      logger.info('Product type updated', { id });
      return response.data;
    } catch (error) {
      logger.error('Failed to update product type', { id, error });
      throw error;
    }
  }

  async deleteProductType(id: string): Promise<void> {
    try {
      await api.delete(`${this.baseUrl}/product-types/${id}/`);
      logger.info('Product type deleted', { id });
    } catch (error) {
      logger.error('Failed to delete product type', { id, error });
      throw error;
    }
  }
}

// =============================================================================
// SINGLETON EXPORT
// =============================================================================

export const storeApi = new StoreApiClient();

// =============================================================================
// REACT HOOK FOR STORE-AWARE API
// =============================================================================

import { useMemo } from 'react';

/**
 * React hook that provides store-aware API methods
 * Automatically uses the currently selected store
 */
export function useStoreApi() {
  const selectedStore = useStoreContextStore(state => state.selectedStore);
  
  return useMemo(() => ({
    storeSlug: selectedStore?.slug || DEFAULT_STORE,
    storeName: selectedStore?.name || 'Loja',
    
    // Products
    getProducts: (params?: ApiParams) => storeApi.getProducts(params, selectedStore?.slug),
    getProduct: (id: number) => storeApi.getProduct(id, selectedStore?.slug),
    createProduct: (data: Partial<Product>) => storeApi.createProduct(data, selectedStore?.slug),
    updateProduct: storeApi.updateProduct.bind(storeApi),
    deleteProduct: storeApi.deleteProduct.bind(storeApi),
    
    // Categories
    getCategories: (params?: ApiParams) => storeApi.getCategories(params, selectedStore?.slug),
    getCategory: storeApi.getCategory.bind(storeApi),
    createCategory: (data: Partial<Category>) => storeApi.createCategory(data, selectedStore?.slug),
    updateCategory: storeApi.updateCategory.bind(storeApi),
    deleteCategory: storeApi.deleteCategory.bind(storeApi),
    
    // Orders
    getOrders: (params?: ApiParams) => storeApi.getOrders(params, selectedStore?.slug),
    getOrder: storeApi.getOrder.bind(storeApi),
    updateOrderStatus: storeApi.updateOrderStatus.bind(storeApi),
    getOrderPaymentStatus: storeApi.getOrderPaymentStatus.bind(storeApi),
    
    // Coupons
    getCoupons: (params?: ApiParams) => storeApi.getCoupons(params, selectedStore?.slug),
    getCoupon: storeApi.getCoupon.bind(storeApi),
    createCoupon: (data: Partial<Coupon>) => storeApi.createCoupon(data, selectedStore?.slug),
    updateCoupon: storeApi.updateCoupon.bind(storeApi),
    deleteCoupon: storeApi.deleteCoupon.bind(storeApi),
    validateCoupon: (code: string) => storeApi.validateCoupon(code, selectedStore?.slug),
    
    // Delivery Zones
    getDeliveryZones: (params?: ApiParams) => storeApi.getDeliveryZones(params, selectedStore?.slug),
    getDeliveryZone: storeApi.getDeliveryZone.bind(storeApi),
    createDeliveryZone: (data: Partial<DeliveryZone>) => storeApi.createDeliveryZone(data, selectedStore?.slug),
    updateDeliveryZone: storeApi.updateDeliveryZone.bind(storeApi),
    deleteDeliveryZone: storeApi.deleteDeliveryZone.bind(storeApi),
    
    // Product Types
    getProductTypes: (params?: ApiParams) => storeApi.getProductTypes(params, selectedStore?.slug),
    getProductType: (id: string) => storeApi.getProductType(id, selectedStore?.slug),
    createProductType: (data: Partial<ProductType>) => storeApi.createProductType(data, selectedStore?.slug),
    updateProductType: storeApi.updateProductType.bind(storeApi),
    deleteProductType: storeApi.deleteProductType.bind(storeApi),
    
    // Dashboard
    getDashboardStats: () => storeApi.getDashboardStats(selectedStore?.slug),
    getCatalog: () => storeApi.getCatalog(selectedStore?.slug),
  }), [selectedStore]);
}

export default storeApi;
