import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import logger from '../../services/logger';
import {
  PlusIcon,
  PencilIcon,
  TrashIcon,
  MagnifyingGlassIcon,
  TruckIcon,
  MapPinIcon,
  CheckCircleIcon,
  Cog6ToothIcon,
} from '@heroicons/react/24/outline';
import { Card, Button, Input, Badge, Modal, Loading } from '../../components/common';
import {
  deliveryService,
  DeliveryZone,
  CreateDeliveryZone,
  UpdateDeliveryZone,
  DeliveryZoneStats,
  StoreLocation,
} from '../../services/delivery';
import { useStore } from '../../hooks';

const formatKm = (value?: number | string | null) => {
  const numeric = typeof value === 'number' ? value : Number.parseFloat(String(value ?? '0'));
  if (!Number.isFinite(numeric)) return '0.00';
  return numeric.toFixed(2);
};

const formatMoney = (value?: number | string | null) => {
  const numeric = typeof value === 'number' ? value : Number.parseFloat(String(value ?? '0'));
  if (Number.isNaN(numeric)) return '0.00';
  return numeric.toFixed(2);
};

const formatDays = (value?: number | string | null) => {
  const numeric = typeof value === 'number' ? value : Number.parseFloat(String(value ?? '0'));
  if (Number.isNaN(numeric)) return '0';
  return String(Math.round(numeric));
};

const DISTANCE_BANDS = [
  { value: '0_2', label: '0 - 2 km' },
  { value: '2_5', label: '2 - 5 km' },
  { value: '5_8', label: '5 - 8 km' },
  { value: '8_12', label: '8 - 12 km' },
  { value: '12_15', label: '12 - 15 km' },
  { value: '15_20', label: '15 - 20 km' },
];

const buildMapUrls = ({
  lat,
  lng,
  query,
}: {
  lat?: number | string | null;
  lng?: number | string | null;
  query?: string;
}) => {
  const parsedLat = typeof lat === 'string' ? Number.parseFloat(lat) : lat;
  const parsedLng = typeof lng === 'string' ? Number.parseFloat(lng) : lng;
  const hasCoords = Number.isFinite(parsedLat) && Number.isFinite(parsedLng);
  const normalizedQuery = query?.trim();
  if (normalizedQuery) {
    const encoded = encodeURIComponent(normalizedQuery);
    return {
      mapUrl: `https://www.google.com/maps?q=${encoded}&output=embed`,
      externalUrl: `https://www.google.com/maps?q=${encoded}`,
    };
  }
  if (hasCoords && parsedLat != null && parsedLng != null) {
    const coords = `${parsedLat},${parsedLng}`;
    return {
      mapUrl: `https://www.google.com/maps?q=${coords}&output=embed`,
      externalUrl: `https://www.google.com/maps?q=${coords}`,
    };
  }
  return null;
};

