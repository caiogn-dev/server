import { useState, useEffect, useCallback } from 'react';
import logger from '../../services/logger';
import { format, parseISO } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import toast from 'react-hot-toast';
import {
  DocumentChartBarIcon,
  PlusIcon,
  PlayIcon,
  PauseIcon,
  ArrowDownTrayIcon,
  EnvelopeIcon,
  ArrowPathIcon,
  ClockIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
} from '@heroicons/react/24/outline';
import { Card, Button, Badge, Loading, Modal, Input } from '../../components/common';
import {
  reportSchedulesService,
  generatedReportsService,
} from '../../services/scheduling';
import { whatsappService, companyProfileApi } from '../../services';
import {
  ReportSchedule,
  CreateReportSchedule,
  GeneratedReport,
  WhatsAppAccount,
  CompanyProfile,
  PaginatedResponse,
} from '../../types';

const statusVariants: Record<string, 'gray' | 'info' | 'success' | 'danger' | 'warning'> = {
  active: 'success',
  paused: 'warning',
  disabled: 'gray',
  generating: 'info',
  completed: 'success',
  failed: 'danger',
};

const reportTypeLabels: Record<string, string> = {
  messages: 'Mensagens',
  orders: 'Pedidos',
  conversations: 'Conversas',
  automation: 'Automação',
  payments: 'Pagamentos',
  full: 'Completo',
};

const frequencyLabels: Record<string, string> = {
  daily: 'Diário',
  weekly: 'Semanal',
  monthly: 'Mensal',
};

const dayOfWeekLabels: Record<number, string> = {
  1: 'Segunda',
  2: 'Terça',
  3: 'Quarta',
  4: 'Quinta',
  5: 'Sexta',
  6: 'Sábado',
  7: 'Domingo',
};

