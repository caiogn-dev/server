import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { toast } from 'react-hot-toast';
import {
  BuildingStorefrontIcon,
  MapPinIcon,
  TruckIcon,
  CurrencyDollarIcon,
  ClockIcon,
  Cog6ToothIcon,
  CheckCircleIcon,
  ArrowPathIcon,
} from '@heroicons/react/24/outline';
import { getStore, updateStore, type Store } from '../../services/storesApi';
import { useStore } from '../../hooks';
import logger from '../../services/logger';

interface DeliveryConfig {
  delivery_base_fee: number;
  delivery_fee_per_km: number;
  delivery_free_km: number;
  delivery_max_fee: number;
  delivery_max_distance: number;
}

const defaultDeliveryConfig: DeliveryConfig = {
  delivery_base_fee: 5.0,
  delivery_fee_per_km: 1.0,
  delivery_free_km: 2.0,
  delivery_max_fee: 25.0,
  delivery_max_distance: 20.0,
};

export const StoreSettingsPage: React.FC = () => {
  const { storeId: routeStoreId } = useParams<{ storeId?: string }>();
  const { storeId: contextStoreId, storeSlug, stores } = useStore();

  const effectiveStoreId = useMemo(() => {
    if (!routeStoreId) return storeSlug || contextStoreId || null;
    const match = stores.find((store) => store.id === routeStoreId || store.slug === routeStoreId);
    return match?.id || match?.slug || routeStoreId;
  }, [routeStoreId, storeSlug, contextStoreId, stores]);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [store, setStore] = useState<Store | null>(null);
  const [deliveryConfig, setDeliveryConfig] = useState<DeliveryConfig>(defaultDeliveryConfig);
  const [storeForm, setStoreForm] = useState({
    name: '',
    email: '',
    phone: '',
    whatsapp_number: '',
    address: '',
    city: '',
    state: '',
    zip_code: '',
    latitude: '',
    longitude: '',
  });

  const loadStore = useCallback(async () => {
    if (!effectiveStoreId) {
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      const data = await getStore(effectiveStoreId);
      setStore(data);

      setStoreForm({
        name: data.name || '',
        email: data.email || '',
        phone: data.phone || '',
        whatsapp_number: data.whatsapp_number || '',
        address: data.address || '',
        city: data.city || '',
        state: data.state || '',
        zip_code: data.zip_code || '',
        latitude: data.latitude?.toString() || '',
        longitude: data.longitude?.toString() || '',
      });

      const metadata = data.metadata || {};
      setDeliveryConfig({
        delivery_base_fee: Number(metadata.delivery_base_fee) || defaultDeliveryConfig.delivery_base_fee,
        delivery_fee_per_km: Number(metadata.delivery_fee_per_km) || defaultDeliveryConfig.delivery_fee_per_km,
        delivery_free_km: Number(metadata.delivery_free_km) || defaultDeliveryConfig.delivery_free_km,
        delivery_max_fee: Number(metadata.delivery_max_fee) || defaultDeliveryConfig.delivery_max_fee,
        delivery_max_distance: Number(metadata.delivery_max_distance) || defaultDeliveryConfig.delivery_max_distance,
      });
    } catch (error) {
      logger.error('Error loading store:', error);
      toast.error('Erro ao carregar configurações da loja');
    } finally {
      setLoading(false);
    }
  }, [effectiveStoreId]);

  useEffect(() => {
    loadStore();
  }, [loadStore]);

  const handleSaveStore = async () => {
    if (!effectiveStoreId) return;
    setSaving(true);
    try {
      const payload = {
        name: storeForm.name,
        email: storeForm.email,
        phone: storeForm.phone,
        whatsapp_number: storeForm.whatsapp_number,
        address: storeForm.address,
        city: storeForm.city,
        state: storeForm.state,
        zip_code: storeForm.zip_code,
      };

      await updateStore(effectiveStoreId, payload);
      toast.success('Informações da loja atualizadas!');
      loadStore();
    } catch (error) {
      logger.error('Error saving store:', error);
      toast.error('Erro ao salvar informações da loja');
    } finally {
      setSaving(false);
    }
  };

  const handleSaveDeliveryConfig = async () => {
    if (!effectiveStoreId) return;
    setSaving(true);
    try {
      const currentMetadata = store?.metadata || {};
      const payload = {
        metadata: {
          ...currentMetadata,
          delivery_base_fee: deliveryConfig.delivery_base_fee,
          delivery_fee_per_km: deliveryConfig.delivery_fee_per_km,
          delivery_free_km: deliveryConfig.delivery_free_km,
          delivery_max_fee: deliveryConfig.delivery_max_fee,
          delivery_max_distance: deliveryConfig.delivery_max_distance,
        },
      };

      await updateStore(effectiveStoreId, payload);
      toast.success('Configurações de entrega atualizadas!');
      loadStore();
    } catch (error) {
      logger.error('Error saving delivery config:', error);
      toast.error('Erro ao salvar configurações de entrega');
    } finally {
      setSaving(false);
    }
  };

  const handleSaveLocation = async () => {
    if (!effectiveStoreId) return;
    const lat = parseFloat(storeForm.latitude);
    const lng = parseFloat(storeForm.longitude);

    if (isNaN(lat) || isNaN(lng)) {
      toast.error('Latitude e longitude devem ser números válidos');
      return;
    }

    if (lat < -90 || lat > 90) {
      toast.error('Latitude deve estar entre -90 e 90');
      return;
    }

    if (lng < -180 || lng > 180) {
      toast.error('Longitude deve estar entre -180 e 180');
      return;
    }

    setSaving(true);
    try {
      const currentMetadata = store?.metadata || {};
      const payload = {
        metadata: {
          ...currentMetadata,
          store_latitude: lat,
          store_longitude: lng,
        },
      };

      await updateStore(effectiveStoreId, payload);
      toast.success('Localização da loja atualizada!');
      loadStore();
    } catch (error) {
      logger.error('Error saving location:', error);
      toast.error('Erro ao salvar localização');
    } finally {
      setSaving(false);
    }
  };

  const calculateExampleFee = (distance: number): number => {
    if (distance <= deliveryConfig.delivery_free_km) {
      return deliveryConfig.delivery_base_fee;
    }
    const extraKm = distance - deliveryConfig.delivery_free_km;
    const fee = deliveryConfig.delivery_base_fee + (extraKm * deliveryConfig.delivery_fee_per_km);
    return Math.min(fee, deliveryConfig.delivery_max_fee);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-black flex items-center justify-center">
        <div className="text-center">
          <ArrowPathIcon className="w-8 h-8 text-gray-400 animate-spin mx-auto mb-3" />
          <p className="text-gray-500 dark:text-zinc-400">Carregando configurações...</p>
        </div>
      </div>
    );
  }

  if (!effectiveStoreId) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-black flex items-center justify-center">
        <div className="text-center max-w-md">
          <BuildingStorefrontIcon className="w-12 h-12 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-500 dark:text-zinc-400">Selecione uma loja para configurar.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-black p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex items-center gap-3">
          <BuildingStorefrontIcon className="w-6 h-6 text-primary-600" />
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Configurações da Loja</h1>
            <p className="text-sm text-gray-500 dark:text-zinc-400">{store?.name || 'Loja'}</p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white dark:bg-zinc-900 rounded-xl p-6 shadow-sm">
            <div className="flex items-center gap-2 mb-4">
              <BuildingStorefrontIcon className="w-5 h-5 text-gray-600 dark:text-zinc-300" />
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Informações da Loja</h2>
            </div>
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium text-gray-600 dark:text-zinc-400">Nome</label>
                <input
                  type="text"
                  value={storeForm.name}
                  onChange={(e) => setStoreForm({ ...storeForm, name: e.target.value })}
                  className="w-full mt-1 px-4 py-2 border border-gray-200 dark:border-zinc-800 rounded-lg focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-600 dark:text-zinc-400">Email</label>
                <input
                  type="email"
                  value={storeForm.email}
                  onChange={(e) => setStoreForm({ ...storeForm, email: e.target.value })}
                  className="w-full mt-1 px-4 py-2 border border-gray-200 dark:border-zinc-800 rounded-lg focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-600 dark:text-zinc-400">Telefone</label>
                <input
                  type="text"
                  value={storeForm.phone}
                  onChange={(e) => setStoreForm({ ...storeForm, phone: e.target.value })}
                  className="w-full mt-1 px-4 py-2 border border-gray-200 dark:border-zinc-800 rounded-lg focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-600 dark:text-zinc-400">WhatsApp</label>
                <input
                  type="text"
                  value={storeForm.whatsapp_number}
                  onChange={(e) => setStoreForm({ ...storeForm, whatsapp_number: e.target.value })}
                  className="w-full mt-1 px-4 py-2 border border-gray-200 dark:border-zinc-800 rounded-lg focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <button
                onClick={handleSaveStore}
                disabled={saving}
                className="w-full py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50"
              >
                {saving ? 'Salvando...' : 'Salvar Informações'}
              </button>
            </div>
          </div>

          <div className="bg-white dark:bg-zinc-900 rounded-xl p-6 shadow-sm">
            <div className="flex items-center gap-2 mb-4">
              <MapPinIcon className="w-5 h-5 text-gray-600 dark:text-zinc-300" />
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Localização</h2>
            </div>
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium text-gray-600 dark:text-zinc-400">Endereço</label>
                <input
                  type="text"
                  value={storeForm.address}
                  onChange={(e) => setStoreForm({ ...storeForm, address: e.target.value })}
                  className="w-full mt-1 px-4 py-2 border border-gray-200 dark:border-zinc-800 rounded-lg focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium text-gray-600 dark:text-zinc-400">Cidade</label>
                  <input
                    type="text"
                    value={storeForm.city}
                    onChange={(e) => setStoreForm({ ...storeForm, city: e.target.value })}
                    className="w-full mt-1 px-4 py-2 border border-gray-200 dark:border-zinc-800 rounded-lg focus:ring-2 focus:ring-primary-500"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-gray-600 dark:text-zinc-400">Estado</label>
                  <input
                    type="text"
                    value={storeForm.state}
                    onChange={(e) => setStoreForm({ ...storeForm, state: e.target.value })}
                    className="w-full mt-1 px-4 py-2 border border-gray-200 dark:border-zinc-800 rounded-lg focus:ring-2 focus:ring-primary-500"
                  />
                </div>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-600 dark:text-zinc-400">CEP</label>
                <input
                  type="text"
                  value={storeForm.zip_code}
                  onChange={(e) => setStoreForm({ ...storeForm, zip_code: e.target.value })}
                  className="w-full mt-1 px-4 py-2 border border-gray-200 dark:border-zinc-800 rounded-lg focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium text-gray-600 dark:text-zinc-400">Latitude</label>
                  <input
                    type="text"
                    value={storeForm.latitude}
                    onChange={(e) => setStoreForm({ ...storeForm, latitude: e.target.value })}
                    className="w-full mt-1 px-4 py-2 border border-gray-200 dark:border-zinc-800 rounded-lg focus:ring-2 focus:ring-primary-500"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-gray-600 dark:text-zinc-400">Longitude</label>
                  <input
                    type="text"
                    value={storeForm.longitude}
                    onChange={(e) => setStoreForm({ ...storeForm, longitude: e.target.value })}
                    className="w-full mt-1 px-4 py-2 border border-gray-200 dark:border-zinc-800 rounded-lg focus:ring-2 focus:ring-primary-500"
                  />
                </div>
              </div>
              <button
                onClick={handleSaveLocation}
                disabled={saving}
                className="w-full py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50"
              >
                {saving ? 'Salvando...' : 'Salvar Localização'}
              </button>
            </div>
          </div>
        </div>

        <div className="bg-white dark:bg-zinc-900 rounded-xl p-6 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <TruckIcon className="w-5 h-5 text-gray-600 dark:text-zinc-300" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Entrega</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium text-gray-600 dark:text-zinc-400">Taxa Base</label>
                <input
                  type="number"
                  value={deliveryConfig.delivery_base_fee}
                  onChange={(e) => setDeliveryConfig({ ...deliveryConfig, delivery_base_fee: parseFloat(e.target.value) })}
                  className="w-full mt-1 px-4 py-2 border border-gray-200 dark:border-zinc-800 rounded-lg focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-600 dark:text-zinc-400">Taxa por KM</label>
                <input
                  type="number"
                  value={deliveryConfig.delivery_fee_per_km}
                  onChange={(e) => setDeliveryConfig({ ...deliveryConfig, delivery_fee_per_km: parseFloat(e.target.value) })}
                  className="w-full mt-1 px-4 py-2 border border-gray-200 dark:border-zinc-800 rounded-lg focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-600 dark:text-zinc-400">KM Grátis</label>
                <input
                  type="number"
                  value={deliveryConfig.delivery_free_km}
                  onChange={(e) => setDeliveryConfig({ ...deliveryConfig, delivery_free_km: parseFloat(e.target.value) })}
                  className="w-full mt-1 px-4 py-2 border border-gray-200 dark:border-zinc-800 rounded-lg focus:ring-2 focus:ring-primary-500"
                />
              </div>
            </div>
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium text-gray-600 dark:text-zinc-400">Taxa Máxima</label>
                <input
                  type="number"
                  value={deliveryConfig.delivery_max_fee}
                  onChange={(e) => setDeliveryConfig({ ...deliveryConfig, delivery_max_fee: parseFloat(e.target.value) })}
                  className="w-full mt-1 px-4 py-2 border border-gray-200 dark:border-zinc-800 rounded-lg focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-600 dark:text-zinc-400">Distância Máxima</label>
                <input
                  type="number"
                  value={deliveryConfig.delivery_max_distance}
                  onChange={(e) => setDeliveryConfig({ ...deliveryConfig, delivery_max_distance: parseFloat(e.target.value) })}
                  className="w-full mt-1 px-4 py-2 border border-gray-200 dark:border-zinc-800 rounded-lg focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div className="bg-gray-50 dark:bg-black rounded-lg p-4">
                <div className="flex items-center gap-2 text-gray-500 dark:text-zinc-400 mb-2">
                  <CurrencyDollarIcon className="w-4 h-4" />
                  <span className="text-sm font-medium">Exemplo</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span>5 km</span>
                  <span className="font-semibold">R$ {calculateExampleFee(5).toFixed(2)}</span>
                </div>
              </div>
            </div>
          </div>
          <button
            onClick={handleSaveDeliveryConfig}
            disabled={saving}
            className="mt-6 w-full py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50"
          >
            {saving ? 'Salvando...' : 'Salvar Configurações de Entrega'}
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-white dark:bg-zinc-900 rounded-xl p-4 shadow-sm">
            <div className="flex items-center gap-2">
              <Cog6ToothIcon className="w-5 h-5 text-gray-500" />
              <span className="text-sm text-gray-600 dark:text-zinc-400">Status</span>
            </div>
            <p className="text-lg font-semibold text-gray-900 dark:text-white mt-2">
              {store?.status === 'active' ? 'Ativa' : 'Inativa'}
            </p>
          </div>
          <div className="bg-white dark:bg-zinc-900 rounded-xl p-4 shadow-sm">
            <div className="flex items-center gap-2">
              <CheckCircleIcon className="w-5 h-5 text-green-500" />
              <span className="text-sm text-gray-600 dark:text-zinc-400">Pedidos</span>
            </div>
            <p className="text-lg font-semibold text-gray-900 dark:text-white mt-2">
              {store?.orders_count ?? 0}
            </p>
          </div>
          <div className="bg-white dark:bg-zinc-900 rounded-xl p-4 shadow-sm">
            <div className="flex items-center gap-2">
              <ClockIcon className="w-5 h-5 text-blue-500" />
              <span className="text-sm text-gray-600 dark:text-zinc-400">Produtos</span>
            </div>
            <p className="text-lg font-semibold text-gray-900 dark:text-white mt-2">
              {store?.products_count ?? 0}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default StoreSettingsPage;
