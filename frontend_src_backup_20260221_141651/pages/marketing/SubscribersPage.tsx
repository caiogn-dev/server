/**
 * Customers/Contacts Management Page
 * 
 * Shows all customers aggregated from:
 * - Orders (customers who made purchases)
 * - Subscribers (manually added or imported)
 */
import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  UserGroupIcon,
  PlusIcon,
  MagnifyingGlassIcon,
  ArrowUpTrayIcon,
  ArrowDownTrayIcon,
  EnvelopeIcon,
  CheckCircleIcon,
  XCircleIcon,
  TrashIcon,
  ShoppingBagIcon,
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
import { Card, Button, Modal, Loading } from '../../components/common';
import { useStore } from '../../hooks';
import { marketingService, Subscriber } from '../../services/marketingService';
import logger from '../../services/logger';

// =============================================================================
// TYPES
// =============================================================================

interface NewSubscriber {
  email: string;
  name: string;
  phone: string;
  tags: string[];
}

// =============================================================================
// COMPONENT
// =============================================================================

export const SubscribersPage: React.FC = () => {
  const navigate = useNavigate();
  const { storeId, storeName } = useStore();

  // State
  const [loading, setLoading] = useState(true);
  const [subscribers, setSubscribers] = useState<Subscriber[]>([]);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [showAddModal, setShowAddModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [newSubscriber, setNewSubscriber] = useState<NewSubscriber>({
    email: '',
    name: '',
    phone: '',
    tags: [],
  });
  const [importText, setImportText] = useState('');
  const [saving, setSaving] = useState(false);

  // =============================================================================
  // DATA LOADING
  // =============================================================================

  useEffect(() => {
    const loadCustomers = async () => {
      if (!storeId) {
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        // This now fetches from /customers/ which aggregates orders + subscribers
        const data = await marketingService.subscribers.list(storeId);
        setSubscribers(data);
        logger.info('Loaded customers', { count: data.length });
      } catch (error) {
        logger.error('Failed to load customers', error);
        toast.error('Erro ao carregar contatos');
      } finally {
        setLoading(false);
      }
    };

    loadCustomers();
  }, [storeId]);

  // =============================================================================
  // COMPUTED VALUES
  // =============================================================================

  const filteredSubscribers = useMemo(() => {
    let result = subscribers;

    // Status filter
    if (statusFilter !== 'all') {
      result = result.filter(s => s.status === statusFilter);
    }

    // Search
    if (search) {
      const searchLower = search.toLowerCase();
      result = result.filter(s =>
        s.email.toLowerCase().includes(searchLower) ||
        s.name.toLowerCase().includes(searchLower) ||
        s.phone?.toLowerCase().includes(searchLower)
      );
    }

    return result;
  }, [subscribers, statusFilter, search]);

  const stats = useMemo(() => ({
    total: subscribers.length,
    active: subscribers.filter(s => s.status === 'active').length,
    withOrders: subscribers.filter(s => (s.total_orders || 0) > 0).length,
    unsubscribed: subscribers.filter(s => s.status === 'unsubscribed').length,
  }), [subscribers]);

  // =============================================================================
  // HANDLERS
  // =============================================================================

  const handleAddSubscriber = async () => {
    if (!storeId) return;
    if (!newSubscriber.email) {
      toast.error('Email é obrigatório');
      return;
    }

    setSaving(true);
    try {
      const created = await marketingService.subscribers.create({
        store: storeId,
        email: newSubscriber.email,
        name: newSubscriber.name,
        phone: newSubscriber.phone,
        tags: newSubscriber.tags,
        status: 'active',
        accepts_marketing: true,
      });

      setSubscribers(prev => [created, ...prev]);
      setShowAddModal(false);
      setNewSubscriber({ email: '', name: '', phone: '', tags: [] });
      toast.success('Contato adicionado!');
    } catch (error) {
      logger.error('Failed to add subscriber', error);
      toast.error('Erro ao adicionar contato');
    } finally {
      setSaving(false);
    }
  };

  const handleImport = async () => {
    if (!storeId) return;
    if (!importText.trim()) {
      toast.error('Cole os contatos para importar');
      return;
    }

    setSaving(true);
    try {
      // Parse CSV/text - expect format: email,name or just email per line
      const lines = importText.trim().split('\n');
      const contacts = lines.map(line => {
        const parts = line.split(',').map(p => p.trim());
        return {
          email: parts[0],
          name: parts[1] || '',
          phone: parts[2] || '',
        };
      }).filter(c => c.email && c.email.includes('@'));

      if (contacts.length === 0) {
        toast.error('Nenhum email válido encontrado');
        return;
      }

      const result = await marketingService.subscribers.importCsv(storeId, contacts);
      
      // Reload subscribers
      const data = await marketingService.subscribers.list(storeId);
      setSubscribers(data);

      setShowImportModal(false);
      setImportText('');
      toast.success(`Importados: ${result.created} novos, ${result.updated} atualizados`);
    } catch (error) {
      logger.error('Failed to import subscribers', error);
      toast.error('Erro ao importar contatos');
    } finally {
      setSaving(false);
    }
  };

  const handleExport = () => {
    const csv = filteredSubscribers
      .map(s => `${s.email},${s.name},${s.phone || ''},${s.status}`)
      .join('\n');
    
    const blob = new Blob([`email,name,phone,status\n${csv}`], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `subscribers-${storeName || 'export'}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Exportação iniciada');
  };

  const handleUnsubscribe = async (subscriber: Subscriber) => {
    try {
      await marketingService.subscribers.unsubscribe(subscriber.id);
      setSubscribers(prev =>
        prev.map(s => s.id === subscriber.id ? { ...s, status: 'unsubscribed' as const } : s)
      );
      toast.success('Contato descadastrado');
    } catch (error) {
      logger.error('Failed to unsubscribe', error);
      toast.error('Erro ao descadastrar');
    }
  };

  // =============================================================================
  // RENDER
  // =============================================================================

  if (!storeId) {
    return (
      <div className="p-6 text-center">
        <UserGroupIcon className="w-16 h-16 text-gray-300 mx-auto mb-4" />
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">Nenhuma loja selecionada</h2>
        <p className="text-gray-500 dark:text-zinc-400 mb-4">Selecione uma loja para gerenciar contatos.</p>
        <Button onClick={() => navigate('/stores')}>Ver Lojas</Button>
      </div>
    );
  }

  if (loading) {
    return <Loading />;
  }

  return (
    <div className="p-4 md:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Contatos</h1>
          <p className="text-gray-500 dark:text-zinc-400">
            Gerencie sua lista de contatos para campanhas de marketing
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => setShowImportModal(true)}>
            <ArrowUpTrayIcon className="w-5 h-5 mr-2" />
            Importar
          </Button>
          <Button variant="secondary" onClick={handleExport}>
            <ArrowDownTrayIcon className="w-5 h-5 mr-2" />
            Exportar
          </Button>
          <Button onClick={() => setShowAddModal(true)}>
            <PlusIcon className="w-5 h-5 mr-2" />
            Adicionar
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 dark:bg-blue-900/40 rounded-lg">
              <UserGroupIcon className="w-6 h-6 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{stats.total}</p>
              <p className="text-sm text-gray-500 dark:text-zinc-400">Total</p>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-100 dark:bg-green-900/40 rounded-lg">
              <CheckCircleIcon className="w-6 h-6 text-green-600 dark:text-green-400" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{stats.active}</p>
              <p className="text-sm text-gray-500 dark:text-zinc-400">Ativos</p>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-100 dark:bg-purple-900/40 rounded-lg">
              <ShoppingBagIcon className="w-6 h-6 text-purple-600 dark:text-purple-400" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{stats.withOrders}</p>
              <p className="text-sm text-gray-500 dark:text-zinc-400">Com Pedidos</p>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-yellow-100 dark:bg-yellow-900/40 rounded-lg">
              <XCircleIcon className="w-6 h-6 text-yellow-600 dark:text-yellow-400" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{stats.unsubscribed}</p>
              <p className="text-sm text-gray-500 dark:text-zinc-400">Descadastrados</p>
            </div>
          </div>
        </Card>
      </div>

      {/* Filters */}
      <Card className="p-4">
        <div className="flex flex-col sm:flex-row gap-4">
          <div className="flex-1 relative">
            <MagnifyingGlassIcon className="w-5 h-5 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
              placeholder="Buscar por email, nome ou telefone..."
            />
          </div>
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            className="px-4 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
          >
            <option value="all">Todos os status</option>
            <option value="active">Ativos</option>
            <option value="unsubscribed">Descadastrados</option>
            <option value="bounced">Bounced</option>
          </select>
        </div>
      </Card>

      {/* Subscribers List */}
      <Card>
        {filteredSubscribers.length === 0 ? (
          <div className="p-12 text-center">
            <UserGroupIcon className="w-16 h-16 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
              {subscribers.length === 0 ? 'Nenhum contato ainda' : 'Nenhum resultado'}
            </h3>
            <p className="text-gray-500 dark:text-zinc-400 mb-4">
              {subscribers.length === 0
                ? 'Adicione contatos para começar suas campanhas de marketing.'
                : 'Tente ajustar os filtros de busca.'}
            </p>
            {subscribers.length === 0 && (
              <Button onClick={() => setShowAddModal(true)}>
                <PlusIcon className="w-5 h-5 mr-2" />
                Adicionar Contato
              </Button>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 dark:bg-black border-b">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-500 dark:text-zinc-400">Contato</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-500 dark:text-zinc-400">Status</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-500 dark:text-zinc-400">Tags</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-500 dark:text-zinc-400">Pedidos</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-500 dark:text-zinc-400">Ações</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {filteredSubscribers.map(subscriber => (
                  <tr key={subscriber.id} className="hover:bg-gray-50 dark:hover:bg-zinc-700 dark:bg-black">
                    <td className="px-4 py-3">
                      <div>
                        <p className="font-medium text-gray-900 dark:text-white">{subscriber.email}</p>
                        {subscriber.name && (
                          <p className="text-sm text-gray-500 dark:text-zinc-400">{subscriber.name}</p>
                        )}
                        {subscriber.phone && (
                          <p className="text-sm text-gray-400">{subscriber.phone}</p>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                        subscriber.status === 'active'
                          ? 'bg-green-100 text-green-700'
                          : subscriber.status === 'unsubscribed'
                          ? 'bg-yellow-100 text-yellow-700'
                          : 'bg-red-100 text-red-700'
                      }`}>
                        {subscriber.status === 'active' ? 'Ativo' :
                         subscriber.status === 'unsubscribed' ? 'Descadastrado' : 'Bounced'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {subscriber.tags?.slice(0, 3).map(tag => (
                          <span key={tag} className="px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-zinc-400 rounded text-xs">
                            {tag}
                          </span>
                        ))}
                        {subscriber.tags && subscriber.tags.length > 3 && (
                          <span className="text-xs text-gray-400">+{subscriber.tags.length - 3}</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-gray-900 dark:text-white">{subscriber.total_orders || 0}</span>
                      {subscriber.total_spent > 0 && (
                        <span className="text-sm text-gray-500 dark:text-zinc-400 ml-1">
                          (R$ {subscriber.total_spent.toFixed(2)})
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => navigate(`/marketing/email/new`)}
                          className="p-1.5 text-gray-400 hover:text-primary-600 hover:bg-primary-50 rounded"
                          title="Enviar email"
                        >
                          <EnvelopeIcon className="w-5 h-5" />
                        </button>
                        {subscriber.status === 'active' && (
                          <button
                            onClick={() => handleUnsubscribe(subscriber)}
                            className="p-1.5 text-gray-400 hover:text-red-600 dark:text-red-400 hover:bg-red-50 rounded"
                            title="Descadastrar"
                          >
                            <TrashIcon className="w-5 h-5" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Add Subscriber Modal */}
      <Modal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        title="Adicionar Contato"
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
              Email *
            </label>
            <input
              type="email"
              value={newSubscriber.email}
              onChange={e => setNewSubscriber(prev => ({ ...prev, email: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
              placeholder="email@exemplo.com"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
              Nome
            </label>
            <input
              type="text"
              value={newSubscriber.name}
              onChange={e => setNewSubscriber(prev => ({ ...prev, name: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
              placeholder="Nome do contato"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
              Telefone
            </label>
            <input
              type="tel"
              value={newSubscriber.phone}
              onChange={e => setNewSubscriber(prev => ({ ...prev, phone: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
              placeholder="(11) 99999-9999"
            />
          </div>
          <div className="flex justify-end gap-2 pt-4">
            <Button variant="secondary" onClick={() => setShowAddModal(false)}>
              Cancelar
            </Button>
            <Button onClick={handleAddSubscriber} disabled={saving}>
              {saving ? 'Salvando...' : 'Adicionar'}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Import Modal */}
      <Modal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        title="Importar Contatos"
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-500 dark:text-zinc-400">
            Cole os contatos no formato: <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">email,nome,telefone</code> (um por linha)
          </p>
          <textarea
            value={importText}
            onChange={e => setImportText(e.target.value)}
            className="w-full h-48 px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500 font-mono text-sm"
            placeholder={`joao@email.com,João Silva,11999999999
maria@email.com,Maria Santos
pedro@email.com`}
          />
          <div className="flex justify-end gap-2 pt-4">
            <Button variant="secondary" onClick={() => setShowImportModal(false)}>
              Cancelar
            </Button>
            <Button onClick={handleImport} disabled={saving}>
              {saving ? 'Importando...' : 'Importar'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default SubscribersPage;
