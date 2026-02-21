import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  ArrowLeftIcon,
  BuildingOfficeIcon,
  ClipboardDocumentIcon,
  KeyIcon,
  TrashIcon,
} from '@heroicons/react/24/outline';
import { companyProfileApi, businessTypeLabels } from '../../services/automation';
import { CompanyProfile, UpdateCompanyProfile, BusinessHours } from '../../types';
import { Loading as LoadingSpinner } from '../../components/common/Loading';
import { toast } from 'react-hot-toast';

const daysOfWeek = [
  { key: 'monday', label: 'Segunda-feira' },
  { key: 'tuesday', label: 'Terça-feira' },
  { key: 'wednesday', label: 'Quarta-feira' },
  { key: 'thursday', label: 'Quinta-feira' },
  { key: 'friday', label: 'Sexta-feira' },
  { key: 'saturday', label: 'Sábado' },
  { key: 'sunday', label: 'Domingo' },
];

const CompanyProfileDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [profile, setProfile] = useState<CompanyProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState<UpdateCompanyProfile>({});
  const [businessHours, setBusinessHours] = useState<BusinessHours>({});

  useEffect(() => {
    if (id) {
      loadProfile();
    }
  }, [id]);

  const loadProfile = async () => {
    try {
      setLoading(true);
      const data = await companyProfileApi.get(id!);
      setProfile(data);
      setFormData({
        company_name: data.company_name,
        business_type: data.business_type,
        description: data.description,
        website_url: data.website_url,
        menu_url: data.menu_url,
        order_url: data.order_url,
        auto_reply_enabled: data.auto_reply_enabled,
        welcome_message_enabled: data.welcome_message_enabled,
        menu_auto_send: data.menu_auto_send,
        abandoned_cart_notification: data.abandoned_cart_notification,
        abandoned_cart_delay_minutes: data.abandoned_cart_delay_minutes,
        pix_notification_enabled: data.pix_notification_enabled,
        payment_confirmation_enabled: data.payment_confirmation_enabled,
        order_status_notification_enabled: data.order_status_notification_enabled,
        delivery_notification_enabled: data.delivery_notification_enabled,
        use_ai_agent: data.use_ai_agent,
        default_agent: data.default_agent,
      });
      setBusinessHours(data.business_hours || {});
    } catch (error) {
      toast.error('Erro ao carregar perfil');
      navigate('/automation/companies');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSaving(true);
      await companyProfileApi.update(id!, {
        ...formData,
        business_hours: businessHours,
      });
      toast.success('Perfil atualizado com sucesso!');
      loadProfile();
    } catch (error) {
      toast.error('Erro ao atualizar perfil');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm('Tem certeza que deseja excluir este perfil? Esta ação não pode ser desfeita.')) {
      return;
    }
    try {
      await companyProfileApi.delete(id!);
      toast.success('Perfil excluído com sucesso');
      navigate('/automation/companies');
    } catch (error) {
      toast.error('Erro ao excluir perfil');
    }
  };

  const handleCopyApiKey = () => {
    if (profile?.external_api_key) {
      navigator.clipboard.writeText(profile.external_api_key);
      toast.success('API key copiada!');
    }
  };

  const handleRegenerateApiKey = async () => {
    if (!confirm('Tem certeza? A chave atual será invalidada.')) return;
    try {
      const result = await companyProfileApi.regenerateApiKey(id!);
      toast.success('Nova API key gerada!');
      navigator.clipboard.writeText(result.api_key);
      loadProfile();
    } catch (error) {
      toast.error('Erro ao gerar nova API key');
    }
  };

  const handleBusinessHoursChange = (
    day: string,
    field: 'open' | 'start' | 'end',
    value: boolean | string
  ) => {
    setBusinessHours(prev => ({
      ...prev,
      [day]: {
        ...prev[day as keyof BusinessHours],
        [field]: value,
      },
    }));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (!profile) {
    return null;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Link
            to="/automation/companies"
            className="p-2 text-gray-400 hover:text-gray-600 dark:text-zinc-400"
          >
            <ArrowLeftIcon className="h-5 w-5" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{profile.company_name}</h1>
            <p className="text-sm text-gray-500 dark:text-zinc-400">{profile.account_phone}</p>
          </div>
        </div>
        <div className="flex space-x-2">
          <Link
            to={`/automation/companies/${id}/messages`}
            className="inline-flex items-center px-4 py-2 border border-gray-300 dark:border-zinc-700 rounded-md shadow-sm text-sm font-medium text-gray-700 dark:text-zinc-300 bg-white dark:bg-zinc-900 hover:bg-gray-50 dark:hover:bg-zinc-700 dark:bg-black"
          >
            Mensagens Automáticas
          </Link>
          <button
            onClick={handleDelete}
            className="inline-flex items-center px-4 py-2 border border-red-300 rounded-md shadow-sm text-sm font-medium text-red-700 dark:text-red-300 bg-white dark:bg-zinc-900 hover:bg-red-50"
          >
            <TrashIcon className="h-4 w-4 mr-2" />
            Excluir
          </button>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Basic Info */}
        <div className="bg-white dark:bg-zinc-900 shadow rounded-lg p-6">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Informações Básicas</h2>
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">
                Nome da Empresa
              </label>
              <input
                type="text"
                value={formData.company_name || ''}
                onChange={(e) => setFormData({ ...formData, company_name: e.target.value })}
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-green-500 focus:ring-green-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">
                Tipo de Negócio
              </label>
              <select
                value={formData.business_type || ''}
                onChange={(e) => setFormData({ ...formData, business_type: e.target.value as any })}
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-green-500 focus:ring-green-500"
              >
                {Object.entries(businessTypeLabels).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>
            <div className="sm:col-span-2">
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">
                Descrição
              </label>
              <textarea
                rows={3}
                value={formData.description || ''}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-green-500 focus:ring-green-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">
                URL do Site
              </label>
              <input
                type="url"
                value={formData.website_url || ''}
                onChange={(e) => setFormData({ ...formData, website_url: e.target.value })}
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-green-500 focus:ring-green-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">
                URL do Cardápio/Catálogo
              </label>
              <input
                type="url"
                value={formData.menu_url || ''}
                onChange={(e) => setFormData({ ...formData, menu_url: e.target.value })}
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-green-500 focus:ring-green-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">
                URL para Pedidos
              </label>
              <input
                type="url"
                value={formData.order_url || ''}
                onChange={(e) => setFormData({ ...formData, order_url: e.target.value })}
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-green-500 focus:ring-green-500"
              />
            </div>
          </div>
        </div>

        {/* Automation Settings */}
        <div className="bg-white dark:bg-zinc-900 shadow rounded-lg p-6">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Configurações de Automação</h2>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-zinc-300">Respostas Automáticas</label>
                <p className="text-sm text-gray-500 dark:text-zinc-400">Habilitar respostas automáticas para mensagens</p>
              </div>
              <input
                type="checkbox"
                checked={formData.auto_reply_enabled || false}
                onChange={(e) => setFormData({ ...formData, auto_reply_enabled: e.target.checked })}
                className="h-4 w-4 text-green-600 dark:text-green-400 focus:ring-green-500 border-gray-300 dark:border-zinc-700 rounded"
              />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-zinc-300">Mensagem de Boas-vindas</label>
                <p className="text-sm text-gray-500 dark:text-zinc-400">Enviar boas-vindas na primeira mensagem</p>
              </div>
              <input
                type="checkbox"
                checked={formData.welcome_message_enabled || false}
                onChange={(e) => setFormData({ ...formData, welcome_message_enabled: e.target.checked })}
                className="h-4 w-4 text-green-600 dark:text-green-400 focus:ring-green-500 border-gray-300 dark:border-zinc-700 rounded"
              />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-zinc-300">Enviar Cardápio Automaticamente</label>
                <p className="text-sm text-gray-500 dark:text-zinc-400">Enviar cardápio junto com boas-vindas</p>
              </div>
              <input
                type="checkbox"
                checked={formData.menu_auto_send || false}
                onChange={(e) => setFormData({ ...formData, menu_auto_send: e.target.checked })}
                className="h-4 w-4 text-green-600 dark:text-green-400 focus:ring-green-500 border-gray-300 dark:border-zinc-700 rounded"
              />
            </div>
          </div>
        </div>

        {/* Notification Settings */}
        <div className="bg-white dark:bg-zinc-900 shadow rounded-lg p-6">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Notificações</h2>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-zinc-300">Carrinho Abandonado</label>
                <p className="text-sm text-gray-500 dark:text-zinc-400">Notificar quando cliente abandona carrinho</p>
              </div>
              <input
                type="checkbox"
                checked={formData.abandoned_cart_notification || false}
                onChange={(e) => setFormData({ ...formData, abandoned_cart_notification: e.target.checked })}
                className="h-4 w-4 text-green-600 dark:text-green-400 focus:ring-green-500 border-gray-300 dark:border-zinc-700 rounded"
              />
            </div>
            {formData.abandoned_cart_notification && (
              <div className="ml-4">
                <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">
                  Tempo de espera (minutos)
                </label>
                <input
                  type="number"
                  min="1"
                  value={formData.abandoned_cart_delay_minutes || 30}
                  onChange={(e) => setFormData({ ...formData, abandoned_cart_delay_minutes: parseInt(e.target.value) })}
                  className="mt-1 block w-32 rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-green-500 focus:ring-green-500"
                />
              </div>
            )}
            <div className="flex items-center justify-between">
              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-zinc-300">PIX Gerado</label>
                <p className="text-sm text-gray-500 dark:text-zinc-400">Notificar quando PIX é gerado</p>
              </div>
              <input
                type="checkbox"
                checked={formData.pix_notification_enabled || false}
                onChange={(e) => setFormData({ ...formData, pix_notification_enabled: e.target.checked })}
                className="h-4 w-4 text-green-600 dark:text-green-400 focus:ring-green-500 border-gray-300 dark:border-zinc-700 rounded"
              />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-zinc-300">Confirmação de Pagamento</label>
                <p className="text-sm text-gray-500 dark:text-zinc-400">Notificar quando pagamento é confirmado</p>
              </div>
              <input
                type="checkbox"
                checked={formData.payment_confirmation_enabled || false}
                onChange={(e) => setFormData({ ...formData, payment_confirmation_enabled: e.target.checked })}
                className="h-4 w-4 text-green-600 dark:text-green-400 focus:ring-green-500 border-gray-300 dark:border-zinc-700 rounded"
              />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-zinc-300">Status do Pedido</label>
                <p className="text-sm text-gray-500 dark:text-zinc-400">Notificar mudanças no status do pedido</p>
              </div>
              <input
                type="checkbox"
                checked={formData.order_status_notification_enabled || false}
                onChange={(e) => setFormData({ ...formData, order_status_notification_enabled: e.target.checked })}
                className="h-4 w-4 text-green-600 dark:text-green-400 focus:ring-green-500 border-gray-300 dark:border-zinc-700 rounded"
              />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-zinc-300">Entrega</label>
                <p className="text-sm text-gray-500 dark:text-zinc-400">Notificar sobre entrega</p>
              </div>
              <input
                type="checkbox"
                checked={formData.delivery_notification_enabled || false}
                onChange={(e) => setFormData({ ...formData, delivery_notification_enabled: e.target.checked })}
                className="h-4 w-4 text-green-600 dark:text-green-400 focus:ring-green-500 border-gray-300 dark:border-zinc-700 rounded"
              />
            </div>
          </div>
        </div>

        {/* Business Hours */}
        <div className="bg-white dark:bg-zinc-900 shadow rounded-lg p-6">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Horário de Funcionamento</h2>
          <div className="space-y-3">
            {daysOfWeek.map(({ key, label }) => (
              <div key={key} className="flex items-center space-x-4">
                <div className="w-32">
                  <label className="text-sm font-medium text-gray-700 dark:text-zinc-300">{label}</label>
                </div>
                <input
                  type="checkbox"
                  checked={businessHours[key as keyof BusinessHours]?.open || false}
                  onChange={(e) => handleBusinessHoursChange(key, 'open', e.target.checked)}
                  className="h-4 w-4 text-green-600 dark:text-green-400 focus:ring-green-500 border-gray-300 dark:border-zinc-700 rounded"
                />
                {businessHours[key as keyof BusinessHours]?.open && (
                  <>
                    <input
                      type="time"
                      value={businessHours[key as keyof BusinessHours]?.start || '08:00'}
                      onChange={(e) => handleBusinessHoursChange(key, 'start', e.target.value)}
                      className="rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-green-500 focus:ring-green-500"
                    />
                    <span className="text-gray-500 dark:text-zinc-400">até</span>
                    <input
                      type="time"
                      value={businessHours[key as keyof BusinessHours]?.end || '18:00'}
                      onChange={(e) => handleBusinessHoursChange(key, 'end', e.target.value)}
                      className="rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-green-500 focus:ring-green-500"
                    />
                  </>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* API Integration */}
        <div className="bg-white dark:bg-zinc-900 shadow rounded-lg p-6">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Integração API</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">API Key</label>
              <div className="mt-1 flex rounded-md shadow-sm">
                <input
                  type="text"
                  readOnly
                  value={profile.external_api_key || 'Não gerada'}
                  className="flex-1 block w-full rounded-l-md border-gray-300 dark:border-zinc-700 bg-gray-50 dark:bg-black"
                />
                <button
                  type="button"
                  onClick={handleCopyApiKey}
                  className="inline-flex items-center px-3 border border-l-0 border-gray-300 dark:border-zinc-700 bg-gray-50 dark:bg-black text-gray-500 dark:text-zinc-400 hover:text-gray-700 dark:hover:text-zinc-300 dark:hover:text-zinc-300"
                >
                  <ClipboardDocumentIcon className="h-5 w-5" />
                </button>
                <button
                  type="button"
                  onClick={handleRegenerateApiKey}
                  className="inline-flex items-center px-3 rounded-r-md border border-l-0 border-gray-300 dark:border-zinc-700 bg-gray-50 dark:bg-black text-gray-500 dark:text-zinc-400 hover:text-gray-700 dark:hover:text-zinc-300 dark:hover:text-zinc-300"
                >
                  <KeyIcon className="h-5 w-5" />
                </button>
              </div>
              <p className="mt-1 text-sm text-gray-500 dark:text-zinc-400">
                Use esta chave no header X-API-Key para autenticar webhooks
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">Webhook Secret</label>
              <div className="mt-1 flex rounded-md shadow-sm">
                <input
                  type="text"
                  readOnly
                  value={profile.webhook_secret ? '••••••••••••••••' : 'Não gerado'}
                  className="flex-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 bg-gray-50 dark:bg-black"
                />
              </div>
              <p className="mt-1 text-sm text-gray-500 dark:text-zinc-400">
                Use para validar assinaturas de webhook (opcional)
              </p>
            </div>
          </div>
        </div>

        {/* AI Agent Integration */}
        <div className="bg-white dark:bg-zinc-900 shadow rounded-lg p-6">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Integração Agente IA</h2>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-zinc-300">Usar Agente IA</label>
                <p className="text-sm text-gray-500 dark:text-zinc-400">Usar Agente IA (Langchain) para respostas avançadas</p>
              </div>
              <input
                type="checkbox"
                checked={formData.use_ai_agent || false}
                onChange={(e) => setFormData({ ...formData, use_ai_agent: e.target.checked })}
                className="h-4 w-4 text-green-600 dark:text-green-400 focus:ring-green-500 border-gray-300 dark:border-zinc-700 rounded"
              />
            </div>
            {formData.use_ai_agent && (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">
                  ID do Agente
                </label>
                <input
                  type="text"
                  value={formData.default_agent || ''}
                  onChange={(e) => setFormData({ ...formData, default_agent: e.target.value || null })}
                  placeholder="UUID do Agente IA"
                  className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-green-500 focus:ring-green-500"
                />
                <p className="mt-1 text-sm text-gray-500 dark:text-zinc-400">
                  <Link to="/agents" className="text-green-600 hover:text-green-700">Gerenciar Agentes IA →</Link>
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Submit */}
        <div className="flex justify-end space-x-3">
          <Link
            to="/automation/companies"
            className="px-4 py-2 border border-gray-300 dark:border-zinc-700 rounded-md shadow-sm text-sm font-medium text-gray-700 dark:text-zinc-300 bg-white dark:bg-zinc-900 hover:bg-gray-50 dark:hover:bg-zinc-700 dark:bg-black"
          >
            Cancelar
          </Link>
          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-green-600 hover:bg-green-700 disabled:opacity-50"
          >
            {saving ? <LoadingSpinner size="sm" /> : 'Salvar'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default CompanyProfileDetailPage;
