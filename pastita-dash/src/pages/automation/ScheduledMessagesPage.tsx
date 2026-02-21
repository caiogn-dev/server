import { useState, useEffect, useCallback } from 'react';
import logger from '../../services/logger';
import { format, parseISO } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import toast from 'react-hot-toast';
import {
  ClockIcon,
  PlusIcon,
  PaperAirplaneIcon,
  XMarkIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  CalendarIcon,
} from '@heroicons/react/24/outline';
import { Card, Button, Badge, Loading, Modal, Input } from '../../components/common';
import { scheduledMessagesService } from '../../services/scheduling';
import { whatsappService } from '../../services';
import {
  ScheduledMessage,
  CreateScheduledMessage,
  ScheduledMessageStats,
  WhatsAppAccount,
  PaginatedResponse,
} from '../../types';

const statusVariants: Record<string, 'gray' | 'info' | 'success' | 'danger' | 'warning'> = {
  pending: 'info',
  processing: 'warning',
  sent: 'success',
  failed: 'danger',
  cancelled: 'gray',
};

const messageTypeLabels: Record<string, string> = {
  text: 'Texto',
  template: 'Template',
  image: 'Imagem',
  document: 'Documento',
  interactive: 'Interativo',
};

export default function ScheduledMessagesPage() {
  const [messages, setMessages] = useState<ScheduledMessage[]>([]);
  const [stats, setStats] = useState<ScheduledMessageStats | null>(null);
  const [accounts, setAccounts] = useState<WhatsAppAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isRescheduleModalOpen, setIsRescheduleModalOpen] = useState(false);
  const [selectedMessage, setSelectedMessage] = useState<ScheduledMessage | null>(null);
  const [newScheduledAt, setNewScheduledAt] = useState('');
  const [filters, setFilters] = useState({
    account_id: '',
    status: '',
  });
  const [formData, setFormData] = useState<CreateScheduledMessage>({
    account_id: '',
    to_number: '',
    contact_name: '',
    message_type: 'text',
    message_text: '',
    scheduled_at: '',
    timezone: 'America/Sao_Paulo',
    notes: '',
  });

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [messagesRes, statsRes, accountsRes] = await Promise.all([
        scheduledMessagesService.list(filters),
        scheduledMessagesService.getStats(filters.account_id || undefined),
        whatsappService.getAccounts(),
      ]);
      setMessages(messagesRes.results);
      setStats(statsRes);
      setAccounts(accountsRes.results);
    } catch (error) {
      toast.error('Erro ao carregar mensagens agendadas');
      logger.error('Failed to load scheduled messages', error);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleCreate = async () => {
    if (!formData.account_id || !formData.to_number || !formData.scheduled_at) {
      toast.error('Preencha os campos obrigatórios');
      return;
    }

    try {
      await scheduledMessagesService.create(formData);
      toast.success('Mensagem agendada com sucesso');
      setIsModalOpen(false);
      setFormData({
        account_id: '',
        to_number: '',
        contact_name: '',
        message_type: 'text',
        message_text: '',
        scheduled_at: '',
        timezone: 'America/Sao_Paulo',
        notes: '',
      });
      fetchData();
    } catch (error) {
      toast.error('Erro ao agendar mensagem');
      logger.error('Failed to schedule message', error);
    }
  };

  const handleCancel = async (id: string) => {
    if (!confirm('Deseja cancelar esta mensagem agendada?')) return;

    try {
      await scheduledMessagesService.cancel(id);
      toast.success('Mensagem cancelada');
      fetchData();
    } catch (error) {
      toast.error('Erro ao cancelar mensagem');
      logger.error('Failed to cancel message', error);
    }
  };

  const handleReschedule = async () => {
    if (!selectedMessage || !newScheduledAt) return;

    try {
      await scheduledMessagesService.reschedule(selectedMessage.id, newScheduledAt);
      toast.success('Mensagem reagendada');
      setIsRescheduleModalOpen(false);
      setSelectedMessage(null);
      setNewScheduledAt('');
      fetchData();
    } catch (error) {
      toast.error('Erro ao reagendar mensagem');
      logger.error('Failed to reschedule message', error);
    }
  };

  const openRescheduleModal = (message: ScheduledMessage) => {
    setSelectedMessage(message);
    setNewScheduledAt(message.scheduled_at.slice(0, 16));
    setIsRescheduleModalOpen(true);
  };

  if (loading) {
    return <Loading />;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Mensagens Agendadas</h1>
          <p className="text-gray-600 dark:text-zinc-400">Agende mensagens para envio futuro</p>
        </div>
        <Button onClick={() => setIsModalOpen(true)}>
          <PlusIcon className="h-5 w-5 mr-2" />
          Nova Mensagem
        </Button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
          <Card className="p-4 text-center">
            <p className="text-2xl font-bold text-gray-900 dark:text-white">{stats.total}</p>
            <p className="text-sm text-gray-500 dark:text-zinc-400">Total</p>
          </Card>
          <Card className="p-4 text-center">
            <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">{stats.pending}</p>
            <p className="text-sm text-gray-500 dark:text-zinc-400">Pendentes</p>
          </Card>
          <Card className="p-4 text-center">
            <p className="text-2xl font-bold text-green-600 dark:text-green-400">{stats.sent}</p>
            <p className="text-sm text-gray-500 dark:text-zinc-400">Enviadas</p>
          </Card>
          <Card className="p-4 text-center">
            <p className="text-2xl font-bold text-red-600 dark:text-red-400">{stats.failed}</p>
            <p className="text-sm text-gray-500 dark:text-zinc-400">Falhas</p>
          </Card>
          <Card className="p-4 text-center">
            <p className="text-2xl font-bold text-gray-600 dark:text-zinc-400">{stats.cancelled}</p>
            <p className="text-sm text-gray-500 dark:text-zinc-400">Canceladas</p>
          </Card>
          <Card className="p-4 text-center">
            <p className="text-2xl font-bold text-indigo-600">{stats.scheduled_today}</p>
            <p className="text-sm text-gray-500 dark:text-zinc-400">Agendadas Hoje</p>
          </Card>
          <Card className="p-4 text-center">
            <p className="text-2xl font-bold text-emerald-600">{stats.sent_today}</p>
            <p className="text-sm text-gray-500 dark:text-zinc-400">Enviadas Hoje</p>
          </Card>
        </div>
      )}

      {/* Filters */}
      <Card className="p-4">
        <div className="flex flex-wrap gap-4">
          <select
            className="rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
            value={filters.account_id}
            onChange={(e) => setFilters({ ...filters, account_id: e.target.value })}
          >
            <option value="">Todas as contas</option>
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </select>
          <select
            className="rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
            value={filters.status}
            onChange={(e) => setFilters({ ...filters, status: e.target.value })}
          >
            <option value="">Todos os status</option>
            <option value="pending">Pendente</option>
            <option value="sent">Enviada</option>
            <option value="failed">Falhou</option>
            <option value="cancelled">Cancelada</option>
          </select>
          <Button variant="secondary" onClick={fetchData}>
            <ArrowPathIcon className="h-5 w-5" />
          </Button>
        </div>
      </Card>

      {/* Messages List */}
      <Card>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50 dark:bg-black">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
                  Destinatário
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
                  Tipo
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
                  Agendado Para
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
                  Conta
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
                  Ações
                </th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-zinc-900 divide-y divide-gray-200">
              {messages.map((message) => (
                <tr key={message.id} className="hover:bg-gray-50 dark:hover:bg-zinc-700 dark:bg-black">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div>
                      <p className="font-medium text-gray-900 dark:text-white">{message.to_number}</p>
                      {message.contact_name && (
                        <p className="text-sm text-gray-500 dark:text-zinc-400">{message.contact_name}</p>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="text-sm text-gray-900 dark:text-white">
                      {messageTypeLabels[message.message_type] || message.message_type}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center text-sm text-gray-900 dark:text-white">
                      <CalendarIcon className="h-4 w-4 mr-1 text-gray-400" />
                      {format(parseISO(message.scheduled_at), "dd/MM/yyyy 'às' HH:mm", {
                        locale: ptBR,
                      })}
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <Badge variant={statusVariants[message.status]}>
                      {message.status_display}
                    </Badge>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-zinc-400">
                    {message.account_name}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <div className="flex justify-end gap-2">
                      {message.status === 'pending' && (
                        <>
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => openRescheduleModal(message)}
                          >
                            <ClockIcon className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="danger"
                            size="sm"
                            onClick={() => handleCancel(message.id)}
                          >
                            <XMarkIcon className="h-4 w-4" />
                          </Button>
                        </>
                      )}
                      {message.status === 'failed' && (
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => openRescheduleModal(message)}
                        >
                          <ArrowPathIcon className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {messages.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-gray-500 dark:text-zinc-400">
                    Nenhuma mensagem agendada encontrada
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Create Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Agendar Mensagem"
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">Conta WhatsApp *</label>
            <select
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              value={formData.account_id}
              onChange={(e) => setFormData({ ...formData, account_id: e.target.value })}
            >
              <option value="">Selecione uma conta</option>
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name} ({account.display_phone_number})
                </option>
              ))}
            </select>
          </div>

          <Input
            label="Número do Destinatário *"
            placeholder="5511999999999"
            value={formData.to_number}
            onChange={(e) => setFormData({ ...formData, to_number: e.target.value })}
          />

          <Input
            label="Nome do Contato"
            placeholder="Nome do destinatário"
            value={formData.contact_name || ''}
            onChange={(e) => setFormData({ ...formData, contact_name: e.target.value })}
          />

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">Tipo de Mensagem</label>
            <select
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              value={formData.message_type}
              onChange={(e) =>
                setFormData({ ...formData, message_type: e.target.value as any })
              }
            >
              <option value="text">Texto</option>
              <option value="template">Template</option>
              <option value="image">Imagem</option>
              <option value="document">Documento</option>
              <option value="interactive">Interativo</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">Mensagem</label>
            <textarea
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              rows={4}
              value={formData.message_text || ''}
              onChange={(e) => setFormData({ ...formData, message_text: e.target.value })}
              placeholder="Digite a mensagem..."
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">Data e Hora *</label>
            <input
              type="datetime-local"
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              value={formData.scheduled_at}
              onChange={(e) => setFormData({ ...formData, scheduled_at: e.target.value })}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">Notas</label>
            <textarea
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              rows={2}
              value={formData.notes || ''}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
              placeholder="Notas internas..."
            />
          </div>

          <div className="flex justify-end gap-3 pt-4">
            <Button variant="secondary" onClick={() => setIsModalOpen(false)}>
              Cancelar
            </Button>
            <Button onClick={handleCreate}>
              <PaperAirplaneIcon className="h-5 w-5 mr-2" />
              Agendar
            </Button>
          </div>
        </div>
      </Modal>

      {/* Reschedule Modal */}
      <Modal
        isOpen={isRescheduleModalOpen}
        onClose={() => setIsRescheduleModalOpen(false)}
        title="Reagendar Mensagem"
      >
        <div className="space-y-4">
          <p className="text-gray-600 dark:text-zinc-400">
            Reagendar mensagem para {selectedMessage?.to_number}
          </p>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">Nova Data e Hora</label>
            <input
              type="datetime-local"
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              value={newScheduledAt}
              onChange={(e) => setNewScheduledAt(e.target.value)}
            />
          </div>

          <div className="flex justify-end gap-3 pt-4">
            <Button variant="secondary" onClick={() => setIsRescheduleModalOpen(false)}>
              Cancelar
            </Button>
            <Button onClick={handleReschedule}>
              <ClockIcon className="h-5 w-5 mr-2" />
              Reagendar
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
