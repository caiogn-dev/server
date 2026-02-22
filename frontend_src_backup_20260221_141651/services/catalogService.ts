/**
 * @deprecated This module is deprecated. Use storeApi.ts instead.
 * 
 * Catalog Service (LEGACY)
 * 
 * Complete service for managing store catalog:
 * - Products (with dynamic product types)
 * - Categories
 * - Product Types (with custom fields)
 * 
 * MIGRATION GUIDE:
 * - Import from './storeApi' instead of './catalogService'
 * - Use storeApi.getProducts() instead of catalogService.getProducts()
 * - Use storeApi.getCategories() instead of catalogService.getCategories()
 * 
 * This file will be removed in a future version.
 */
import api from './api';
import logger from './logger';

// Log deprecation warning in development
if (import.meta.env.DEV) {
  console.warn(
    '[DEPRECATED] catalogService.ts is deprecated. Please migrate to storeApi.ts. ' +
    'See the migration guide in the file header.'
  );
}

const BASE_URL = '/stores';

// =============================================================================
// TYPES
// =============================================================================

export interface Category {
  id: string;
  store: string;
  name: string;
  slug: string;
  description: string;
  image?: string;
  image_url?: string;
  parent?: string | null;
  children?: Category[];
  sort_order: number;
  is_active: boolean;
  products_count?: number;
  created_at: string;
  updated_at: string;
}

export interface CategoryInput {
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

export interface ProductTypeInput {
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

export interface ProductVariant {
  id: string;
  product: string;
  name: string;
  sku: string;
  barcode?: string;
  price?: number;
  compare_at_price?: number;
  stock_quantity: number;
  attributes: Record<string, string>;
  is_active: boolean;
}

export interface Product {
  id: string;
  store: string;
  category?: string | null;
  category_name?: string;
  product_type?: string | null;
  product_type_name?: string;
  product_type_slug?: string;
  type_attributes: Record<string, unknown>;
  
  // Basic info
  name: string;
  slug: string;
  description: string;
  short_description?: string;
  
  // SKU
  sku: string;
  barcode?: string;
  
  // Pricing
  price: number;
  compare_at_price?: number | null;
  cost_price?: number | null;
  is_on_sale?: boolean;
  discount_percentage?: number;
  
  // Stock
  track_stock: boolean;
  stock_quantity: number;
  low_stock_threshold: number;
  allow_backorder: boolean;
  is_low_stock?: boolean;
  is_in_stock?: boolean;
  
  // Status
  status: 'active' | 'inactive' | 'out_of_stock' | 'discontinued';
  featured: boolean;
  is_active?: boolean;
  
  // Images
  main_image?: string | null;
  main_image_url?: string | null;
  images: string[];
  
  // SEO
  meta_title?: string;
  meta_description?: string;
  
  // Physical
  weight?: number;
  weight_unit?: string;
  dimensions?: { length?: number; width?: number; height?: number };
  
  // Extra
  attributes: Record<string, unknown>;
  tags: string[];
  sort_order: number;
  
  // Stats
  view_count?: number;
  sold_count?: number;
  
  // Variants
  variants?: ProductVariant[];
  
  // Timestamps
  created_at: string;
  updated_at: string;
}

export interface ProductInput {
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
  compare_at_price?: number | null;
  cost_price?: number | null;
  
  track_stock?: boolean;
  stock_quantity?: number;
  low_stock_threshold?: number;
  allow_backorder?: boolean;
  