export default function ReportsPage() {
  const [schedules, setSchedules] = useState<ReportSchedule[]>([]);
  const [reports, setReports] = useState<GeneratedReport[]>([]);
  const [accounts, setAccounts] = useState<WhatsAppAccount[]>([]);
  const [companies, setCompanies] = useState<CompanyProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'schedules' | 'reports'>('schedules');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isGenerateModalOpen, setIsGenerateModalOpen] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    report_type: 'full' as 'messages' | 'orders' | 'conversations' | 'automation' | 'payments' | 'full',
    frequency: 'weekly' as 'daily' | 'weekly' | 'monthly',
    day_of_week: 1,
    day_of_month: 1,
    hour: 8,
    timezone: 'America/Sao_Paulo',
    recipients: [] as string[],
    include_charts: true,
    export_format: 'xlsx' as 'csv' | 'xlsx',
  });
  const [generateData, setGenerateData] = useState({
    report_type: 'full',
    period_start: '',
    period_end: '',
    account_id: '',
    company_id: '',
    recipients: '',
    export_format: 'xlsx',
  });
  const [recipientInput, setRecipientInput] = useState('');

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [schedulesRes, reportsRes, accountsRes, companiesRes] = await Promise.all([
        reportSchedulesService.list(),
        generatedReportsService.list(),
        whatsappService.getAccounts(),
        companyProfileApi.list(),
      ]);
      setSchedules(schedulesRes.results);
      setReports(reportsRes.results);
      setAccounts(accountsRes.results);
      setCompanies(companiesRes.results);
    } catch (error) {
      toast.error('Erro ao carregar dados');
      logger.error('Failed to load reports data', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleCreateSchedule = async () => {
    if (!formData.name || formData.recipients.length === 0) {
      toast.error('Preencha o nome e adicione pelo menos um destinatário');
      return;
    }

    try {
      await reportSchedulesService.create(formData);
      toast.success('Agendamento criado com sucesso');
      setIsModalOpen(false);
      setFormData({
        name: '',
        description: '',
        report_type: 'full',
        frequency: 'weekly',
        day_of_week: 1,
        day_of_month: 1,
        hour: 8,
        timezone: 'America/Sao_Paulo',
        recipients: [],
        include_charts: true,
        export_format: 'xlsx',
      });
      fetchData();
    } catch (error) {
      toast.error('Erro ao criar agendamento');
      logger.error('Failed to create schedule', error);
    }
  };

  const handleRunNow = async (id: string) => {
    try {
      await reportSchedulesService.runNow(id);
      toast.success('Relatório sendo gerado...');
      fetchData();
    } catch (error) {
      toast.error('Erro ao gerar relatório');
      logger.error('Failed to run report now', error);
    }
  };

  const handlePause = async (id: string) => {
    try {
      await reportSchedulesService.pause(id);
      toast.success('Agendamento pausado');
      fetchData();
    } catch (error) {
      toast.error('Erro ao pausar agendamento');
      logger.error('Failed to pause schedule', error);
    }
  };

  const handleResume = async (id: string) => {
    try {
      await reportSchedulesService.resume(id);
      toast.success('Agendamento retomado');
      fetchData();
    } catch (error) {
      toast.error('Erro ao retomar agendamento');
      logger.error('Failed to resume schedule', error);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Deseja excluir este agendamento?')) return;

    try {
      await reportSchedulesService.delete(id);
      toast.success('Agendamento excluído');
      fetchData();
    } catch (error) {
      toast.error('Erro ao excluir agendamento');
      logger.error('Failed to delete schedule', error);
    }
  };

  const handleGenerateReport = async () => {
    try {
      const recipients = generateData.recipients
        .split(',')
        .map((e) => e.trim())
        .filter((e) => e);

      await generatedReportsService.generate({
        report_type: generateData.report_type as any,
        period_start: generateData.period_start || undefined,
        period_end: generateData.period_end || undefined,
        account_id: generateData.account_id || undefined,
        company_id: generateData.company_id || undefined,
        recipients,
        export_format: generateData.export_format as any,
      });
      toast.success('Relatório sendo gerado...');
      setIsGenerateModalOpen(false);
      fetchData();
    } catch (error) {
      toast.error('Erro ao gerar relatório');
      logger.error('Failed to generate report', error);
    }
  };

  const handleDownload = async (report: GeneratedReport) => {
    try {
      const blob = await generatedReportsService.download(report.id);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `${report.name}.${report.file_format}`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      toast.error('Erro ao baixar relatório');
      logger.error('Failed to download report', error);
    }
  };

  const addRecipient = () => {
    if (recipientInput && !formData.recipients.includes(recipientInput)) {
      setFormData({
        ...formData,
        recipients: [...formData.recipients, recipientInput],
      });
      setRecipientInput('');
    }
  };

  const removeRecipient = (email: string) => {
    setFormData({
      ...formData,
      recipients: formData.recipients.filter((r) => r !== email),
    });
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  if (loading) {
    return <Loading />;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Relatórios Automatizados</h1>
          <p className="text-gray-600 dark:text-zinc-400">Configure relatórios periódicos e gere sob demanda</p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setIsGenerateModalOpen(true)}>
            <DocumentChartBarIcon className="h-5 w-5 mr-2" />
            Gerar Agora
          </Button>
          <Button onClick={() => setIsModalOpen(true)}>
            <PlusIcon className="h-5 w-5 mr-2" />
            Novo Agendamento
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-zinc-800">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setActiveTab('schedules')}
            className={`py-4 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'schedules'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Agendamentos ({schedules.length})
          </button>
          <button
            onClick={() => setActiveTab('reports')}
            className={`py-4 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'reports'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Relatórios Gerados ({reports.length})
          </button>
        </nav>
      </div>

      {/* Schedules Tab */}
      {activeTab === 'schedules' && (
        <div className="grid gap-4">
          {schedules.map((schedule) => (
            <Card key={schedule.id} className="p-6">
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="flex items-center gap-3">
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{schedule.name}</h3>
                    <Badge variant={statusVariants[schedule.status]}>
                      {schedule.status_display}
                    </Badge>
                  </div>
                  {schedule.description && (
                    <p className="text-gray-600 dark:text-zinc-400 mt-1">{schedule.description}</p>
                  )}
                  <div className="mt-3 flex flex-wrap gap-4 text-sm text-gray-500 dark:text-zinc-400">
                    <span className="flex items-center">
                      <DocumentChartBarIcon className="h-4 w-4 mr-1" />
                      {reportTypeLabels[schedule.report_type]}
                    </span>
                    <span className="flex items-center">
                      <ClockIcon className="h-4 w-4 mr-1" />
                      {frequencyLabels[schedule.frequency]}
                      {schedule.frequency === 'weekly' &&
                        ` (${dayOfWeekLabels[schedule.day_of_week]})`}
                      {schedule.frequency === 'monthly' && ` (Dia ${schedule.day_of_month})`}
                      {` às ${schedule.hour}:00`}
                    </span>
                    <span className="flex items-center">
                      <EnvelopeIcon className="h-4 w-4 mr-1" />
                      {schedule.recipients.length} destinatário(s)
                    </span>
                  </div>
                  {schedule.next_run_at && (
                    <p className="mt-2 text-sm text-gray-500 dark:text-zinc-400">
                      Próxima execução:{' '}
                      {format(parseISO(schedule.next_run_at), "dd/MM/yyyy 'às' HH:mm", {
                        locale: ptBR,
                      })}
                    </p>
                  )}
                  {schedule.last_error && (
                    <p className="mt-2 text-sm text-red-600 dark:text-red-400">
                      Último erro: {schedule.last_error}
                    </p>
                  )}
                </div>
                <div className="flex gap-2">
                  <Button variant="secondary" size="sm" onClick={() => handleRunNow(schedule.id)}>
                    <PlayIcon className="h-4 w-4" />
                  </Button>
                  {schedule.status === 'active' ? (
                    <Button variant="secondary" size="sm" onClick={() => handlePause(schedule.id)}>
                      <PauseIcon className="h-4 w-4" />
                    </Button>
                  ) : (
                    <Button variant="secondary" size="sm" onClick={() => handleResume(schedule.id)}>
                      <ArrowPathIcon className="h-4 w-4" />
                    </Button>
                  )}
                  <Button variant="danger" size="sm" onClick={() => handleDelete(schedule.id)}>
                    ×
                  </Button>
                </div>
              </div>
            </Card>
          ))}
          {schedules.length === 0 && (
            <Card className="p-12 text-center text-gray-500 dark:text-zinc-400">
              Nenhum agendamento configurado
            </Card>
          )}
        </div>
      )}

      {/* Reports Tab */}
      {activeTab === 'reports' && (
        <Card>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50 dark:bg-black">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
                    Relatório
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
                    Tipo
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
                    Período
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
                    Registros
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
                    Tamanho
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
                    Ações
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-zinc-900 divide-y divide-gray-200">
                {reports.map((report) => (
                  <tr key={report.id} className="hover:bg-gray-50 dark:hover:bg-zinc-700 dark:bg-black">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div>
                        <p className="font-medium text-gray-900 dark:text-white">{report.name}</p>
                        <p className="text-sm text-gray-500 dark:text-zinc-400">
                          {format(parseISO(report.created_at), 'dd/MM/yyyy HH:mm', {
                            locale: ptBR,
                          })}
                        </p>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">
                      {reportTypeLabels[report.report_type] || report.report_type}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-zinc-400">
                      {format(parseISO(report.period_start), 'dd/MM/yyyy', { locale: ptBR })} -{' '}
                      {format(parseISO(report.period_end), 'dd/MM/yyyy', { locale: ptBR })}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <Badge variant={statusVariants[report.status]}>{report.status_display}</Badge>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">
                      {report.records_count.toLocaleString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-zinc-400">
                      {formatFileSize(report.file_size)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      {report.status === 'completed' && (
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => handleDownload(report)}
                        >
                          <ArrowDownTrayIcon className="h-4 w-4" />
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
                {reports.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-6 py-12 text-center text-gray-500 dark:text-zinc-400">
                      Nenhum relatório gerado
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Create Schedule Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Novo Agendamento de Relatório"
      >
        <div className="space-y-4">
          <Input
            label="Nome *"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            placeholder="Ex: Relatório Semanal de Vendas"
          />

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">Descrição</label>
            <textarea
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              rows={2}
              value={formData.description || ''}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">Tipo de Relatório</label>
              <select
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                value={formData.report_type}
                onChange={(e) => setFormData({ ...formData, report_type: e.target.value as any })}
              >
                <option value="full">Completo</option>
                <option value="messages">Mensagens</option>
                <option value="orders">Pedidos</option>
                <option value="conversations">Conversas</option>
                <option value="automation">Automação</option>
                <option value="payments">Pagamentos</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">Frequência</label>
              <select
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                value={formData.frequency}
                onChange={(e) => setFormData({ ...formData, frequency: e.target.value as any })}
              >
                <option value="daily">Diário</option>
                <option value="weekly">Semanal</option>
                <option value="monthly">Mensal</option>
              </select>
            </div>
          </div>

          {formData.frequency === 'weekly' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">Dia da Semana</label>
              <select
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                value={formData.day_of_week}
                onChange={(e) =>
                  setFormData({ ...formData, day_of_week: parseInt(e.target.value) })
                }
              >
                {Object.entries(dayOfWeekLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
          )}

          {formData.frequency === 'monthly' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">Dia do Mês</label>
              <select
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                value={formData.day_of_month}
                onChange={(e) =>
                  setFormData({ ...formData, day_of_month: parseInt(e.target.value) })
                }
              >
                {Array.from({ length: 28 }, (_, i) => i + 1).map((day) => (
                  <option key={day} value={day}>
                    {day}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">Hora de Envio</label>
            <select
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              value={formData.hour}
              onChange={(e) => setFormData({ ...formData, hour: parseInt(e.target.value) })}
            >
              {Array.from({ length: 24 }, (_, i) => i).map((hour) => (
                <option key={hour} value={hour}>
                  {hour.toString().padStart(2, '0')}:00
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">
              Destinatários (Email) *
            </label>
            <div className="flex gap-2 mt-1">
              <input
                type="email"
                className="flex-1 rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                value={recipientInput}
                onChange={(e) => setRecipientInput(e.target.value)}
                placeholder="email@exemplo.com"
                onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), addRecipient())}
              />
              <Button variant="secondary" onClick={addRecipient}>
                Adicionar
              </Button>
            </div>
            <div className="flex flex-wrap gap-2 mt-2">
              {formData.recipients.map((email) => (
                <span
                  key={email}
                  className="inline-flex items-center px-2 py-1 rounded-full text-sm bg-gray-100 dark:bg-gray-700"
                >
                  {email}
                  <button
                    type="button"
                    className="ml-1 text-gray-500 dark:text-zinc-400 hover:text-gray-700 dark:hover:text-zinc-300 dark:hover:text-zinc-300"
                    onClick={() => removeRecipient(email)}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">Formato</label>
              <select
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                value={formData.export_format}
                onChange={(e) =>
                  setFormData({ ...formData, export_format: e.target.value as any })
                }
              >
                <option value="xlsx">Excel (.xlsx)</option>
                <option value="csv">CSV (.csv)</option>
              </select>
            </div>

            <div className="flex items-center pt-6">
              <input
                type="checkbox"
                id="include_charts"
                className="rounded border-gray-300 dark:border-zinc-700 text-indigo-600 focus:ring-indigo-500"
                checked={formData.include_charts}
                onChange={(e) => setFormData({ ...formData, include_charts: e.target.checked })}
              />
              <label htmlFor="include_charts" className="ml-2 text-sm text-gray-700 dark:text-zinc-300">
                Incluir gráficos
              </label>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-4">
            <Button variant="secondary" onClick={() => setIsModalOpen(false)}>
              Cancelar
            </Button>
            <Button onClick={handleCreateSchedule}>Criar Agendamento</Button>
          </div>
        </div>
      </Modal>

      {/* Generate Report Modal */}
      <Modal
        isOpen={isGenerateModalOpen}
        onClose={() => setIsGenerateModalOpen(false)}
        title="Gerar Relatório"
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">Tipo de Relatório</label>
            <select
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              value={generateData.report_type}
              onChange={(e) => setGenerateData({ ...generateData, report_type: e.target.value })}
            >
              <option value="full">Completo</option>
              <option value="messages">Mensagens</option>
              <option value="orders">Pedidos</option>
              <option value="conversations">Conversas</option>
              <option value="automation">Automação</option>
              <option value="payments">Pagamentos</option>
            </select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">Data Início</label>
              <input
                type="date"
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                value={generateData.period_start}
                onChange={(e) =>
                  setGenerateData({ ...generateData, period_start: e.target.value })
                }
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">Data Fim</label>
              <input
                type="date"
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                value={generateData.period_end}
                onChange={(e) => setGenerateData({ ...generateData, period_end: e.target.value })}
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">
              Destinatários (separados por vírgula)
            </label>
            <input
              type="text"
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              value={generateData.recipients}
              onChange={(e) => setGenerateData({ ...generateData, recipients: e.target.value })}
              placeholder="email1@exemplo.com, email2@exemplo.com"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">Formato</label>
            <select
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              value={generateData.export_format}
              onChange={(e) =>
                setGenerateData({ ...generateData, export_format: e.target.value })
              }
            >
              <option value="xlsx">Excel (.xlsx)</option>
              <option value="csv">CSV (.csv)</option>
            </select>
          </div>

          <div className="flex justify-end gap-3 pt-4">
            <Button variant="secondary" onClick={() => setIsGenerateModalOpen(false)}>
              Cancelar
            </Button>
            <Button onClick={handleGenerateReport}>
              <DocumentChartBarIcon className="h-5 w-5 mr-2" />
              Gerar Relatório
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
