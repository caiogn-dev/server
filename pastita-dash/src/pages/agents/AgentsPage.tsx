import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  PlusIcon, 
  MagnifyingGlassIcon,
  FunnelIcon,
  CpuChipIcon,
  ArrowPathIcon
} from '@heroicons/react/24/outline';
import { cn } from '../../utils/cn';
import { AgentCard } from '../../components/agents';
import agentsService, { Agent } from '../../services/agents';

type StatusFilter = 'all' | 'active' | 'inactive' | 'draft';
type ProviderFilter = 'all' | 'kimi' | 'openai' | 'anthropic' | 'ollama';

export const AgentsPage: React.FC = () => {
  const navigate = useNavigate();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [providerFilter, setProviderFilter] = useState<ProviderFilter>('all');
  const [showFilters, setShowFilters] = useState(false);

  const loadAgents = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await agentsService.getAgents();
      setAgents(data);
    } catch (error) {
      console.error('Erro ao carregar agentes:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAgents();
  }, [loadAgents]);

  const handleToggleStatus = async (id: string) => {
    const agent = agents.find(a => a.id === id);
    if (!agent) return;

    try {
      const newStatus = agent.status === 'active' ? 'inactive' : 'active';
      await agentsService.updateAgent(id, { status: newStatus });
      setAgents(prev => prev.map(a => 
        a.id === id ? { ...a, status: newStatus } : a
      ));
    } catch (error) {
      console.error('Erro ao atualizar status:', error);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Tem certeza que deseja excluir este agente?')) return;

    try {
      await agentsService.deleteAgent(id);
      setAgents(prev => prev.filter(a => a.id !== id));
    } catch (error) {
      console.error('Erro ao excluir agente:', error);
    }
  };

  const filteredAgents = agents.filter(agent => {
    const matchesSearch = agent.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                          agent.description?.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStatus = statusFilter === 'all' || agent.status === statusFilter;
    const matchesProvider = providerFilter === 'all' || agent.provider === providerFilter;
    
    return matchesSearch && matchesStatus && matchesProvider;
  });

  const stats = {
    total: agents.length,
    active: agents.filter(a => a.status === 'active').length,
    inactive: agents.filter(a => a.status === 'inactive').length,
    draft: agents.filter(a => a.status === 'draft').length,
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-bold text-zinc-900 dark:text-white">
            Agentes IA
          </h1>
          <p className="text-zinc-500 dark:text-zinc-400 mt-1">
            Gerencie seus agentes de inteligência artificial
          </p>
        </div>
        <button
          onClick={() => navigate('/agents/new')}
          className={cn(
            "inline-flex items-center gap-2 px-4 py-2.5 rounded-lg font-medium",
            "bg-primary-600 hover:bg-primary-700 text-white",
            "transition-colors shadow-sm"
          )}
        >
          <PlusIcon className="w-5 h-5" />
          Novo Agente
        </button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        <div className="bg-white dark:bg-zinc-900 rounded-xl p-4 border border-zinc-200 dark:border-zinc-800">
          <div className="text-2xl font-bold text-zinc-900 dark:text-white">{stats.total}</div>
          <div className="text-sm text-zinc-500 dark:text-zinc-400">Total de Agentes</div>
        </div>
        <div className="bg-white dark:bg-zinc-900 rounded-xl p-4 border border-zinc-200 dark:border-zinc-800">
          <div className="text-2xl font-bold text-green-600">{stats.active}</div>
          <div className="text-sm text-zinc-500 dark:text-zinc-400">Ativos</div>
        </div>
        <div className="bg-white dark:bg-zinc-900 rounded-xl p-4 border border-zinc-200 dark:border-zinc-800">
          <div className="text-2xl font-bold text-gray-500">{stats.inactive}</div>
          <div className="text-sm text-zinc-500 dark:text-zinc-400">Inativos</div>
        </div>
        <div className="bg-white dark:bg-zinc-900 rounded-xl p-4 border border-zinc-200 dark:border-zinc-800">
          <div className="text-2xl font-bold text-yellow-500">{stats.draft}</div>
          <div className="text-sm text-zinc-500 dark:text-zinc-400">Rascunhos</div>
        </div>
      </div>

      {/* Search & Filters */}
      <div className="flex flex-col sm:flex-row gap-4 mb-6">
        {/* Search */}
        <div className="relative flex-1">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-zinc-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            placeholder="Buscar agentes..."
            className={cn(
              "w-full pl-10 pr-4 py-2.5 rounded-lg border",
              "bg-white dark:bg-zinc-900",
              "text-zinc-900 dark:text-white placeholder-zinc-400",
              "border-zinc-200 dark:border-zinc-700",
              "focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            )}
          />
        </div>

        {/* Filters Toggle */}
        <button
          onClick={() => setShowFilters(!showFilters)}
          className={cn(
            "inline-flex items-center gap-2 px-4 py-2.5 rounded-lg border",
            "bg-white dark:bg-zinc-900",
            "text-zinc-700 dark:text-zinc-300",
            "border-zinc-200 dark:border-zinc-700",
            "hover:bg-zinc-50 dark:hover:bg-zinc-800",
            showFilters && "bg-zinc-100 dark:bg-zinc-800"
          )}
        >
          <FunnelIcon className="w-5 h-5" />
          Filtros
        </button>

        {/* Refresh */}
        <button
          onClick={loadAgents}
          disabled={isLoading}
          className={cn(
            "inline-flex items-center gap-2 px-4 py-2.5 rounded-lg border",
            "bg-white dark:bg-zinc-900",
            "text-zinc-700 dark:text-zinc-300",
            "border-zinc-200 dark:border-zinc-700",
            "hover:bg-zinc-50 dark:hover:bg-zinc-800",
            "disabled:opacity-50"
          )}
        >
          <ArrowPathIcon className={cn("w-5 h-5", isLoading && "animate-spin")} />
        </button>
      </div>

      {/* Filters Panel */}
      {showFilters && (
        <div className="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-4 mb-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                Status
              </label>
              <select
                value={statusFilter}
                onChange={e => setStatusFilter(e.target.value as StatusFilter)}
                className={cn(
                  "w-full px-3 py-2 rounded-lg border",
                  "bg-white dark:bg-zinc-800",
                  "text-zinc-900 dark:text-white",
                  "border-zinc-200 dark:border-zinc-700"
                )}
              >
                <option value="all">Todos</option>
                <option value="active">Ativos</option>
                <option value="inactive">Inativos</option>
                <option value="draft">Rascunhos</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                Provedor
              </label>
              <select
                value={providerFilter}
                onChange={e => setProviderFilter(e.target.value as ProviderFilter)}
                className={cn(
                  "w-full px-3 py-2 rounded-lg border",
                  "bg-white dark:bg-zinc-800",
                  "text-zinc-900 dark:text-white",
                  "border-zinc-200 dark:border-zinc-700"
                )}
              >
                <option value="all">Todos</option>
                <option value="kimi">Kimi</option>
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
                <option value="ollama">Ollama</option>
              </select>
            </div>
          </div>
        </div>
      )}

      {/* Agents Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[...Array(6)].map((_, i) => (
            <div 
              key={i}
              className="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 h-64 animate-pulse"
            />
          ))}
        </div>
      ) : filteredAgents.length === 0 ? (
        <div className="text-center py-16">
          <CpuChipIcon className="w-20 h-20 mx-auto text-zinc-200 dark:text-zinc-700 mb-4" />
          {agents.length === 0 ? (
            <>
              <p className="text-xl font-medium text-zinc-900 dark:text-white mb-2">
                Nenhum agente criado
              </p>
              <p className="text-zinc-500 dark:text-zinc-400 mb-6">
                Crie seu primeiro agente IA para automatizar atendimentos
              </p>
              <button
                onClick={() => navigate('/agents/new')}
                className={cn(
                  "inline-flex items-center gap-2 px-6 py-3 rounded-lg font-medium",
                  "bg-primary-600 hover:bg-primary-700 text-white",
                  "transition-colors"
                )}
              >
                <PlusIcon className="w-5 h-5" />
                Criar Primeiro Agente
              </button>
            </>
          ) : (
            <>
              <p className="text-xl font-medium text-zinc-900 dark:text-white mb-2">
                Nenhum resultado encontrado
              </p>
              <p className="text-zinc-500 dark:text-zinc-400">
                Tente ajustar os filtros ou termo de busca
              </p>
            </>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredAgents.map(agent => (
            <AgentCard
              key={agent.id}
              agent={agent}
              onEdit={id => navigate(`/agents/${id}`)}
              onDelete={handleDelete}
              onToggleStatus={handleToggleStatus}
              onTest={id => navigate(`/agents/${id}/test`)}
              onViewConversations={id => navigate(`/agents/${id}/conversations`)}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default AgentsPage;
