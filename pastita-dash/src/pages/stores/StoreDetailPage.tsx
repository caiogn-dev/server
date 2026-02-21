/**
 * Store Detail Page
 * 
 * Comprehensive store management page with tabs for:
 * - Overview/Dashboard
 * - Products
 * - Orders
 * - Coupons
 * - Delivery Zones
 * - Settings
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  ArrowLeftIcon,
  Cog6ToothIcon,
  CubeIcon,
  ShoppingCartIcon,
  TagIcon,
  TruckIcon,
  ChartBarIcon,
  BuildingStorefrontIcon,
  PencilIcon,
  CheckCircleIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
import { Card, Button, Badge, Loading, Modal, Input } from '../../components/common';
import storesApi, { Store, StoreStats } from '../../services/storesApi';
import { useStoreContextStore } from '../../stores';
import logger from '../../services/logger';

type TabId = 'overview' | 'products' | 'orders' | 'coupons' | 'delivery' | 'settings';

interface Tab {
  id: TabId;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  path?: string;
}

const TABS: Tab[] = [
  { id: 'overview', label: 'Visão Geral', icon: ChartBarIcon },
  { id: 'products', label: 'Produtos', icon: CubeIcon, path: 'products' },
  { id: 'orders', label: 'Pedidos', icon: ShoppingCartIcon, path: 'orders' },
  { id: 'coupons', label: 'Cupons', icon: TagIcon, path: 'coupons' },
  { id: 'delivery', label: 'Entrega', icon: TruckIcon, path: 'delivery' },
  { id: 'settings', label: 'Configurações', icon: Cog6ToothIcon, path: 'settings' },
];

export const StoreDetailPage: React.FC = () => {
  const { storeId } = useParams<{ storeId: string }>();
  const navigate = useNavigate();
  const { setSelectedStore } = useStoreContextStore();
  
  const [store, setStore] = useState<Store | null>(null);
  const [stats, setStats] = useState<StoreStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);

  const loadStore = useCallback(async () => {
    if (!storeId) return;
    
    try {
      setLoading(true);
      const [storeData, statsData] = await Promise.all([
        storesApi.getStore(storeId),
        storesApi.getStoreStats(storeId),
      ]);
      setStore(storeData);
      setStats(statsData);
      
      // Set as selected store in context
      setSelectedStore(storeData);
    } catch (error) {
      logger.error('Failed to load store:', error);
      toast.error('Erro ao carregar loja');
      navigate('/stores');
    } finally {
      setLoading(false);
    }
  }, [storeId, navigate, setSelectedStore]);

  useEffect(() => {
    loadStore();
  }, [loadStore]);

  const handleToggleStatus = async () => {
    if (!store) return;
    
    try {
      if (store.status === 'active') {
        await storesApi.deactivateStore(store.id);
        toast.success('Loja desativada');
      } else {
        await storesApi.activateStore(store.id);
        toast.success('Loja ativada');
      }
      loadStore();
    } catch (error) {
      logger.error('Failed to toggle store status:', error);
      toast.error('Erro ao alterar status');
    }
  };

  const handleTabClick = (tab: Tab) => {
    if (tab.path) {
      navigate(`/stores/${storeId}/${tab.path}`);
    } else {
      setActiveTab(tab.id);
    }
  };

  if (loading) {
    return <Loading />;
  }

  if (!store) {
    return (
      <div className="p-6 text-center">
        <p className="text-gray-500 dark:text-zinc-400">Loja não encontrada</p>
        <Button onClick={() => navigate('/stores')} className="mt-4">
          Voltar para Lojas
        </Button>
      </div>
    );
  }

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6">
        <button
          onClick={() => navigate('/stores')}
          className="flex items-center text-gray-600 dark:text-zinc-400 hover:text-gray-900 dark:text-white mb-4"
        >
          <ArrowLeftIcon className="w-4 h-4 mr-2" />
          Voltar para Lojas
        </button>

        <div className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            {store.logo_url ? (
              <img
                src={store.logo_url}
                alt={store.name}
                className="w-16 h-16 rounded-xl object-cover"
              />
            ) : (
              <div className="w-16 h-16 rounded-xl bg-primary-100 flex items-center justify-center">
                <BuildingStorefrontIcon className="w-8 h-8 text-primary-600" />
              </div>
            )}
            <div>
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{store.name}</h1>
              <p className="text-gray-500 dark:text-zinc-400">{store.slug}</p>
              <div className="flex items-center gap-2 mt-1">
                <Badge variant={store.status === 'active' ? 'success' : 'gray'}>
                  {store.status === 'active' ? 'Ativa' : 'Inativa'}
                </Badge>
                <span className="text-sm text-gray-500 dark:text-zinc-400">
                  {store.store_type === 'food' ? '🍕 Alimentação' : store.store_type}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              onClick={() => setIsEditModalOpen(true)}
            >
              <PencilIcon className="w-4 h-4 mr-2" />
              Editar
            </Button>
            <Button
              variant={store.status === 'active' ? 'danger' : 'primary'}
              onClick={handleToggleStatus}
            >
              {store.status === 'active' ? (
                <>
                  <XCircleIcon className="w-4 h-4 mr-2" />
                  Desativar
                </>
              ) : (
                <>
                  <CheckCircleIcon className="w-4 h-4 mr-2" />
                  Ativar
                </>
              )}
            </Button>
          </div>
        </div>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <Card className="p-4">
            <p className="text-sm text-gray-600 dark:text-zinc-400">Receita Total</p>
            <p className="text-2xl font-bold text-green-600 dark:text-green-400">
              R$ {stats.revenue.total.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
            </p>
            <p className="text-xs text-gray-500 dark:text-zinc-400">
              Hoje: R$ {stats.revenue.today.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
            </p>
          </Card>
          <Card className="p-4">
            <p className="text-sm text-gray-600 dark:text-zinc-400">Pedidos</p>
            <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">{stats.orders.total}</p>
            <p className="text-xs text-gray-500 dark:text-zinc-400">
              Hoje: {stats.orders.today}
            </p>
          </Card>
          <Card className="p-4">
            <p className="text-sm text-gray-600 dark:text-zinc-400">Produtos</p>
            <p className="text-2xl font-bold text-purple-600 dark:text-purple-400">{stats.products.total}</p>
            <p className="text-xs text-gray-500 dark:text-zinc-400">
              Ativos: {stats.products.active}
            </p>
          </Card>
          <Card className="p-4">
            <p className="text-sm text-gray-600 dark:text-zinc-400">Clientes</p>
            <p className="text-2xl font-bold text-orange-600">{stats.customers.total}</p>
            <p className="text-xs text-gray-500 dark:text-zinc-400">
              Total cadastrados
            </p>
          </Card>
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-zinc-800 mb-6">
        <nav className="flex gap-4 overflow-x-auto">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => handleTabClick(tab)}
                className={`
                  flex items-center gap-2 px-4 py-3 border-b-2 font-medium text-sm whitespace-nowrap
                  transition-colors duration-200
                  ${isActive 
                    ? 'border-primary-500 text-primary-600' 
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}
                `}
              >
                <Icon className="w-5 h-5" />
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Quick Actions */}
          <Card className="p-6">
            <h3 className="text-lg font-semibold mb-4">Ações Rápidas</h3>
            <div className="grid grid-cols-2 gap-3">
              <Link
                to={`/stores/${storeId}/products`}
                className="flex items-center gap-3 p-4 bg-gray-50 dark:bg-black rounded-lg hover:bg-gray-100 dark:hover:bg-zinc-700 dark:hover:bg-zinc-800 transition-colors"
              >
                <CubeIcon className="w-8 h-8 text-purple-600 dark:text-purple-400" />
                <div>
                  <p className="font-medium">Produtos</p>
                  <p className="text-sm text-gray-500 dark:text-zinc-400">{store.products_count} itens</p>
                </div>
              </Link>
              <Link
                to={`/stores/${storeId}/orders`}
                className="flex items-center gap-3 p-4 bg-gray-50 dark:bg-black rounded-lg hover:bg-gray-100 dark:hover:bg-zinc-700 dark:hover:bg-zinc-800 transition-colors"
              >
                <ShoppingCartIcon className="w-8 h-8 text-blue-600 dark:text-blue-400" />
                <div>
                  <p className="font-medium">Pedidos</p>
                  <p className="text-sm text-gray-500 dark:text-zinc-400">{store.orders_count} pedidos</p>
                </div>
              </Link>
              <Link
                to={`/stores/${storeId}/coupons`}
                className="flex items-center gap-3 p-4 bg-gray-50 dark:bg-black rounded-lg hover:bg-gray-100 dark:hover:bg-zinc-700 dark:hover:bg-zinc-800 transition-colors"
              >
                <TagIcon className="w-8 h-8 text-green-600 dark:text-green-400" />
                <div>
                  <p className="font-medium">Cupons</p>
                  <p className="text-sm text-gray-500 dark:text-zinc-400">Gerenciar descontos</p>
                </div>
              </Link>
              <Link
                to={`/stores/${storeId}/delivery`}
                className="flex items-center gap-3 p-4 bg-gray-50 dark:bg-black rounded-lg hover:bg-gray-100 dark:hover:bg-zinc-700 dark:hover:bg-zinc-800 transition-colors"
              >
                <TruckIcon className="w-8 h-8 text-orange-600" />
                <div>
                  <p className="font-medium">Entrega</p>
                  <p className="text-sm text-gray-500 dark:text-zinc-400">Zonas e taxas</p>
                </div>
              </Link>
            </div>
          </Card>

          {/* Store Info */}
          <Card className="p-6">
            <h3 className="text-lg font-semibold mb-4">Informações da Loja</h3>
            <div className="space-y-3">
              {store.email && (
                <div>
                  <p className="text-sm text-gray-500 dark:text-zinc-400">Email</p>
                  <p className="font-medium">{store.email}</p>
                </div>
              )}
              {store.phone && (
                <div>
                  <p className="text-sm text-gray-500 dark:text-zinc-400">Telefone</p>
                  <p className="font-medium">{store.phone}</p>
                </div>
              )}
              {store.whatsapp_number && (
                <div>
                  <p className="text-sm text-gray-500 dark:text-zinc-400">WhatsApp</p>
                  <p className="font-medium">{store.whatsapp_number}</p>
                </div>
              )}
              {store.address && (
                <div>
                  <p className="text-sm text-gray-500 dark:text-zinc-400">Endereço</p>
                  <p className="font-medium">
                    {store.address}
                    {store.city && `, ${store.city}`}
                    {store.state && ` - ${store.state}`}
                  </p>
                </div>
              )}
              <div className="pt-3 border-t">
                <p className="text-sm text-gray-500 dark:text-zinc-400">Configurações de Entrega</p>
                <div className="flex gap-4 mt-1">
                  <span className={`text-sm ${store.delivery_enabled ? 'text-green-600' : 'text-gray-400'}`}>
                    {store.delivery_enabled ? '✓ Delivery' : '✗ Delivery'}
                  </span>
                  <span className={`text-sm ${store.pickup_enabled ? 'text-green-600' : 'text-gray-400'}`}>
                    {store.pickup_enabled ? '✓ Retirada' : '✗ Retirada'}
                  </span>
                </div>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* Edit Modal */}
      <Modal
        isOpen={isEditModalOpen}
        onClose={() => setIsEditModalOpen(false)}
        title="Editar Loja"
        size="lg"
      >
        <p className="text-gray-500 dark:text-zinc-400">
          Funcionalidade de edição em desenvolvimento.
          Por enquanto, use o Django Admin para editar os dados da loja.
        </p>
        <div className="flex justify-end mt-4">
          <Button onClick={() => setIsEditModalOpen(false)}>
            Fechar
          </Button>
        </div>
      </Modal>
    </div>
  );
};

export default StoreDetailPage;
