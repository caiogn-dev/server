import api from './api';
import { PaginatedResponse } from '../types';

// Store slug for filtering products
const STORE_SLUG = import.meta.env.VITE_STORE_SLUG || 'pastita';

export interface Product {
  id: string;
  name: string;
  description?: string | null;
  price: number;
  stock_quantity: number;
  image?: string | null;
  image_url?: string | null;
  main_image?: string | null;
  main_image_url?: string | null;
  category?: string | null;
  category_name?: string | null;
  sku: string;
  is_active: boolean;
  status?: string;
  store?: string;
  metadata?: Record<string, unknown>;
  attributes?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Category {
  id: string;
  name: string;
  slug: string;
  store: string;
}

export interface CreateProduct {
  name: string;
  description?: string | null;
  price: number;
  stock_quantity: number;
  category?: string | null;
  sku: string;
  is_active?: boolean;
  image?: File | null;
  store?: string;
}

export interface UpdateProduct extends Partial<CreateProduct> {}

export interface ProductFilters {
  search?: string;
  category?: string;
  is_active?: boolean;
  ordering?: string;
  page?: number;
  page_size?: number;
  store?: string;
}

// Cache store ID and categories
let cachedStoreId: string | null = null;
let cachedCategories: Category[] | null = null;

async function getStoreId(): Promise<string> {
  if (cachedStoreId) return cachedStoreId;
  
  try {
    const response = await api.get('/stores/stores/', { params: { slug: STORE_SLUG } });
    const stores = response.data.results || response.data;
    if (stores.length > 0) {
      cachedStoreId = stores[0].id as string;
      return cachedStoreId;
    }
  } catch (error) {
    console.error('Failed to get store ID:', error);
  }
  return '';
}

async function getCategoriesWithIds(): Promise<Category[]> {
  if (cachedCategories) return cachedCategories;
  
  try {
    const response = await api.get('/stores/categories/');
    const data = response.data;
    const results = data.results || data || [];
    if (Array.isArray(results)) {
      cachedCategories = results;
      return cachedCategories;
    }
  } catch (error) {
    console.error('Failed to get categories:', error);
  }
  return [];
}

function generateSlug(name: string): string {
  return name
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

async function getCategoryIdByName(categoryName: string): Promise<string | null> {
  if (!categoryName) return null;
  
  const categories = await getCategoriesWithIds();
  const category = categories.find(
    c => c.name.toLowerCase() === categoryName.toLowerCase() || 
         c.slug.toLowerCase() === categoryName.toLowerCase()
  );
  return category?.id || null;
}

const buildProductFormData = async (data: CreateProduct | UpdateProduct, includeStore = false): Promise<FormData> => {
  const formData = new FormData();
  
  if (data.name !== undefined) {
    formData.append('name', data.name);
    // Auto-generate slug from name
    formData.append('slug', generateSlug(data.name));
  }
  if (data.description !== undefined) formData.append('description', data.description || '');
  if (data.price !== undefined) formData.append('price', String(data.price));
  if (data.stock_quantity !== undefined) formData.append('stock_quantity', String(data.stock_quantity));
  
  // Convert category name to ID
  if (data.category !== undefined) {
    const categoryId = await getCategoryIdByName(data.category || '');
    if (categoryId) {
      formData.append('category', categoryId);
    }
  }
  
  if (data.sku !== undefined) formData.append('sku', data.sku);
  if (data.is_active !== undefined) formData.append('is_active', String(data.is_active));
  
  // Include store ID
  if (includeStore || data.store !== undefined) {
    const storeId = data.store || await getStoreId();
    if (storeId) {
      formData.append('store', storeId);
    }
  }
  
  if (data.image) formData.append('image', data.image);
  return formData;
};

class ProductsService {
  private baseUrl = '/stores/products';
  private categoriesUrl = '/stores/categories';

  async getProducts(filters?: ProductFilters): Promise<PaginatedResponse<Product>> {
    const params = new URLSearchParams();
    if (filters?.search) params.append('search', filters.search);
    if (filters?.category) params.append('category', filters.category);
    if (filters?.is_active !== undefined) params.append('is_active', String(filters.is_active));
    if (filters?.ordering) params.append('ordering', filters.ordering);
    if (filters?.page) params.append('page', String(filters.page));
    if (filters?.page_size) params.append('page_size', String(filters.page_size));

    const queryString = params.toString();
    const url = queryString ? `${this.baseUrl}/?${queryString}` : `${this.baseUrl}/`;
    const response = await api.get<PaginatedResponse<Product>>(url);
    return response.data;
  }

  async getProduct(id: string): Promise<Product> {
    const response = await api.get<Product>(`${this.baseUrl}/${id}/`);
    return response.data;
  }

  async createProduct(data: CreateProduct): Promise<Product> {
    const formData = await buildProductFormData(data, true);
    const response = await api.post<Product>(`${this.baseUrl}/`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  }

  async updateProduct(id: string, data: UpdateProduct): Promise<Product> {
    const formData = await buildProductFormData(data, false);
    const response = await api.patch<Product>(`${this.baseUrl}/${id}/`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  }

  async deleteProduct(id: string): Promise<void> {
    await api.delete(`${this.baseUrl}/${id}/`);
  }

  async getCategories(): Promise<string[]> {
    try {
      const response = await api.get(`${this.categoriesUrl}/`);
      const data = response.data;
      // Handle paginated response
      const results = data.results || data || [];
      if (!Array.isArray(results)) return [];
      return results.map((cat: { name?: string; slug?: string }) => cat.name || cat.slug || '');
    } catch (error) {
      console.error('Failed to get categories:', error);
      return [];
    }
  }
}

export const productsService = new ProductsService();
export default productsService;
