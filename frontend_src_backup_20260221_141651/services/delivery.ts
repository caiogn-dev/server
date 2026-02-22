import api from './api';
import { PaginatedResponse } from '../types';

export interface DeliveryZone {
  id: string;
  store?: string | null;
  store_name?: string | null;
  name: string;
  zone_type?: string;
  distance_band?: string | null;
  distance_label?: string | null;
  min_km?: number | null;
  max_km?: number | null;
  min_minutes?: number | null;
  max_minutes?: number | null;
  delivery_fee: number;
  fee_per_km?: number | null;
  estimated_days: number;
  estimated_minutes?: number;
  color?: string;
  polygon_coordinates?: number[][];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateDeliveryZone {
  store?: string | null;
  name: string;
  zone_type?: string;
  distance_band?: string;
  min_km?: number | null;
  max_km?: number | null;
  min_minutes?: number | null;
  max_minutes?: number | null;
  delivery_fee: number;
  fee_per_km?: number | null;
  estimated_days?: number;
  estimated_minutes?: number;
  color?: string;
  polygon_coordinates?: number[][];
  is_active?: boolean;
}

export interface UpdateDeliveryZone {
  store?: string | null;
  name?: string;
  zone_type?: string;
  distance_band?: string;
  min_km?: number | null;
  max_km?: number | null;
  min_minutes?: number | null;
  max_minutes?: number | null;
  delivery_fee?: number;
  fee_per_km?: number | null;
  estimated_days?: number;
  estimated_minutes?: number;
  color?: string;
  polygon_coordinates?: number[][];
  is_active?: boolean;
}

export interface DeliveryZoneStats {
  total: number;
  active: number;
  inactive: number;
  avg_fee: number;
  avg_days: number;
}

export interface StoreLocation {
  id: string;
  name: string;
  zip_code: string;
  address: string;
  city: string;
  state: string;
  latitude: number | null;
  longitude: number | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface UpdateStoreLocation {
  name?: string;
  zip_code: string;
  address?: string;
  city?: string;
  state?: string;
}

export interface DeliveryZoneFilters {
  store?: string;
  is_active?: boolean;
  zone_type?: string;
  search?: string;
  page?: number;
  page_size?: number;
}

class DeliveryService {
  private baseUrl = '/stores/delivery-zones';
  private storeUrl = '/stores/stores';
  private storeSlug = import.meta.env.VITE_STORE_SLUG || 'pastita';

  async getZones(filters?: DeliveryZoneFilters): Promise<PaginatedResponse<DeliveryZone>> {
    const params = new URLSearchParams();
    
    // Store filter - critical for multi-store support
    if (filters?.store) {
      params.append('store', filters.store);
    }
    if (filters?.is_active !== undefined) {
      params.append('is_active', String(filters.is_active));
    }
    if (filters?.zone_type) {
      params.append('zone_type', filters.zone_type);
    }
    if (filters?.search) {
      params.append('search', filters.search);
    }
    if (filters?.page) {
      params.append('page', String(filters.page));
    }
    if (filters?.page_size) {
      params.append('page_size', String(filters.page_size));
    }

    const queryString = params.toString();
    const url = queryString ? `${this.baseUrl}/?${queryString}` : `${this.baseUrl}/`;
    
    const response = await api.get<PaginatedResponse<DeliveryZone>>(url);
    return response.data;
  }

  async getZone(id: string): Promise<DeliveryZone> {
    const response = await api.get<DeliveryZone>(`${this.baseUrl}/${id}/`);
    return response.data;
  }

  async createZone(data: CreateDeliveryZone): Promise<DeliveryZone> {
    const response = await api.post<DeliveryZone>(`${this.baseUrl}/`, data);
    return response.data;
  }

  async updateZone(id: string, data: UpdateDeliveryZone): Promise<DeliveryZone> {
    const response = await api.patch<DeliveryZone>(`${this.baseUrl}/${id}/`, data);
    return response.data;
  }

  async deleteZone(id: string): Promise<void> {
    await api.delete(`${this.baseUrl}/${id}/`);
  }

  async toggleActive(id: string): Promise<DeliveryZone> {
    const response = await api.post<DeliveryZone>(`${this.baseUrl}/${id}/toggle_active/`);
    return response.data;
  }

  async getStats(storeId?: string): Promise<DeliveryZoneStats> {
    const params = new URLSearchParams();
    if (storeId) {
      params.append('store', storeId);
    }
    const queryString = params.toString();
    const url = queryString ? `${this.baseUrl}/stats/?${queryString}` : `${this.baseUrl}/stats/`;
    const response = await api.get<DeliveryZoneStats>(url);
    return response.data;
  }

  async getStoreLocation(): Promise<StoreLocation | null> {
    try {
      // Use the store slug to get the store location
      const response = await api.get<StoreLocation>(`${this.storeUrl}/${this.storeSlug}/`);
      if (response.data && Object.keys(response.data).length > 0) {
        return response.data as StoreLocation;
      }
      return null;
    } catch (error) {
      console.error('Error fetching store location:', error);
      return null;
    }
  }

  async updateStoreLocation(data: UpdateStoreLocation): Promise<StoreLocation> {
    // Use PATCH to update the store with the slug
    const response = await api.patch<StoreLocation>(`${this.storeUrl}/${this.storeSlug}/`, data);
    return response.data;
  }
}

export const deliveryService = new DeliveryService();
export default deliveryService;