export const DeliveryZonesPage: React.FC = () => {
  const { storeId: routeStoreId } = useParams<{ storeId?: string }>();
  const { storeId: contextStoreId, storeName, isStoreSelected } = useStore();
  
  // Use route storeId if available, otherwise use context
  const storeId = routeStoreId || contextStoreId;
  const settingsPath = storeId ? `/stores/${storeId}/settings` : '/settings';
  const [zones, setZones] = useState<DeliveryZone[]>([]);
  const [stats, setStats] = useState<DeliveryZoneStats | null>(null);
  const [storeLocation, setStoreLocation] = useState<StoreLocation | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filterActive, setFilterActive] = useState<boolean | undefined>(undefined);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [editingZone, setEditingZone] = useState<DeliveryZone | null>(null);
  const [deletingZone, setDeletingZone] = useState<DeliveryZone | null>(null);
  const [saving, setSaving] = useState(false);

  const [formData, setFormData] = useState<CreateDeliveryZone>({
    store: storeId || undefined,
    name: '',
    distance_band: '',
    delivery_fee: 0,
    estimated_days: 1,
    is_active: true,
  });

  const mapInfo = useMemo(() => {
    if (!storeLocation) return null;
    const queryParts = [
      storeLocation.name,
      storeLocation.address,
      storeLocation.city,
      storeLocation.state,
      storeLocation.zip_code,
      'Brasil',
    ].filter(Boolean);
    return buildMapUrls({
      lat: storeLocation.latitude,
      lng: storeLocation.longitude,
      query: storeLocation.name?.trim() || queryParts.join(', '),
    });
  }, [storeLocation]);

  const loadData = useCallback(async () => {
    if (!storeId) {
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const [zonesData, statsData, storeData] = await Promise.all([
        deliveryService.getZones({
          store: storeId,
          search: search || undefined,
          is_active: filterActive,
        }),
        deliveryService.getStats(storeId),
        deliveryService.getStoreLocation(),
      ]);
      setZones(zonesData.results);
      setStats(statsData);
      if (storeData) {
        setStoreLocation(storeData);
      }
    } catch (err) {
      logger.error('Error loading delivery zones:', err);
      setError('Erro ao carregar zonas de entrega');
    } finally {
      setLoading(false);
    }
  }, [search, filterActive, storeId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Update form data when store changes
  useEffect(() => {
    setFormData(prev => ({ ...prev, store: storeId || undefined }));
  }, [storeId]);

  const handleOpenModal = (zone?: DeliveryZone) => {
    if (zone) {
      setEditingZone(zone);
      setFormData({
        name: zone.name,
        distance_band: zone.distance_band || '',
        delivery_fee: zone.delivery_fee,
        estimated_days: zone.estimated_days,
        is_active: zone.is_active,
      });
    } else {
      setEditingZone(null);
      setFormData({
        name: '',
        distance_band: '',
        delivery_fee: 0,
        estimated_days: 1,
        is_active: true,
      });
    }
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setEditingZone(null);
  };

  const handleSave = async () => {
    if (!storeId) {
      setError('Selecione uma loja antes de criar uma zona de entrega');
      return;
    }

    try {
      setSaving(true);
      setError(null);
      
      if (editingZone) {
        const payload: UpdateDeliveryZone = {
          ...formData,
          store: storeId,
          name: formData.name.trim(),
          distance_band: formData.distance_band,
        };
        await deliveryService.updateZone(editingZone.id, payload);
      } else {
        const payload: CreateDeliveryZone = {
          ...formData,
          store: storeId,
          name: formData.name.trim(),
        };
        await deliveryService.createZone(payload);
      }
      handleCloseModal();
      loadData();
    } catch (err) {
      logger.error('Error saving delivery zone:', err);
      setError('Erro ao salvar zona de entrega');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleActive = async (zone: DeliveryZone) => {
    try {
      await deliveryService.toggleActive(zone.id);
      loadData();
    } catch (error) {
      logger.error('Error toggling zone:', error);
    }
  };

  const handleDelete = async () => {
    if (!deletingZone) return;
    try {
      setSaving(true);
      await deliveryService.deleteZone(deletingZone.id);
      setIsDeleteModalOpen(false);
      setDeletingZone(null);
      loadData();
    } catch (error) {
      logger.error('Error deleting zone:', error);
    } finally {
      setSaving(false);
    }
  };

  if (loading && zones.length === 0) {
    return <Loading />;
  }

  return (
    <div className="p-4 md:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-gray-900 dark:text-white">Zonas de Entrega</h1>
          <p className="text-sm md:text-base text-gray-500 dark:text-zinc-400">Calcule frete por quilometragem e gerencie faixas de preço</p>
        </div>
        <Button onClick={() => handleOpenModal()} className="w-full sm:w-auto">
          <PlusIcon className="w-5 h-5 mr-2" />
          Nova Faixa
        </Button>
      </div>

      {/* Store Location Card - Read Only */}
      <Card className="p-4 md:p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Localização da Loja</h2>
            <p className="text-sm text-gray-500 dark:text-zinc-400 mt-1">
              A localização é usada para calcular a distância de entrega.
            </p>
          </div>
          <Link
            to={settingsPath}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-blue-600 dark:text-blue-400 bg-blue-50 rounded-lg hover:bg-blue-100 dark:bg-blue-900/40 transition-colors"
          >
            <Cog6ToothIcon className="w-4 h-4" />
            Editar Localização
          </Link>
        </div>

        {storeLocation ? (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="sm:col-span-2">
                <p className="text-sm font-medium text-gray-500 dark:text-zinc-400">Nome da Loja</p>
                <p className="text-base text-gray-900 dark:text-white">{storeLocation.name || '-'}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-500 dark:text-zinc-400">CEP</p>
                <p className="text-base text-gray-900 dark:text-white">{storeLocation.zip_code || '-'}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-500 dark:text-zinc-400">Cidade/Estado</p>
                <p className="text-base text-gray-900 dark:text-white">
                  {storeLocation.city && storeLocation.state 
                    ? `${storeLocation.city}/${storeLocation.state}` 
                    : '-'}
                </p>
              </div>
            </div>
            
            <div>
              <p className="text-sm font-medium text-gray-500 dark:text-zinc-400">Endereço</p>
              <p className="text-base text-gray-900 dark:text-white">{storeLocation.address || '-'}</p>
            </div>

            {mapInfo && (
              <div className="mt-4">
                <div className="rounded-lg overflow-hidden border border-gray-200 dark:border-zinc-800">
                  <iframe
                    title="Mapa da loja"
                    src={mapInfo.mapUrl}
                    className="w-full h-48 md:h-64"
                    loading="lazy"
                  />
                </div>
                <a
                  href={mapInfo.externalUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm text-primary-600 hover:text-primary-700 inline-flex items-center mt-2"
                >
                  Ver no Google Maps →
                </a>
              </div>
            )}
          </div>
        ) : (
          <div className="text-center py-8">
            <MapPinIcon className="w-12 h-12 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500 dark:text-zinc-400 mb-4">Localização não configurada</p>
            <Link
              to={settingsPath}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors"
            >
              <Cog6ToothIcon className="w-4 h-4" />
              Configurar Localização
            </Link>
          </div>
        )}
      </Card>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
          <Card className="p-3 md:p-4">
            <div className="flex items-center">
              <div className="p-2 bg-blue-100 dark:bg-blue-900/40 rounded-lg shrink-0">
                <MapPinIcon className="w-5 h-5 md:w-6 md:h-6 text-blue-600 dark:text-blue-400" />
              </div>
              <div className="ml-3 md:ml-4 min-w-0">
                <p className="text-xs md:text-sm text-gray-500 dark:text-zinc-400 truncate">Total de Faixas</p>
                <p className="text-lg md:text-2xl font-bold text-gray-900 dark:text-white">{stats.total}</p>
              </div>
            </div>
          </Card>
          <Card className="p-3 md:p-4">
            <div className="flex items-center">
              <div className="p-2 bg-green-100 dark:bg-green-900/40 rounded-lg shrink-0">
                <CheckCircleIcon className="w-5 h-5 md:w-6 md:h-6 text-green-600 dark:text-green-400" />
              </div>
              <div className="ml-3 md:ml-4 min-w-0">
                <p className="text-xs md:text-sm text-gray-500 dark:text-zinc-400 truncate">Ativas</p>
                <p className="text-lg md:text-2xl font-bold text-gray-900 dark:text-white">{stats.active}</p>
              </div>
            </div>
          </Card>
          <Card className="p-3 md:p-4">
            <div className="flex items-center">
              <div className="p-2 bg-yellow-100 dark:bg-yellow-900/40 rounded-lg shrink-0">
                <TruckIcon className="w-5 h-5 md:w-6 md:h-6 text-yellow-600 dark:text-yellow-400" />
              </div>
              <div className="ml-3 md:ml-4 min-w-0">
                <p className="text-xs md:text-sm text-gray-500 dark:text-zinc-400 truncate">Valor Médio</p>
                <p className="text-lg md:text-2xl font-bold text-gray-900 dark:text-white">R$ {formatMoney(stats.avg_fee)}</p>
              </div>
            </div>
          </Card>
          <Card className="p-3 md:p-4">
            <div className="flex items-center">
              <div className="p-2 bg-purple-100 dark:bg-purple-900/40 rounded-lg shrink-0">
                <TruckIcon className="w-5 h-5 md:w-6 md:h-6 text-purple-600 dark:text-purple-400" />
              </div>
              <div className="ml-3 md:ml-4 min-w-0">
                <p className="text-xs md:text-sm text-gray-500 dark:text-zinc-400 truncate">Prazo Médio</p>
                <p className="text-lg md:text-2xl font-bold text-gray-900 dark:text-white">{formatDays(stats.avg_days)} dias</p>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* Filters */}
      <Card className="p-3 md:p-4">
        <div className="flex flex-col sm:flex-row gap-3 md:gap-4">
          <div className="flex-1">
            <div className="relative">
              <MagnifyingGlassIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
              <Input
                type="text"
                placeholder="Buscar por nome..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-10"
              />
            </div>
          </div>
          <select
            value={filterActive === undefined ? '' : String(filterActive)}
            onChange={(e) => setFilterActive(e.target.value === '' ? undefined : e.target.value === 'true')}
            className="w-full sm:w-auto px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent text-sm md:text-base"
          >
            <option value="">Todos os status</option>
            <option value="true">Ativas</option>
            <option value="false">Inativas</option>
          </select>
        </div>
      </Card>

      {/* Zones Table */}
      <Card>
        {/* Mobile Cards View */}
        <div className="block md:hidden divide-y divide-gray-200">
          {zones.map((zone) => (
            <div key={zone.id} className="p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <MapPinIcon className="w-5 h-5 text-gray-400" />
                  <span className="font-medium text-gray-900 dark:text-white">{zone.name}</span>
                </div>
                <button
                  onClick={() => handleToggleActive(zone)}
                  className="focus:outline-none"
                >
                  <Badge variant={zone.is_active ? 'success' : 'danger'}>
                    {zone.is_active ? 'Ativa' : 'Inativa'}
                  </Badge>
                </button>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-gray-500 dark:text-zinc-400">Distância:</span>
                  <span className="ml-1 font-mono text-gray-700 dark:text-zinc-300">
                    {zone.distance_label
                      ? zone.distance_label
                      : zone.min_km !== null && zone.min_km !== undefined
                        ? `${formatKm(zone.min_km)} - ${zone.max_km !== null && zone.max_km !== undefined ? formatKm(zone.max_km) : '?'} km`
                        : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-gray-500 dark:text-zinc-400">Prazo:</span>
                  <span className="ml-1 text-gray-700 dark:text-zinc-300">
                    {zone.estimated_days} {zone.estimated_days === 1 ? 'dia útil' : 'dias úteis'}
                  </span>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-lg font-semibold text-green-600 dark:text-green-400">
                  R$ {formatMoney(zone.delivery_fee)}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleOpenModal(zone)}
                    className="p-2 text-primary-600 hover:bg-primary-50 rounded-lg"
                  >
                    <PencilIcon className="w-5 h-5" />
                  </button>
                  <button
                    onClick={() => {
                      setDeletingZone(zone);
                      setIsDeleteModalOpen(true);
                    }}
                    className="p-2 text-red-600 dark:text-red-400 hover:bg-red-50 rounded-lg"
                  >
                    <TrashIcon className="w-5 h-5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Desktop Table View */}
        <div className="hidden md:block overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50 dark:bg-black">
              <tr>
                <th className="px-4 lg:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
                  Faixa
                </th>
                <th className="px-4 lg:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
                  Distância (KM)
                </th>
                <th className="px-4 lg:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
                  Valor
                </th>
                <th className="px-4 lg:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
                  Prazo
                </th>
                <th className="px-4 lg:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-4 lg:px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
                  Ações
                </th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-zinc-900 divide-y divide-gray-200">
              {zones.map((zone) => (
                <tr key={zone.id} className="hover:bg-gray-50 dark:hover:bg-zinc-700 dark:bg-black">
                  <td className="px-4 lg:px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center">
                      <MapPinIcon className="w-5 h-5 text-gray-400 mr-2" />
                      <span className="font-medium text-gray-900 dark:text-white">{zone.name}</span>
                    </div>
                  </td>
                  <td className="px-4 lg:px-6 py-4 whitespace-nowrap">
                    <span className="font-mono text-sm text-gray-700 dark:text-zinc-300">
                      {zone.distance_label
                        ? zone.distance_label
                        : zone.min_km !== null && zone.min_km !== undefined
                          ? `${formatKm(zone.min_km)} - ${zone.max_km !== null && zone.max_km !== undefined ? formatKm(zone.max_km) : '?'} km`
                          : '—'}
                    </span>
                  </td>
                  <td className="px-4 lg:px-6 py-4 whitespace-nowrap">
                    <span className="text-base font-semibold text-green-600 dark:text-green-400">
                      R$ {formatMoney(zone.delivery_fee)}
                    </span>
                  </td>
                  <td className="px-4 lg:px-6 py-4 whitespace-nowrap text-sm text-gray-600 dark:text-zinc-400">
                    {zone.estimated_days} {zone.estimated_days === 1 ? 'dia útil' : 'dias úteis'}
                  </td>
                  <td className="px-4 lg:px-6 py-4 whitespace-nowrap">
                    <button
                      onClick={() => handleToggleActive(zone)}
                      className="focus:outline-none"
                    >
                      <Badge variant={zone.is_active ? 'success' : 'danger'}>
                        {zone.is_active ? 'Ativa' : 'Inativa'}
                      </Badge>
                    </button>
                  </td>
                  <td className="px-4 lg:px-6 py-4 whitespace-nowrap text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={() => handleOpenModal(zone)}
                        className="p-2 text-primary-600 hover:bg-primary-50 rounded-lg transition-colors"
                        title="Editar"
                      >
                        <PencilIcon className="w-5 h-5" />
                      </button>
                      <button
                        onClick={() => {
                          setDeletingZone(zone);
                          setIsDeleteModalOpen(true);
                        }}
                        className="p-2 text-red-600 dark:text-red-400 hover:bg-red-50 rounded-lg transition-colors"
                        title="Excluir"
                      >
                        <TrashIcon className="w-5 h-5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {zones.length === 0 && (
          <div className="text-center py-12 px-4">
            <MapPinIcon className="mx-auto h-12 w-12 text-gray-400" />
            <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-white">Nenhuma faixa encontrada</h3>
            <p className="mt-1 text-sm text-gray-500 dark:text-zinc-400">
              Cadastre faixas de quilometragem para calcular o frete.
            </p>
            <div className="mt-6">
              <Button onClick={() => handleOpenModal()}>
                <PlusIcon className="w-5 h-5 mr-2" />
                Nova Faixa
              </Button>
            </div>
          </div>
        )}
      </Card>

      {/* Create/Edit Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        title={editingZone ? 'Editar Faixa de Entrega' : 'Nova Faixa de Entrega'}
      >
        <div className="space-y-4">
          <Input
            label="Nome da Faixa *"
            type="text"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            placeholder="Ex: Até 5km, Zona Metropolitana"
          />

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
              Faixa de Distância *
            </label>
            <select
              value={formData.distance_band}
              onChange={(e) => {
                const nextBand = e.target.value;
                const matched = DISTANCE_BANDS.find((band) => band.value === nextBand);
                setFormData((prev) => ({
                  ...prev,
                  distance_band: nextBand,
                  name: prev.name || matched?.label || prev.name,
                }));
              }}
              className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent text-sm md:text-base"
            >
              <option value="">Selecione uma faixa</option>
              {DISTANCE_BANDS.map((band) => (
                <option key={band.value} value={band.value}>{band.label}</option>
              ))}
            </select>
          </div>

          <Input
            label="Valor da Entrega (R$) *"
            type="number"
            value={formData.delivery_fee}
            onChange={(e) => setFormData({ ...formData, delivery_fee: parseFloat(e.target.value) || 0 })}
            min="0"
            step="0.01"
            placeholder="0.00"
          />

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Input
              label="Prazo de Entrega (dias) *"
              type="number"
              value={formData.estimated_days}
              onChange={(e) => setFormData({ ...formData, estimated_days: parseInt(e.target.value) || 1 })}
              min="1"
            />
            <div className="flex items-center sm:mt-7">
              <input
                type="checkbox"
                id="is_active"
                checked={formData.is_active}
                onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 dark:border-zinc-700 rounded"
              />
              <label htmlFor="is_active" className="ml-2 block text-sm text-gray-900 dark:text-white">
                Faixa ativa
              </label>
            </div>
          </div>

          <div className="flex flex-col-reverse sm:flex-row justify-end gap-3 pt-4 border-t border-gray-100">
            <Button variant="secondary" onClick={handleCloseModal} className="w-full sm:w-auto">
              Cancelar
            </Button>
            <Button
              onClick={handleSave}
              disabled={saving || !formData.name || !formData.distance_band}
              className="w-full sm:w-auto"
            >
              {saving ? 'Salvando...' : editingZone ? 'Salvar Alterações' : 'Criar Faixa'}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={isDeleteModalOpen}
        onClose={() => {
          setIsDeleteModalOpen(false);
          setDeletingZone(null);
        }}
        title="Excluir Faixa de Entrega"
      >
        <div className="space-y-4">
          <p className="text-gray-600 dark:text-zinc-400">
            Tem certeza que deseja excluir a faixa <strong className="text-gray-900 dark:text-white">{deletingZone?.name}</strong>?
            Esta ação não pode ser desfeita.
          </p>
          <div className="flex flex-col-reverse sm:flex-row justify-end gap-3 pt-4 border-t border-gray-100">
            <Button
              variant="secondary"
              onClick={() => {
                setIsDeleteModalOpen(false);
                setDeletingZone(null);
              }}
              className="w-full sm:w-auto"
            >
              Cancelar
            </Button>
            <Button variant="danger" onClick={handleDelete} disabled={saving} className="w-full sm:w-auto">
              {saving ? 'Excluindo...' : 'Excluir Faixa'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default DeliveryZonesPage;
