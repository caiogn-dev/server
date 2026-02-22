/**
 * Store Context Store
 * Manages the currently selected store for multi-store dashboard operations.
 * All store-scoped operations should use this context to filter data.
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { Store, getStores } from '../services/storesApi';
import logger from '../services/logger';

interface StoreContextState {
  // State
  stores: Store[];
  selectedStore: Store | null;
  loading: boolean;
  error: string | null;
  initialized: boolean;
  
  // Actions
  fetchStores: () => Promise<void>;
  setSelectedStore: (store: Store | null) => void;
  selectStoreById: (storeId: string) => void;
  selectStoreBySlug: (slug: string) => void;
  clearSelection: () => void;
  refresh: () => Promise<void>;
}

export const useStoreContextStore = create<StoreContextState>()(
  persist(
    (set, get) => ({
      // Initial state
      stores: [],
      selectedStore: null,
      loading: false,
      error: null,
      initialized: false,
      
      // Fetch all stores the user has access to
      fetchStores: async () => {
        set({ loading: true, error: null });
        try {
          const response = await getStores();
          const stores = response.results || [];
          
          set({ 
            stores, 
            loading: false, 
            initialized: true 
          });
          
          // Auto-select first store if none selected and stores exist
          const { selectedStore } = get();
          if (!selectedStore && stores.length > 0) {
            // Try to find Pastita store first
            const pastitaStore = stores.find(s => s.slug === 'pastita');
            set({ selectedStore: pastitaStore || stores[0] });
          } else if (selectedStore) {
            // Verify selected store still exists
            const stillExists = stores.find(s => s.id === selectedStore.id);
            if (!stillExists) {
              set({ selectedStore: stores[0] || null });
            }
          }
          
          logger.info(`Loaded ${stores.length} stores`);
        } catch (error) {
          logger.error('Failed to fetch stores', error);
          set({ 
            error: 'Falha ao carregar lojas', 
            loading: false,
            initialized: true 
          });
        }
      },
      
      // Set selected store directly
      setSelectedStore: (store) => {
        set({ selectedStore: store });
        if (store) {
          logger.info(`Selected store: ${store.name} (${store.slug})`);
        }
      },
      
      // Select store by ID
      selectStoreById: (storeId) => {
        const { stores } = get();
        const store = stores.find(s => s.id === storeId);
        if (store) {
          set({ selectedStore: store });
          logger.info(`Selected store by ID: ${store.name}`);
        } else {
          logger.warn(`Store not found with ID: ${storeId}`);
        }
      },
      
      // Select store by slug
      selectStoreBySlug: (slug) => {
        const { stores } = get();
        const store = stores.find(s => s.slug === slug);
        if (store) {
          set({ selectedStore: store });
          logger.info(`Selected store by slug: ${store.name}`);
        } else {
          logger.warn(`Store not found with slug: ${slug}`);
        }
      },
      
      // Clear selection
      clearSelection: () => {
        set({ selectedStore: null });
      },
      
      // Refresh stores list
      refresh: async () => {
        await get().fetchStores();
      },
    }),
    {
      name: 'store-context-storage',
      partialize: (state) => ({ 
        selectedStore: state.selectedStore 
      }),
    }
  )
);

// Helper hook to get selected store ID
export const useSelectedStoreId = () => {
  const selectedStore = useStoreContextStore(state => state.selectedStore);
  return selectedStore?.id || null;
};

// Helper hook to get selected store slug
export const useSelectedStoreSlug = () => {
  const selectedStore = useStoreContextStore(state => state.selectedStore);
  return selectedStore?.slug || null;
};

// Helper hook to check if a store is selected
export const useHasSelectedStore = () => {
  const selectedStore = useStoreContextStore(state => state.selectedStore);
  return selectedStore !== null;
};
