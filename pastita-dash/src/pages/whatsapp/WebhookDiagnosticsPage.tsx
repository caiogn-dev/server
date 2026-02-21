/**
 * WhatsApp Webhook Diagnostics Page
 * 
 * Provides real-time diagnostics for WhatsApp webhook processing,
 * helping identify and fix issues with message reception.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  CheckCircleIcon,
  XCircleIcon,
  ExclamationTriangleIcon,
  ArrowPathIcon,
  SignalIcon,
  ServerIcon,
  ChatBubbleLeftRightIcon,
  ClockIcon,
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
import { Card, Button, Loading, Badge } from '../../components/common';
import api from '@/services/api';
import logger from '@/services/logger';

interface DiagnosticsData {
  status: string;
  server_time: string;
  celery_status: string;
  stats: {
    webhook_events: {
      total: number;
      pending: number;
      processing: number;
      completed: number;
      failed: number;
      last_24h: number;
      last_hour: number;
    };
    messages: {
      total_inbound: number;
      total_outbound: number;
      inbound_last_24h: number;
      inbound_last_hour: number;
    };
  };
  accounts: Array<{
    id: string;
    name: string;
    phone_number: string;
    phone_number_id: string;
    status: string;
    is_active: boolean;
    auto_response_enabled: boolean;
  }>;
  recent_events: Array<{
    id: string;
    event_type: string;
    processing_status: string;
    created_at: string;
    error_message: string | null;
    account_id: string | null;
    retry_count: number;
  }>;
  recent_inbound_messages: Array<{
    id: string;
    from_number: string;
    text_body: string | null;
    message_type: string;
    created_at: string;
    account_id: string;
  }>;
  failed_events: Array<{
    id: string;
    event_type: string;
    error_message: string | null;
    retry_count: number;
    created_at: string;
  }>;
  diagnosis: {
    has_active_accounts: boolean;
    has_pending_events: boolean;
    has_failed_events: boolean;
    celery_connected: boolean;
    receiving_webhooks: boolean;
    receiving_messages: boolean;
  };
}

const StatusIndicator: React.FC<{ ok: boolean; label: string }> = ({ ok, label }) => (
  <div className="flex items-center gap-2">
    {ok ? (
      <CheckCircleIcon className="w-5 h-5 text-green-500" />
    ) : (
      <XCircleIcon className="w-5 h-5 text-red-500" />
    )}
    <span className={ok ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'}>
      {label}
    </span>
  </div>
);

export const WebhookDiagnosticsPage: React.FC = () => {
  const [data, setData] = useState<DiagnosticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [reprocessing, setReprocessing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);

  const fetchDiagnostics = useCallback(async () => {
    try {
      const response = await api.get('/webhooks/whatsapp/debug/');
      setData(response.data);
    } catch (error) {
      logger.error('Failed to fetch diagnostics', error);
      toast.error('Erro ao carregar diagnóstico');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDiagnostics();
  }, [fetchDiagnostics]);

  useEffect(() => {
    if (autoRefresh) {
      const interval = setInterval(fetchDiagnostics, 5000);
      return () => clearInterval(interval);
    }
  }, [autoRefresh, fetchDiagnostics]);

  const handleReprocess = async (action: string) => {
    setReprocessing(true);
    try {
      const response = await api.post('/webhooks/whatsapp/debug/', { action, limit: 50 });
      const results = response.data.results;
      toast.success(`Reprocessado: ${results.processed} sucesso, ${results.failed} falhas`);
      fetchDiagnostics();
    } catch (error) {
      logger.error('Failed to reprocess events', error);
      toast.error('Erro ao reprocessar eventos');
    } finally {
      setReprocessing(false);
    }
  };

  if (loading) {
    return <Loading />;
  }

  if (!data) {
    return (
      <div className="p-6">
        <Card className="p-6 text-center">
          <ExclamationTriangleIcon className="w-12 h-12 text-yellow-500 mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
            Erro ao carregar diagnóstico
          </h2>
          <Button onClick={fetchDiagnostics}>Tentar novamente</Button>
        </Card>
      </div>
    );
  }

  const { diagnosis, stats, accounts, recent_events, recent_inbound_messages, failed_events } = data;

  // Calculate overall health
  const healthScore = [
    diagnosis.has_active_accounts,
    diagnosis.celery_connected,
    !diagnosis.has_failed_events,
    diagnosis.receiving_webhooks,
    diagnosis.receiving_messages,
  ].filter(Boolean).length;

  const healthStatus = healthScore >= 4 ? 'healthy' : healthScore >= 2 ? 'warning' : 'critical';

  return (
    <div className="p-4 md:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Diagnóstico de Webhooks WhatsApp
          </h1>
          <p className="text-gray-500 dark:text-zinc-400">
            Monitore o recebimento de mensagens em tempo real
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-zinc-400">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded border-gray-300"
            />
            Auto-refresh (5s)
          </label>
          <Button variant="secondary" onClick={fetchDiagnostics}>
            <ArrowPathIcon className="w-5 h-5" />
          </Button>
        </div>
      </div>

      {/* Health Status */}
      <Card className={`p-6 border-l-4 ${
        healthStatus === 'healthy' ? 'border-l-green-500 bg-green-50 dark:bg-green-900/20' :
        healthStatus === 'warning' ? 'border-l-yellow-500 bg-yellow-50 dark:bg-yellow-900/20' :
        'border-l-red-500 bg-red-50 dark:bg-red-900/20'
      }`}>
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
              Status do Sistema
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <StatusIndicator ok={diagnosis.has_active_accounts} label="Contas ativas" />
              <StatusIndicator ok={diagnosis.celery_connected} label="Celery conectado" />
              <StatusIndicator ok={!diagnosis.has_failed_events} label="Sem eventos falhos" />
              <StatusIndicator ok={diagnosis.receiving_webhooks} label="Recebendo webhooks" />
              <StatusIndicator ok={diagnosis.receiving_messages} label="Recebendo mensagens" />
              <StatusIndicator ok={!diagnosis.has_pending_events} label="Sem eventos pendentes" />
            </div>
          </div>
          <div className={`text-4xl font-bold ${
            healthStatus === 'healthy' ? 'text-green-600' :
            healthStatus === 'warning' ? 'text-yellow-600' :
            'text-red-600'
          }`}>
            {healthScore}/5
          </div>
        </div>
      </Card>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <SignalIcon className="w-8 h-8 text-blue-500" />
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {stats.webhook_events.last_hour}
              </p>
              <p className="text-sm text-gray-500">Webhooks (última hora)</p>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <ChatBubbleLeftRightIcon className="w-8 h-8 text-green-500" />
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {stats.messages.inbound_last_hour}
              </p>
              <p className="text-sm text-gray-500">Mensagens (última hora)</p>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <ClockIcon className="w-8 h-8 text-yellow-500" />
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {stats.webhook_events.pending}
              </p>
              <p className="text-sm text-gray-500">Eventos pendentes</p>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <XCircleIcon className="w-8 h-8 text-red-500" />
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {stats.webhook_events.failed}
              </p>
              <p className="text-sm text-gray-500">Eventos com falha</p>
            </div>
          </div>
        </Card>
      </div>

      {/* Accounts */}
      <Card className="p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Contas WhatsApp
        </h3>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead>
              <tr>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Nome</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Telefone</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Phone Number ID</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Ativo</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {accounts.map((account) => (
                <tr key={account.id}>
                  <td className="px-4 py-2 text-sm text-gray-900 dark:text-white">{account.name}</td>
                  <td className="px-4 py-2 text-sm text-gray-600 dark:text-zinc-400">{account.phone_number}</td>
                  <td className="px-4 py-2 text-sm font-mono text-gray-600 dark:text-zinc-400">{account.phone_number_id}</td>
                  <td className="px-4 py-2">
                    <Badge variant={account.status === 'active' ? 'success' : 'warning'}>
                      {account.status}
                    </Badge>
                  </td>
                  <td className="px-4 py-2">
                    {account.is_active ? (
                      <CheckCircleIcon className="w-5 h-5 text-green-500" />
                    ) : (
                      <XCircleIcon className="w-5 h-5 text-red-500" />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Actions */}
      {(diagnosis.has_pending_events || diagnosis.has_failed_events) && (
        <Card className="p-6 bg-yellow-50 dark:bg-yellow-900/20">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Ações de Recuperação
          </h3>
          <div className="flex flex-wrap gap-4">
            {diagnosis.has_pending_events && (
              <Button
                onClick={() => handleReprocess('reprocess_pending')}
                disabled={reprocessing}
              >
                {reprocessing ? 'Processando...' : `Processar ${stats.webhook_events.pending} eventos pendentes`}
              </Button>
            )}
            {diagnosis.has_failed_events && (
              <Button
                variant="secondary"
                onClick={() => handleReprocess('reprocess_failed')}
                disabled={reprocessing}
              >
                {reprocessing ? 'Processando...' : `Reprocessar ${stats.webhook_events.failed} eventos com falha`}
              </Button>
            )}
          </div>
        </Card>
      )}

      {/* Failed Events */}
      {failed_events.length > 0 && (
        <Card className="p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Eventos com Falha (últimos 5)
          </h3>
          <div className="space-y-3">
            {failed_events.map((event) => (
              <div key={event.id} className="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
                <div className="flex justify-between items-start">
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">
                      {event.event_type} - Tentativas: {event.retry_count}
                    </p>
                    <p className="text-sm text-red-600 dark:text-red-400 mt-1">
                      {event.error_message || 'Erro desconhecido'}
                    </p>
                  </div>
                  <span className="text-xs text-gray-500">
                    {new Date(event.created_at).toLocaleString('pt-BR')}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Recent Events */}
      <Card className="p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Eventos Recentes (últimos 20)
        </h3>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead>
              <tr>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Tipo</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Data</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Erro</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {recent_events.map((event) => (
                <tr key={event.id}>
                  <td className="px-4 py-2 text-sm text-gray-900 dark:text-white">{event.event_type}</td>
                  <td className="px-4 py-2">
                    <Badge variant={
                      event.processing_status === 'completed' ? 'success' :
                      event.processing_status === 'failed' ? 'danger' :
                      event.processing_status === 'pending' ? 'warning' :
                      'info'
                    }>
                      {event.processing_status}
                    </Badge>
                  </td>
                  <td className="px-4 py-2 text-sm text-gray-600 dark:text-zinc-400">
                    {new Date(event.created_at).toLocaleString('pt-BR')}
                  </td>
                  <td className="px-4 py-2 text-sm text-red-600 dark:text-red-400 max-w-xs truncate">
                    {event.error_message || '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Recent Messages */}
      <Card className="p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Mensagens Recebidas (últimas 10)
        </h3>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead>
              <tr>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">De</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Tipo</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Mensagem</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Data</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {recent_inbound_messages.map((msg) => (
                <tr key={msg.id}>
                  <td className="px-4 py-2 text-sm text-gray-900 dark:text-white">{msg.from_number}</td>
                  <td className="px-4 py-2 text-sm text-gray-600 dark:text-zinc-400">{msg.message_type}</td>
                  <td className="px-4 py-2 text-sm text-gray-600 dark:text-zinc-400 max-w-xs truncate">
                    {msg.text_body || '-'}
                  </td>
                  <td className="px-4 py-2 text-sm text-gray-600 dark:text-zinc-400">
                    {new Date(msg.created_at).toLocaleString('pt-BR')}
                  </td>
                </tr>
              ))}
              {recent_inbound_messages.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-gray-500">
                    Nenhuma mensagem recebida recentemente
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Server Info */}
      <Card className="p-4 bg-gray-50 dark:bg-zinc-900">
        <div className="flex items-center gap-4 text-sm text-gray-600 dark:text-zinc-400">
          <ServerIcon className="w-5 h-5" />
          <span>Servidor: {new Date(data.server_time).toLocaleString('pt-BR')}</span>
          <span>|</span>
          <span>Celery: {data.celery_status}</span>
        </div>
      </Card>
    </div>
  );
};

export default WebhookDiagnosticsPage;