  status?: 'active' | 'inactive' | 'out_of_stock' | 'discontinued';
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

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface ProductFilters {
  store?: string;
  category?: string;
  product_type?: string;
  status?: string;
  featured?: boolean;
  search?: string;
  ordering?: string;
  page?: number;
  page_size?: number;
}

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

const generateSlug = (name: string): string => {
  return name
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
};

const buildFormData = (data: Record<string, unknown>, includeFile = true): FormData => {
  const formData = new FormData();
  
  Object.entries(data).forEach(([key, value]) => {
    if (value === null || value === undefined) return;
    
    if (key === 'main_image' && value instanceof File && includeFile) {
      formData.append(key, value);
    } else if (typeof value === 'object' && !(value instanceof File)) {
      formData.append(key, JSON.stringify(value));
    } else if (typeof value === 'boolean') {
      formData.append(key, value ? 'true' : 'false');
    } else {
      formData.append(key, String(value));
    }
  });
  
  return formData;
};

// =============================================================================
// CATEGORIES API
// =============================================================================

export const categoriesApi = {
  async list(storeId: string): Promise<Category[]> {
    try {
      const response = await api.get<PaginatedResponse<Category>>(`${BASE_URL}/categories/`, {
        params: { store: storeId, page_size: 100 }
      });
      return response.data.results || [];
    } catch (error) {
      logger.error('Failed to fetch categories', error);
      throw error;
    }
  },

  async get(id: string): Promise<Category> {
    const response = await api.get<Category>(`${BASE_URL}/categories/${id}/`);
    return response.data;
  },

  async create(data: CategoryInput): Promise<Category> {
    const payload = { ...data, slug: data.slug || generateSlug(data.name) };
    const response = await api.post<Category>(`${BASE_URL}/categories/`, payload);
    return response.data;
  },

  async update(id: string, data: Partial<CategoryInput>): Promise<Category> {
    const response = await api.patch<Category>(`${BASE_URL}/categories/${id}/`, data);
    return response.data;
  },

  async delete(id: string): Promise<void> {
    await api.delete(`${BASE_URL}/categories/${id}/`);
  },
};

// =============================================================================
// PRODUCT TYPES API
// =============================================================================

export const productTypesApi = {
  async list(storeId: string): Promise<ProductType[]> {
    try {
      const response = await api.get<PaginatedResponse<ProductType>>(`${BASE_URL}/product-types/`, {
        params: { store: storeId, page_size: 100 }
      });
      return response.data.results || [];
    } catch (error) {
      logger.error('Failed to fetch product types', error);
      throw error;
    }
  },

  async get(id: string): Promise<ProductType> {
    const response = await api.get<ProductType>(`${BASE_URL}/product-types/${id}/`);
    return response.data;
  },

  async create(data: ProductTypeInput): Promise<ProductType> {
    const payload = { ...data, slug: data.slug || generateSlug(data.name) };
    const response = await api.post<ProductType>(`${BASE_URL}/product-types/`, payload);
    return response.data;
  },

  async update(id: string, data: Partial<ProductTypeInput>): Promise<ProductType> {
    const response = await api.patch<ProductType>(`${BASE_URL}/product-types/${id}/`, data);
    return response.data;
  },

  async delete(id: string): Promise<void> {
    await api.delete(`${BASE_URL}/product-types/${id}/`);
  },
};

// =============================================================================
// PRODUCTS API
// =============================================================================

export const productsApi = {
  async list(filters: ProductFilters = {}): Promise<PaginatedResponse<Product>> {
    try {
      const params = new URLSearchParams();
      
      if (filters.store) params.append('store', filters.store);
      if (filters.category) params.append('category', filters.category);
      if (filters.product_type) params.append('product_type', filters.product_type);
      if (filters.status) params.append('status', filters.status);
      if (filters.featured !== undefined) params.append('featured', String(filters.featured));
      if (filters.search) params.append('search', filters.search);
      if (filters.ordering) params.append('ordering', filters.ordering);
      if (filters.page) params.append('page', String(filters.page));
      if (filters.page_size) params.append('page_size', String(filters.page_size));
      
      const response = await api.get<PaginatedResponse<Product>>(`${BASE_URL}/products/?${params}`);
      return response.data;
    } catch (error) {
      logger.error('Failed to fetch products', error);
      throw error;
    }
  },

  async get(id: string): Promise<Product> {
    const response = await api.get<Product>(`${BASE_URL}/products/${id}/`);
    return response.data;
  },

  async create(data: ProductInput): Promise<Product> {
    const payload = {
      ...data,
      slug: data.slug || generateSlug(data.name),
    };
    
    // Use FormData if there's an image
    if (data.main_image instanceof File) {
      const formData = buildFormData(payload);
      const response = await api.post<Product>(`${BASE_URL}/products/`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      return response.data;
    }
    
    const response = await api.post<Product>(`${BASE_URL}/products/`, payload);
    return response.data;
  },

  async update(id: string, data: Partial<ProductInput>): Promise<Product> {
    // Use FormData if there's an image
    if (data.main_image instanceof File) {
      const formData = buildFormData(data);
      const response = await api.patch<Product>(`${BASE_URL}/products/${id}/`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      return response.data;
    }
    
    const response = await api.patch<Product>(`${BASE_URL}/products/${id}/`, data);
    return response.data;
  },

  async delete(id: string): Promise<void> {
    await api.delete(`${BASE_URL}/products/${id}/`);
  },

  async toggleStatus(id: string): Promise<Product> {
    const product = await this.get(id);
    const newStatus = product.status === 'active' ? 'inactive' : 'active';
    return this.update(id, { status: newStatus });
  },

  async toggleFeatured(id: string): Promise<Product> {
    const product = await this.get(id);
    return this.update(id, { featured: !product.featured });
  },

  async updateStock(id: string, quantity: number): Promise<Product> {
    return this.update(id, { stock_quantity: quantity });
  },

  async bulkUpdateStatus(ids: string[], status: Product['status']): Promise<void> {
    await Promise.all(ids.map(id => this.update(id, { status })));
  },

  async duplicate(id: string): Promise<Product> {
    const product = await this.get(id);
    const newProduct: ProductInput = {
      store: product.store,
      category: product.category,
      product_type: product.product_type,
      type_attributes: product.type_attributes,
      name: `${product.name} (Cópia)`,
      description: product.description,
      short_description: product.short_description,
      sku: `${product.sku}-copy-${Date.now()}`,
      price: product.price,
      compare_at_price: product.compare_at_price,
      cost_price: product.cost_price,
      track_stock: product.track_stock,
      stock_quantity: 0,
      low_stock_threshold: product.low_stock_threshold,
      allow_backorder: product.allow_backorder,
      status: 'inactive',
      featured: false,
      main_image_url: product.main_image_url || undefined,
      images: product.images,
      attributes: product.attributes,
      tags: product.tags,
    };
    return this.create(newProduct);
  },
};

// =============================================================================
// CATALOG SERVICE (Combined)
// =============================================================================

export const catalogService = {
  categories: categoriesApi,
  productTypes: productTypesApi,
  products: productsApi,
  
  // Helper to load all catalog data for a store
  async loadCatalog(storeId: string) {
    const [categories, productTypes, products] = await Promise.all([
      categoriesApi.list(storeId),
      productTypesApi.list(storeId),
      productsApi.list({ store: storeId, page_size: 100 }),
    ]);
    
    return {
      categories,
      productTypes,
      products: products.results,
      totalProducts: products.count,
    };
  },
};

export default catalogService;
