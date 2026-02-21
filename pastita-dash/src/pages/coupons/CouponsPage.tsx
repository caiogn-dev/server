import React, { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import logger from '../../services/logger';
import {
  PlusIcon,
  PencilIcon,
  TrashIcon,
  MagnifyingGlassIcon,
  TagIcon,
  CheckCircleIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline';
import { Card, Button, Input, Badge, Modal, Loading } from '../../components/common';
import { couponsService, Coupon, CreateCoupon, UpdateCoupon, CouponStats } from '../../services/coupons';
import { useStore } from '../../hooks';

export const CouponsPage: React.FC = () => {
  const { storeId: routeStoreId } = useParams<{ storeId?: string }>();
  const { storeId: contextStoreId, storeName, isStoreSelected } = useStore();
  
  // Use route storeId if available, otherwise use context
  const storeId = routeStoreId || contextStoreId;
  const [coupons, setCoupons] = useState<Coupon[]>([]);
  const [stats, setStats] = useState<CouponStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filterActive, setFilterActive] = useState<boolean | undefined>(undefined);
  const [filterType, setFilterType] = useState<'percentage' | 'fixed' | ''>('');
  
  // Modal states
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [editingCoupon, setEditingCoupon] = useState<Coupon | null>(null);
  const [deletingCoupon, setDeletingCoupon] = useState<Coupon | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form state - includes store ID
  const getInitialFormData = useCallback((): CreateCoupon => ({
    store: storeId || undefined,
    code: '',
    description: '',
    discount_type: 'percentage',
    discount_value: 0,
    min_purchase: 0,
    max_discount: null,
    usage_limit: null,
    is_active: true,
    valid_from: new Date().toISOString().split('T')[0],
    valid_until: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
  }), [storeId]);

  const [formData, setFormData] = useState<CreateCoupon>(getInitialFormData());

  const loadCoupons = useCallback(async () => {
    if (!storeId) {
      setLoading(false);
      return;
    }
    
    try {
      setLoading(true);
      setError(null);
      const [couponsData, statsData] = await Promise.all([
        couponsService.getCoupons({
          store: storeId,
          search: search || undefined,
          is_active: filterActive,
          discount_type: filterType || undefined,
        }),
        couponsService.getStats(storeId),
      ]);
      setCoupons(couponsData.results);
      setStats(statsData);
    } catch (err) {
      logger.error('Error loading coupons:', err);
      setError('Erro ao carregar cupons');
    } finally {
      setLoading(false);
    }
  }, [search, filterActive, filterType, storeId]);

  // Reload when store changes
  useEffect(() => {
    loadCoupons();
  }, [loadCoupons]);

  // Update form data when store changes
  useEffect(() => {
    setFormData(prev => ({ ...prev, store: storeId || undefined }));
  }, [storeId]);

  const handleOpenModal = (coupon?: Coupon) => {
    if (coupon) {
      setEditingCoupon(coupon);
      setFormData({
        code: coupon.code,
        description: coupon.description,
        discount_type: coupon.discount_type,
        discount_value: coupon.discount_value,
        min_purchase: coupon.min_purchase,
        max_discount: coupon.max_discount,
        usage_limit: coupon.usage_limit,
        is_active: coupon.is_active,
        valid_from: coupon.valid_from.split('T')[0],
        valid_until: coupon.valid_until.split('T')[0],
      });
    } else {
      setEditingCoupon(null);
      setFormData({
        code: '',
        description: '',
        discount_type: 'percentage',
        discount_value: 0,
        min_purchase: 0,
        max_discount: null,
        usage_limit: null,
        is_active: true,
        valid_from: new Date().toISOString().split('T')[0],
        valid_until: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
      });
    }
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setEditingCoupon(null);
  };

  const handleSave = async () => {
    if (!storeId) {
      setError('Selecione uma loja antes de criar um cupom');
      return;
    }

    try {
      setSaving(true);
      setError(null);
      
      // Ensure store is always included
      const dataToSave = { ...formData, store: storeId };
      
      if (editingCoupon) {
        await couponsService.updateCoupon(editingCoupon.id, dataToSave as UpdateCoupon);
      } else {
        await couponsService.createCoupon(dataToSave);
      }
      handleCloseModal();
      loadCoupons();
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Erro ao salvar cupom';
      logger.error('Error saving coupon:', err);
      setError(errorMessage);
    } finally {
      setSaving(false);
    }
  };

  const handleToggleActive = async (coupon: Coupon) => {
    try {
      await couponsService.toggleActive(coupon.id);
      loadCoupons();
    } catch (error) {
      logger.error('Error toggling coupon:', error);
    }
  };

  const handleDelete = async () => {
    if (!deletingCoupon) return;
    try {
      setSaving(true);
      await couponsService.deleteCoupon(deletingCoupon.id);
      setIsDeleteModalOpen(false);
      setDeletingCoupon(null);
      loadCoupons();
    } catch (error) {
      logger.error('Error deleting coupon:', error);
    } finally {
      setSaving(false);
    }
  };

  const formatMoney = (value: number | string | null | undefined) => {
    const numeric = typeof value === 'number' ? value : Number.parseFloat(String(value ?? '0'));
    if (Number.isNaN(numeric)) return '0.00';
    return numeric.toFixed(2);
  };

  const formatDiscount = (coupon: Coupon) => {
    if (coupon.discount_type === 'percentage') {
      return `${coupon.discount_value}%`;
    }
    return `R$ ${formatMoney(coupon.discount_value)}`;
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('pt-BR');
  };

  if (loading && coupons.length === 0) {
    return <Loading />;
  }

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-gray-900 dark:text-white">Cupons de Desconto</h1>
          <p className="text-sm md:text-base text-gray-500 dark:text-zinc-400">Gerencie os cupons de desconto da loja</p>
        </div>
        <Button onClick={() => handleOpenModal()} className="w-full sm:w-auto">
          <PlusIcon className="w-5 h-5 mr-2" />
          Novo Cupom
        </Button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
          <Card className="p-3 md:p-4">
            <div className="flex items-center">
              <div className="p-2 bg-blue-100 dark:bg-blue-900/40 rounded-lg shrink-0">
                <TagIcon className="w-5 h-5 md:w-6 md:h-6 text-blue-600 dark:text-blue-400" />
              </div>
              <div className="ml-3 md:ml-4 min-w-0">
                <p className="text-xs md:text-sm text-gray-500 dark:text-zinc-400 truncate">Total</p>
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
                <p className="text-xs md:text-sm text-gray-500 dark:text-zinc-400 truncate">Ativos</p>
                <p className="text-lg md:text-2xl font-bold text-gray-900 dark:text-white">{stats.active}</p>
              </div>
            </div>
          </Card>
          <Card className="p-3 md:p-4">
            <div className="flex items-center">
              <div className="p-2 bg-gray-100 dark:bg-gray-700 rounded-lg shrink-0">
                <XCircleIcon className="w-5 h-5 md:w-6 md:h-6 text-gray-600 dark:text-zinc-400" />
              </div>
              <div className="ml-3 md:ml-4 min-w-0">
                <p className="text-xs md:text-sm text-gray-500 dark:text-zinc-400 truncate">Inativos</p>
                <p className="text-lg md:text-2xl font-bold text-gray-900 dark:text-white">{stats.inactive}</p>
              </div>
            </div>
          </Card>
          <Card className="p-3 md:p-4">
            <div className="flex items-center">
              <div className="p-2 bg-purple-100 dark:bg-purple-900/40 rounded-lg shrink-0">
                <TagIcon className="w-5 h-5 md:w-6 md:h-6 text-purple-600 dark:text-purple-400" />
              </div>
              <div className="ml-3 md:ml-4 min-w-0">
                <p className="text-xs md:text-sm text-gray-500 dark:text-zinc-400 truncate">Usos Totais</p>
                <p className="text-lg md:text-2xl font-bold text-gray-900 dark:text-white">{stats.total_usage}</p>
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
                placeholder="Buscar por código..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-10"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 sm:flex gap-2 sm:gap-3">
            <select
              value={filterActive === undefined ? '' : String(filterActive)}
              onChange={(e) => setFilterActive(e.target.value === '' ? undefined : e.target.value === 'true')}
              className="px-2 sm:px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent text-sm"
            >
              <option value="">Status</option>
              <option value="true">Ativos</option>
              <option value="false">Inativos</option>
            </select>
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value as 'percentage' | 'fixed' | '')}
              className="px-2 sm:px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent text-sm"
            >
              <option value="">Tipo</option>
              <option value="percentage">%</option>
              <option value="fixed">R$</option>
            </select>
          </div>
        </div>
      </Card>

      {/* Coupons List */}
      <Card>
        {/* Mobile Cards View */}
        <div className="block md:hidden divide-y divide-gray-200">
          {coupons.map((coupon) => (
            <div key={coupon.id} className="p-4 space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <TagIcon className="w-5 h-5 text-gray-400 shrink-0" />
                  <div>
                    <p className="font-mono font-bold text-gray-900 dark:text-white">{coupon.code}</p>
                    {coupon.description && (
                      <p className="text-xs text-gray-500 dark:text-zinc-400">{coupon.description}</p>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => handleToggleActive(coupon)}
                  className="focus:outline-none shrink-0"
                >
                  <Badge variant={coupon.is_active && coupon.is_valid_now ? 'success' : 'danger'}>
                    {coupon.is_active ? (coupon.is_valid_now ? 'Ativo' : 'Expirado') : 'Inativo'}
                  </Badge>
                </button>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-gray-500 dark:text-zinc-400">Desconto:</span>
                  <Badge variant={coupon.discount_type === 'percentage' ? 'info' : 'success'} className="ml-1">
                    {formatDiscount(coupon)}
                  </Badge>
                </div>
                <div>
                  <span className="text-gray-500 dark:text-zinc-400">Uso:</span>
                  <span className="ml-1 text-gray-700 dark:text-zinc-300">
                    {coupon.used_count}{coupon.usage_limit && ` / ${coupon.usage_limit}`}
                  </span>
                </div>
                <div>
                  <span className="text-gray-500 dark:text-zinc-400">Mín:</span>
                  <span className="ml-1 text-gray-700 dark:text-zinc-300">
                    {Number(coupon.min_purchase || 0) > 0 ? `R$ ${formatMoney(coupon.min_purchase)}` : '-'}
                  </span>
                </div>
                <div>
                  <span className="text-gray-500 dark:text-zinc-400">Até:</span>
                  <span className="ml-1 text-gray-700 dark:text-zinc-300">{formatDate(coupon.valid_until)}</span>
                </div>
              </div>
              <div className="flex items-center justify-end gap-1 pt-2 border-t border-gray-100">
                <button
                  onClick={() => handleOpenModal(coupon)}
                  className="p-2 text-primary-600 hover:bg-primary-50 rounded-lg"
                >
                  <PencilIcon className="w-5 h-5" />
                </button>
                <button
                  onClick={() => {
                    setDeletingCoupon(coupon);
                    setIsDeleteModalOpen(true);
                  }}
                  className="p-2 text-red-600 dark:text-red-400 hover:bg-red-50 rounded-lg"
                >
                  <TrashIcon className="w-5 h-5" />
                </button>
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
                  Código
                </th>
                <th className="px-4 lg:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
                  Desconto
                </th>
                <th className="px-4 lg:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
                  Mín. Compra
                </th>
                <th className="px-4 lg:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
                  Uso
                </th>
                <th className="px-4 lg:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
                  Validade
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
              {coupons.map((coupon) => (
                <tr key={coupon.id} className="hover:bg-gray-50 dark:hover:bg-zinc-700 dark:bg-black">
                  <td className="px-4 lg:px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center">
                      <TagIcon className="w-5 h-5 text-gray-400 mr-2" />
                      <div>
                        <div className="font-mono font-bold text-gray-900 dark:text-white">{coupon.code}</div>
                        {coupon.description && (
                          <div className="text-sm text-gray-500 dark:text-zinc-400 max-w-[200px] truncate">{coupon.description}</div>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-4 lg:px-6 py-4 whitespace-nowrap">
                    <Badge variant={coupon.discount_type === 'percentage' ? 'info' : 'success'}>
                      {formatDiscount(coupon)}
                    </Badge>
                  </td>
                  <td className="px-4 lg:px-6 py-4 whitespace-nowrap text-sm text-gray-600 dark:text-zinc-400">
                    {Number(coupon.min_purchase || 0) > 0 ? `R$ ${formatMoney(coupon.min_purchase)}` : '-'}
                  </td>
                  <td className="px-4 lg:px-6 py-4 whitespace-nowrap text-sm text-gray-600 dark:text-zinc-400">
                    {coupon.used_count}
                    {coupon.usage_limit && ` / ${coupon.usage_limit}`}
                  </td>
                  <td className="px-4 lg:px-6 py-4 whitespace-nowrap text-sm text-gray-600 dark:text-zinc-400">
                    <div>{formatDate(coupon.valid_from)}</div>
                    <div className="text-xs text-gray-500 dark:text-zinc-400">até {formatDate(coupon.valid_until)}</div>
                  </td>
                  <td className="px-4 lg:px-6 py-4 whitespace-nowrap">
                    <button
                      onClick={() => handleToggleActive(coupon)}
                      className="focus:outline-none"
                    >
                      <Badge variant={coupon.is_active && coupon.is_valid_now ? 'success' : 'danger'}>
                        {coupon.is_active ? (coupon.is_valid_now ? 'Ativo' : 'Expirado') : 'Inativo'}
                      </Badge>
                    </button>
                  </td>
                  <td className="px-4 lg:px-6 py-4 whitespace-nowrap text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={() => handleOpenModal(coupon)}
                        className="p-2 text-primary-600 hover:bg-primary-50 rounded-lg transition-colors"
                        title="Editar"
                      >
                        <PencilIcon className="w-5 h-5" />
                      </button>
                      <button
                        onClick={() => {
                          setDeletingCoupon(coupon);
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

        {coupons.length === 0 && (
          <div className="text-center py-12 px-4">
            <TagIcon className="mx-auto h-12 w-12 text-gray-400" />
            <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-white">Nenhum cupom encontrado</h3>
            <p className="mt-1 text-sm text-gray-500 dark:text-zinc-400">
              Comece criando um novo cupom de desconto.
            </p>
            <div className="mt-6">
              <Button onClick={() => handleOpenModal()}>
                <PlusIcon className="w-5 h-5 mr-2" />
                Novo Cupom
              </Button>
            </div>
          </div>
        )}
      </Card>

      {/* Create/Edit Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        title={editingCoupon ? 'Editar Cupom' : 'Novo Cupom'}
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
              Código do Cupom *
            </label>
            <Input
              type="text"
              value={formData.code}
              onChange={(e) => setFormData({ ...formData, code: e.target.value.toUpperCase() })}
              placeholder="Ex: DESCONTO10"
              className="font-mono"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
              Descrição
            </label>
            <Input
              type="text"
              value={formData.description || ''}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="Descrição do cupom"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                Tipo de Desconto *
              </label>
              <select
                value={formData.discount_type}
                onChange={(e) => setFormData({ ...formData, discount_type: e.target.value as 'percentage' | 'fixed' })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
              >
                <option value="percentage">Porcentagem (%)</option>
                <option value="fixed">Valor Fixo (R$)</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                Valor do Desconto *
              </label>
              <Input
                type="number"
                value={formData.discount_value}
                onChange={(e) => setFormData({ ...formData, discount_value: parseFloat(e.target.value) || 0 })}
                min="0"
                step={formData.discount_type === 'percentage' ? '1' : '0.01'}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                Compra Mínima (R$)
              </label>
              <Input
                type="number"
                value={formData.min_purchase || 0}
                onChange={(e) => setFormData({ ...formData, min_purchase: parseFloat(e.target.value) || 0 })}
                min="0"
                step="0.01"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                Desconto Máximo (R$)
              </label>
              <Input
                type="number"
                value={formData.max_discount || ''}
                onChange={(e) => setFormData({ ...formData, max_discount: e.target.value ? parseFloat(e.target.value) : null })}
                min="0"
                step="0.01"
                placeholder="Sem limite"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
              Limite de Uso
            </label>
            <Input
              type="number"
              value={formData.usage_limit || ''}
              onChange={(e) => setFormData({ ...formData, usage_limit: e.target.value ? parseInt(e.target.value) : null })}
              min="0"
              placeholder="Sem limite"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                Válido a partir de *
              </label>
              <Input
                type="date"
                value={formData.valid_from}
                onChange={(e) => setFormData({ ...formData, valid_from: e.target.value })}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                Válido até *
              </label>
              <Input
                type="date"
                value={formData.valid_until}
                onChange={(e) => setFormData({ ...formData, valid_until: e.target.value })}
              />
            </div>
          </div>

          <div className="flex items-center">
            <input
              type="checkbox"
              id="is_active"
              checked={formData.is_active}
              onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
              className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 dark:border-zinc-700 rounded"
            />
            <label htmlFor="is_active" className="ml-2 block text-sm text-gray-900 dark:text-white">
              Cupom ativo
            </label>
          </div>

          <div className="flex justify-end gap-3 pt-4">
            <Button variant="secondary" onClick={handleCloseModal}>
              Cancelar
            </Button>
            <Button onClick={handleSave} disabled={saving || !formData.code || !formData.discount_value}>
              {saving ? 'Salvando...' : editingCoupon ? 'Salvar' : 'Criar'}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={isDeleteModalOpen}
        onClose={() => {
          setIsDeleteModalOpen(false);
          setDeletingCoupon(null);
        }}
        title="Excluir Cupom"
      >
        <div className="space-y-4">
          <p className="text-gray-600 dark:text-zinc-400">
            Tem certeza que deseja excluir o cupom <strong>{deletingCoupon?.code}</strong>?
            Esta ação não pode ser desfeita.
          </p>
          <div className="flex justify-end gap-3">
            <Button
              variant="secondary"
              onClick={() => {
                setIsDeleteModalOpen(false);
                setDeletingCoupon(null);
              }}
            >
              Cancelar
            </Button>
            <Button variant="danger" onClick={handleDelete} disabled={saving}>
              {saving ? 'Excluindo...' : 'Excluir'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default CouponsPage;
