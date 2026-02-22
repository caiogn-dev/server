import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import {
  ArrowPathIcon,
  FunnelIcon,
  MagnifyingGlassIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  BoltIcon,
  CpuChipIcon,
  ClockIcon,
} from '@heroicons/react/24/outline';
import { format } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import { toast } from 'react-hot-toast';
import { cn } from '../../utils/cn';
import { Loading } from '../../components/common/Loading';
import { IntentBadge } from '../../components/messages';
import { intentService, intentTypeLabels } from '../../services';
import type { IntentLog, IntentType } from '../../types';

const ITEMS_PER_PAGE = 20;

export const IntentLogsPage: React.FC = () => {
  const { companyId } = useParams<{ companyId: string }>();
  const [logs, setLogs] = useState<IntentLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [totalCount, setTotalCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedLog, setSelectedLog] = useState<IntentLog | null>(null);
  
  // Filtros
  const [searchTerm, setSearchTerm] = useState('');
  const [intentFilter, setIntentFilter] = useState<IntentType | ''>('');
  const [methodFilter, setMethodFilter] = useState<'regex' | 'llm' | ''>('');
  const [showFilters, setShowFilters] = useState(false);

  const loadLogs = async () => {
    try {
      setLoading(true);
      const response = await intentService.getLogs({
        limit: ITEMS_PER_PAGE,
        offset: (currentPage - 1) * ITEMS_PER_PAGE,
        intent_type: intentFilter || undefined,
        method: methodFilter || undefined,
      });
      setLogs(response.results);
      setTotalCount(response.count);
    } catch (error) {
      toast.error('Erro ao carregar logs');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLogs();
  }, [currentPage, intentFilter, methodFilter, companyId]);

  // Filtrar por busca local
  const filteredLogs = logs.filter(log => {
    if (!searchTerm) return true;
    const search = searchTerm.toLowerCase();
    return (
      log.message_text?.toLowerCase().includes(search) ||
      log.phone_number?.includes(search) ||
      log.handler_used?.toLowerCase().includes(search)
    );
  });

  const totalPages = Math.ceil(totalCount / ITEMS_PER_PAGE);

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-zinc-900 dark:text-white">
            Logs de Intenções
          </h1>
          <p className="text-zinc-500 dark:text-zinc-400 mt-1">
            Histórico de detecção de intenções
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={cn(
              'flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium',
              'border-zinc-300 dark:border-zinc-600',
              'bg-white dark:bg-zinc-800',
              'text-zinc-700 dark:text-zinc-300',
              'hover:bg-zinc-50 dark:hover:bg-zinc-700',
              showFilters && 'bg-blue-50 border-blue-300 dark:bg-blue-900/20 dark:border-blue-700'
            )}
          >
            <FunnelIcon className="w-4 h-4" />
            Filtros
          </button>
          <button
            onClick={loadLogs}
            className="p-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors"
          >
            <ArrowPathIcon className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Filters */}
      {showFilters && (
        <div className="bg-white dark:bg-zinc-800 rounded-xl p-4 shadow-sm mb-6 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Search */}
            <div className="relative">
              <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-zinc-400" />
              <input
                type="text"
                placeholder="Buscar mensagem, telefone..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className={cn(
                  'w-full pl-10 pr-4 py-2 rounded-lg border text-sm',
                  'border-zinc-300 dark:border-zinc-600',
                  'bg-white dark:bg-zinc-800',
                  'text-zinc-900 dark:text-white',
                  'focus:ring-2 focus:ring-blue-500 focus:border-transparent'
                )}
              />
            </div>

            {/* Intent Filter */}
            <select
              value={intentFilter}
              onChange={(e) => setIntentFilter(e.target.value as IntentType | '')}
              className={cn(
                'px-4 py-2 rounded-lg border text-sm',
                'border-zinc-300 dark:border-zinc-600',
                'bg-white dark:bg-zinc-800',
                'text-zinc-900 dark:text-white'
              )}
            >
              <option value="">Todas as intenções</option>
              {Object.entries(intentTypeLabels).map(([key, label]) => (
                <option key={key} value={key}>{label}</option>
              ))}
            </select>

            {/* Method Filter */}
            <select
              value={methodFilter}
              onChange={(e) => setMethodFilter(e.target.value as 'regex' | 'llm' | '')}
              className={cn(
                'px-4 py-2 rounded-lg border text-sm',
                'border-zinc-300 dark:border-zinc-600',
                'bg-white dark:bg-zinc-800',
                'text-zinc-900 dark:text-white'
              )}
            >
              <option value="">Todos os métodos</option>
              <option value="regex">⚡ Regex (rápido)</option>
              <option value="llm">🤖 LLM (IA)</option>
            </select>
          </div>
        </div>
      )}

      {/* Logs Table */}
      {loading ? (
        <div className="flex items-center justify-center h-96">
          <Loading size="lg" />
        </div>
      ) : filteredLogs.length === 0 ? (
        <div className="text-center py-12 bg-white dark:bg-zinc-800 rounded-xl">
          <p className="text-zinc-500 dark:text-zinc-400">
            Nenhum log encontrado para os filtros selecionados.
          </p>
        </div>
      ) : (
        <div className="bg-white dark:bg-zinc-800 rounded-xl shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-zinc-50 dark:bg-zinc-700/50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase">
                    Horário
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase">
                    Telefone
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase">
                    Mensagem
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase">
                    Intenção
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase">
                    Método
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase">
                    Tempo
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-200 dark:divide-zinc-700">
                {filteredLogs.map((log) => (
                  <tr
                    key={log.id}
                    onClick={() => setSelectedLog(log)}
                    className="hover:bg-zinc-50 dark:hover:bg-zinc-700/50 cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-zinc-600 dark:text-zinc-400">
                      {format(new Date(log.created_at), 'dd/MM HH:mm:ss', { locale: ptBR })}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-zinc-600 dark:text-zinc-400 font-mono">
                      {log.phone_number}
                    </td>
                    <td className="px-4 py-3 text-sm text-zinc-900 dark:text-white max-w-xs truncate">
                      {log.message_text}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <IntentBadge
                        intent={log.intent_type}
                        size="sm"
                        showLabel
                      />
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {log.method === 'regex' && (
                        <span className="inline-flex items-center gap-1 text-sm text-green-600 dark:text-green-400">
                          <BoltIcon className="w-4 h-4" />
                          Regex
                        </span>
                      )}
                      {log.method === 'llm' && (
                        <span className="inline-flex items-center gap-1 text-sm text-purple-600 dark:text-purple-400">
                          <CpuChipIcon className="w-4 h-4" />
                          LLM
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-zinc-600 dark:text-zinc-400">
                      <span className="inline-flex items-center gap-1">
                        <ClockIcon className="w-4 h-4" />
                        {log.processing_time_ms}ms
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between px-4 py-3 border-t border-zinc-200 dark:border-zinc-700">
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              Mostrando {((currentPage - 1) * ITEMS_PER_PAGE) + 1} - {Math.min(currentPage * ITEMS_PER_PAGE, totalCount)} de {totalCount}
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="p-2 rounded-lg border border-zinc-300 dark:border-zinc-600 disabled:opacity-50"
              >
                <ChevronLeftIcon className="w-5 h-5" />
              </button>
              <span className="text-sm text-zinc-600 dark:text-zinc-400">
                Página {currentPage} de {totalPages}
              </span>
              <button
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="p-2 rounded-lg border border-zinc-300 dark:border-zinc-600 disabled:opacity-50"
              >
                <ChevronRightIcon className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Detail Modal */}
      {selectedLog && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
          onClick={() => setSelectedLog(null)}
        >
          <div
            className="bg-white dark:bg-zinc-800 rounded-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-bold text-zinc-900 dark:text-white">
                  Detalhes do Log
                </h2>
                <button
                  onClick={() => setSelectedLog(null)}
                  className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
                >
                  ✕
                </button>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase">
                    Mensagem Recebida
                  </label>
                  <p className="mt-1 p-3 bg-zinc-50 dark:bg-zinc-700/50 rounded-lg text-zinc-900 dark:text-white">
                    {selectedLog.message_text}
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase">
                      Intenção Detectada
                    </label>
                    <div className="mt-1">
                      <IntentBadge
                        intent={selectedLog.intent_type}
                        method={selectedLog.method}
                        confidence={selectedLog.confidence}
                      />
                    </div>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase">
                      Handler Utilizado
                    </label>
                    <p className="mt-1 text-sm text-zinc-900 dark:text-white">
                      {selectedLog.handler_used}
                    </p>
                  </div>
                </div>

                <div>
                  <label className="text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase">
                    Resposta Enviada
                  </label>
                  <p className="mt-1 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg text-sm text-zinc-900 dark:text-white whitespace-pre-wrap">
                    {selectedLog.response_text}
                  </p>
                </div>

                <div className="grid grid-cols-3 gap-4 pt-4 border-t border-zinc-200 dark:border-zinc-700">
                  <div>
                    <label className="text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase">
                      Telefone
                    </label>
                    <p className="text-sm text-zinc-900 dark:text-white font-mono">
                      {selectedLog.phone_number}
                    </p>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase">
                      Tempo de Processamento
                    </label>
                    <p className="text-sm text-zinc-900 dark:text-white">
                      {selectedLog.processing_time_ms}ms
                    </p>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase">
                      Horário
                    </label>
                    <p className="text-sm text-zinc-900 dark:text-white">
                      {format(new Date(selectedLog.created_at), 'dd/MM/yyyy HH:mm:ss', { locale: ptBR })}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default IntentLogsPage;
