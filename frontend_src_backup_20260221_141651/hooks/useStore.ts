/**
 * Store Context Hook
 * 
 * Provides easy access to the currently selected store.
 * Use this hook in any component that needs store context.
 * 
 * @example
 * const { storeId, storeSlug, storeName, requireStore } = useStore();
 * 
 * // In form submission:
 * const data = { ...formData, store: storeId };
 * await api.createCoupon(data);
 */

import { useCallback } from 'react';
import { useStoreContextStore } from '../stores/storeContextStore';
import { Store } from '../services/storesApi';

export interface UseStoreReturn {
  /** UUID of the selected store */
  storeId: string | null;
  /** URL-friendly slug of the selected store */
  storeSlug: string | null;
  /** Display name of the selected store */
  storeName: string | null;
  /** Whether a store is currently selected */
  isStoreSelected: boolean;
  /** The full store object */
  store: Store | null;
  /** All available stores */
  stores: Store[];
  /** Loading state */
  loading: boolean;
  /** 
   * Throws an error if no store is selected.
   * Use this before operations that require a store.
   */
  requireStore: () => string;
  /**
   * Get store ID or throw with custom message
   */
  getStoreIdOrThrow: (message?: string) => string;
}

/**
 * Hook to access the currently selected store context.
 * 
 * This is the recommended way to get store information in components.
 * It automatically subscribes to store changes and re-renders when needed.
 */
export function useStore(): UseStoreReturn {
  const {
    selectedStore,
    stores,
    loading,
  } = useStoreContextStore();

  const storeId = selectedStore?.id || null;
  const storeSlug = selectedStore?.slug || null;
  const storeName = selectedStore?.name || null;
  const isStoreSelected = selectedStore !== null;

  const requireStore = useCallback((): string => {
    if (!selectedStore?.id) {
      throw new Error('Nenhuma loja selecionada. Por favor, selecione uma loja no menu superior.');
    }
    return selectedStore.id;
  }, [selectedStore]);

  const getStoreIdOrThrow = useCallback((message?: string): string => {
    if (!selectedStore?.id) {
      throw new Error(message || 'Store ID is required but no store is selected.');
    }
    return selectedStore.id;
  }, [selectedStore]);

  return {
    storeId,
    storeSlug,
    storeName,
    isStoreSelected,
    store: selectedStore,
    stores,
    loading,
    requireStore,
    getStoreIdOrThrow,
  };
}

/**
 * Get store ID outside of React components.
 * Use this in services or utility functions.
 * 
 * @example
 * const storeId = getStoreId();
 * if (storeId) {
 *   await api.get('/products', { params: { store: storeId } });
 * }
 */
export function getStoreId(): string | null {
  const state = useStoreContextStore.getState();
  return state.selectedStore?.id || null;
}

/**
 * Get store slug outside of React components.
 */
export function getStoreSlug(): string | null {
  const state = useStoreContextStore.getState();
  return state.selectedStore?.slug || null;
}

/**
 * Get store ID or fallback to env variable.
 * This is useful for backwards compatibility.
 */
export function getStoreIdWithFallback(): string {
  const storeId = getStoreId();
  if (storeId) return storeId;
  
  // Fallback to env variable (for backwards compatibility)
  const envSlug = import.meta.env.VITE_STORE_SLUG || 'pastita';
  console.warn(`No store selected, using fallback: ${envSlug}`);
  return envSlug;
}

export default useStore;
