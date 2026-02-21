/**
 * Stores Management Page
 * Main page for managing all stores in the platform
 */
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Store, Settings, Package, ShoppingCart, Users, BarChart3, Zap, RefreshCw } from 'lucide-react';
import { Card, Button, Loading, Badge, Modal, Input } from '../../components/common';
import logger from '../../services/logger';
import storesApi, { Store as StoreType, StoreInput, StoreStats } from '../../services/storesApi';

const StoresPage: React.FC = () => {
  const navigate = useNavigate();
  const [stores, setStores] = useState<StoreType[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [selectedStore, setSelectedStore] = useState<StoreType | null>(null);
  const [storeStats, setStoreStats] = useState<Record<string, StoreStats>>({});

  useEffect(() => {
    loadStores();
  }, []);

  const loadStores = async () => {
    try {
      setLoading(true);
      const response = await storesApi.getStores();
      setStores(response.results);
      
      // Load stats for each store
      for (const store of response.results) {
        try {
          const stats = await storesApi.getStoreStats(store.id);
          setStoreStats(prev => ({ ...prev, [store.id]: stats }));
        } catch (error) {
          logger.error(`Failed to load stats for store ${store.id}`, error);
        }
      }
    } catch (error) {
      logger.error('Failed to load stores', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateStore = async (data: StoreInput) => {
    try {
      const newStore = await storesApi.createStore(data);
      setStores(prev => [newStore, ...prev]);
      setShowCreateModal(false);
    } catch (error) {
      logger.error('Failed to create store', error);
    }
  };

  const handleToggleStatus = async (store: StoreType) => {
    try {
      if (store.status === 'active') {
        await storesApi.deactivateStore(store.id);
      } else {
        await storesApi.activateStore(store.id);
      }
      loadStores();
    } catch (error) {
      logger.error('Failed to toggle store status', error);
    }
  };

  const handleSyncPastita = async (storeId: string) => {
    try {
      const result = await storesApi.syncPastitaToStore(storeId);
      alert(`Sincronização concluída!\n${JSON.stringify(result.synced, null, 2)}`);
      loadStores();
    } catch (error) {
      logger.error('Failed to sync Pastita', error);
    }
  };

  const getStatusBadge = (status: string) => {
    const variants: Record<string, 'success' | 'warning' | 'danger' | 'gray'> = {
      active: 'success',
      inactive: 'gray',
      suspended: 'danger',
      pending: 'warning',
    };
    return <Badge variant={variants[status] || 'gray'}>{status}</Badge>;
  };

  const getStoreTypeLabel = (type: string) => {
    const labels: Record<string, string> = {
      food: '🍕 Alimentação',
      retail: '🛍️ Varejo',
      services: '🔧 Serviços',
      digital: '💻 Digital',
      other: '📦 Outro',
    };
    return labels[type] || type;
  };

  if (loading) {
    return <Loading />;
  }

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Lojas</h1>
          <p className="text-gray-600 dark:text-zinc-400">Gerencie todas as suas lojas e integrações</p>
        </div>
        <Button onClick={() => setShowCreateModal(true)}>
          <Plus className="w-4 h-4 mr-2" />
          Nova Loja
        </Button>
      </div>

      {/* Stats Overview */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 dark:bg-blue-900/40 rounded-lg">
              <Store className="w-6 h-6 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <p className="text-sm text-gray-600 dark:text-zinc-400">Total de Lojas</p>
              <p className="text-2xl font-bold">{stores.length}</p>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-100 dark:bg-green-900/40 rounded-lg">
              <Package className="w-6 h-6 text-green-600 dark:text-green-400" />
            </div>
            <div>
              <p className="text-sm text-gray-600 dark:text-zinc-400">Total de Produtos</p>
              <p className="text-2xl font-bold">
                {stores.reduce((acc, s) => acc + s.products_count, 0)}
              </p>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-100 dark:bg-purple-900/40 rounded-lg">
              <ShoppingCart className="w-6 h-6 text-purple-600 dark:text-purple-400" />
            </div>
            <div>
              <p className="text-sm text-gray-600 dark:text-zinc-400">Total de Pedidos</p>
              <p className="text-2xl font-bold">
                {stores.reduce((acc, s) => acc + s.orders_count, 0)}
              </p>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-orange-100 rounded-lg">
              <Zap className="w-6 h-6 text-orange-600" />
            </div>
            <div>
              <p className="text-sm text-gray-600 dark:text-zinc-400">Integrações Ativas</p>
              <p className="text-2xl font-bold">
                {stores.reduce((acc, s) => acc + s.integrations_count, 0)}
              </p>
            </div>
          </div>
        </Card>
      </div>

      {/* Stores Grid */}
      {stores.length === 0 ? (
        <Card className="p-12 text-center">
          <Store className="w-16 h-16 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">Nenhuma loja cadastrada</h3>
          <p className="text-gray-600 dark:text-zinc-400 mb-4">Crie sua primeira loja para começar a vender</p>
          <Button onClick={() => setShowCreateModal(true)}>
            <Plus className="w-4 h-4 mr-2" />
            Criar Loja
          </Button>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {stores.map(store => {
            const stats = storeStats[store.id];
            return (
              <Card key={store.id} className="overflow-hidden">
                {/* Store Header */}
                <div className="p-4 border-b">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      {store.logo_url ? (
                        <img
                          src={store.logo_url}
                          alt={store.name}
                          className="w-12 h-12 rounded-lg object-cover"
                        />
                      ) : (
                        <div className="w-12 h-12 rounded-lg bg-gray-100 dark:bg-gray-700 flex items-center justify-center">
                          <Store className="w-6 h-6 text-gray-400" />
                        </div>
                      )}
                      <div>
                        <h3 className="font-semibold text-gray-900 dark:text-white">{store.name}</h3>
                        <p className="text-sm text-gray-500 dark:text-zinc-400">{getStoreTypeLabel(store.store_type)}</p>
                      </div>
                    </div>
                    {getStatusBadge(store.status)}
                  </div>
                </div>

                {/* Store Stats */}
                <div className="p-4 grid grid-cols-3 gap-4 text-center border-b">
                  <div>
                    <p className="text-2xl font-bold text-gray-900 dark:text-white">{store.products_count}</p>
                    <p className="text-xs text-gray-500 dark:text-zinc-400">Produtos</p>
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-gray-900 dark:text-white">{store.orders_count}</p>
                    <p className="text-xs text-gray-500 dark:text-zinc-400">Pedidos</p>
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-gray-900 dark:text-white">{store.integrations_count}</p>
                    <p className="text-xs text-gray-500 dark:text-zinc-400">Integrações</p>
                  </div>
                </div>

                {/* Revenue Stats */}
                {stats && (
                  <div className="p-4 bg-gray-50 dark:bg-black border-b">
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-gray-600 dark:text-zinc-400">Receita Total</span>
                      <span className="font-semibold text-green-600 dark:text-green-400">
                        R$ {stats.revenue.total.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                      </span>
                    </div>
                    <div className="flex justify-between items-center mt-1">
                      <span className="text-sm text-gray-600 dark:text-zinc-400">Hoje</span>
                      <span className="font-medium text-gray-900 dark:text-white">
                        R$ {stats.revenue.today.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                      </span>
                    </div>
                  </div>
                )}

                {/* Actions */}
                <div className="p-4 flex flex-wrap gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => navigate(`/stores/${store.id}`)}
                  >
                    <Settings className="w-4 h-4 mr-1" />
                    Gerenciar
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => navigate(`/stores/${store.id}/products`)}
                  >
                    <Package className="w-4 h-4 mr-1" />
                    Produtos
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => navigate(`/stores/${store.id}/orders`)}
                  >
                    <ShoppingCart className="w-4 h-4 mr-1" />
                    Pedidos
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => navigate(`/stores/${store.id}/analytics`)}
                  >
                    <BarChart3 className="w-4 h-4 mr-1" />
                    Analytics
                  </Button>
                  {store.slug === 'pastita' && (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => handleSyncPastita(store.id)}
                    >
                      <RefreshCw className="w-4 h-4 mr-1" />
                      Sync Pastita
                    </Button>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Create Store Modal */}
      <CreateStoreModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onSubmit={handleCreateStore}
      />
    </div>
  );
};

// Create Store Modal Component
interface CreateStoreModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: StoreInput) => Promise<void>;
}

const CreateStoreModal: React.FC<CreateStoreModalProps> = ({ isOpen, onClose, onSubmit }) => {
  const [formData, setFormData] = useState<StoreInput>({
    name: '',
    slug: '',
    description: '',
    store_type: 'food',
    email: '',
    phone: '',
    whatsapp_number: '',
    address: '',
    city: '',
    state: '',
    zip_code: '',
    delivery_enabled: true,
    pickup_enabled: true,
    min_order_value: 0,
    default_delivery_fee: 10,
  });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await onSubmit(formData);
      setFormData({
        name: '',
        slug: '',
        description: '',
        store_type: 'food',
        email: '',
        phone: '',
        whatsapp_number: '',
        address: '',
        city: '',
        state: '',
        zip_code: '',
        delivery_enabled: true,
        pickup_enabled: true,
        min_order_value: 0,
        default_delivery_fee: 10,
      });
    } finally {
      setSaving(false);
    }
  };

  const generateSlug = (name: string) => {
    return name
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, '');
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Nova Loja" size="lg">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <Input
            label="Nome da Loja"
            value={formData.name}
            onChange={e => {
              setFormData(prev => ({
                ...prev,
                name: e.target.value,
                slug: generateSlug(e.target.value)
              }));
            }}
            required
          />
          <Input
            label="Slug (URL)"
            value={formData.slug}
            onChange={e => setFormData(prev => ({ ...prev, slug: e.target.value }))}
            required
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">Tipo de Loja</label>
          <select
            value={formData.store_type}
            onChange={e => setFormData(prev => ({ ...prev, store_type: e.target.value }))}
            className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-blue-500"
          >
            <option value="food">🍕 Alimentação</option>
            <option value="retail">🛍️ Varejo</option>
            <option value="services">🔧 Serviços</option>
            <option value="digital">💻 Digital</option>
            <option value="other">📦 Outro</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">Descrição</label>
          <textarea
            value={formData.description}
            onChange={e => setFormData(prev => ({ ...prev, description: e.target.value }))}
            rows={3}
            className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Input
            label="Email"
            type="email"
            value={formData.email}
            onChange={e => setFormData(prev => ({ ...prev, email: e.target.value }))}
          />
          <Input
            label="Telefone"
            value={formData.phone}
            onChange={e => setFormData(prev => ({ ...prev, phone: e.target.value }))}
          />
        </div>

        <Input
          label="WhatsApp"
          value={formData.whatsapp_number}
          onChange={e => setFormData(prev => ({ ...prev, whatsapp_number: e.target.value }))}
          placeholder="5511999999999"
        />

        <div className="grid grid-cols-3 gap-4">
          <Input
            label="Cidade"
            value={formData.city}
            onChange={e => setFormData(prev => ({ ...prev, city: e.target.value }))}
          />
          <Input
            label="Estado"
            value={formData.state}
            onChange={e => setFormData(prev => ({ ...prev, state: e.target.value }))}
          />
          <Input
            label="CEP"
            value={formData.zip_code}
            onChange={e => setFormData(prev => ({ ...prev, zip_code: e.target.value }))}
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Input
            label="Pedido Mínimo (R$)"
            type="number"
            value={formData.min_order_value}
            onChange={e => setFormData(prev => ({ ...prev, min_order_value: parseFloat(e.target.value) || 0 }))}
          />
          <Input
            label="Taxa de Entrega Padrão (R$)"
            type="number"
            value={formData.default_delivery_fee}
            onChange={e => setFormData(prev => ({ ...prev, default_delivery_fee: parseFloat(e.target.value) || 0 }))}
          />
        </div>

        <div className="flex gap-4">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={formData.delivery_enabled}
              onChange={e => setFormData(prev => ({ ...prev, delivery_enabled: e.target.checked }))}
              className="rounded"
            />
            <span className="text-sm">Entrega habilitada</span>
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={formData.pickup_enabled}
              onChange={e => setFormData(prev => ({ ...prev, pickup_enabled: e.target.checked }))}
              className="rounded"
            />
            <span className="text-sm">Retirada habilitada</span>
          </label>
        </div>

        <div className="flex justify-end gap-3 pt-4 border-t">
          <Button variant="secondary" onClick={onClose} type="button">
            Cancelar
          </Button>
          <Button type="submit" disabled={saving}>
            {saving ? 'Criando...' : 'Criar Loja'}
          </Button>
        </div>
      </form>
    </Modal>
  );
};

export default StoresPage;
