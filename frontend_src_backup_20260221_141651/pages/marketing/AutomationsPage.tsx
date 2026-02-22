/**
 * Email Automations Page
 * 
 * Configure automated emails for events like:
 * - Order confirmed
 * - Payment confirmed
 * - Order shipped
 * - Order delivered
 * - Cart abandoned
 * - etc.
 */
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BoltIcon,
  PlusIcon,
  PlayIcon,
  PauseIcon,
  PencilIcon,
  TrashIcon,
  EnvelopeIcon,
  ClockIcon,
  CheckCircleIcon,
  BeakerIcon,
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
import { Card, Button, Modal, Loading } from '../../components/common';
import { useStore } from '../../hooks';
import { 
  automationsApi, 
  EmailAutomation, 
  TriggerType 
} from '../../services/marketingService';
import logger from '../../services/logger';

// =============================================================================
// TRIGGER TYPE ICONS & COLORS
// =============================================================================

const TRIGGER_CONFIG: Record<string, { icon: string; color: string; bgColor: string }> = {
  new_user: { icon: '👤', color: 'text-blue-600', bgColor: 'bg-blue-100' },
  welcome: { icon: '👋', color: 'text-green-600', bgColor: 'bg-green-100' },
  order_confirmed: { icon: '✅', color: 'text-emerald-600', bgColor: 'bg-emerald-100' },
  order_preparing: { icon: '👨‍🍳', color: 'text-orange-600', bgColor: 'bg-orange-100' },
  order_shipped: { icon: '🚚', color: 'text-blue-600', bgColor: 'bg-blue-100' },
  order_delivered: { icon: '📦', color: 'text-green-600', bgColor: 'bg-green-100' },
  order_cancelled: { icon: '❌', color: 'text-red-600', bgColor: 'bg-red-100' },
  payment_confirmed: { icon: '💳', color: 'text-green-600', bgColor: 'bg-green-100' },
  payment_failed: { icon: '⚠️', color: 'text-red-600', bgColor: 'bg-red-100' },
  cart_abandoned: { icon: '🛒', color: 'text-yellow-600', bgColor: 'bg-yellow-100' },
  coupon_sent: { icon: '🎟️', color: 'text-purple-600', bgColor: 'bg-purple-100' },
  birthday: { icon: '🎂', color: 'text-pink-600', bgColor: 'bg-pink-100' },
  review_request: { icon: '⭐', color: 'text-yellow-600', bgColor: 'bg-yellow-100' },
};

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export default function AutomationsPage() {
  const navigate = useNavigate();
  const { storeId } = useStore();

  // State
  const [automations, setAutomations] = useState<EmailAutomation[]>([]);
  const [triggerTypes, setTriggerTypes] = useState<TriggerType[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showTestModal, setShowTestModal] = useState(false);
  const [selectedAutomation, setSelectedAutomation] = useState<EmailAutomation | null>(null);
  const [testEmail, setTestEmail] = useState('');

  // Form state
  const [formData, setFormData] = useState({
    name: '',
    trigger_type: '',
    subject: '',
    html_content: '',
    delay_minutes: 0,
    is_active: true,
  });

  // =============================================================================
  // DATA LOADING
  // =============================================================================

  useEffect(() => {
    const loadData = async () => {
      if (!storeId) {
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        const [automationsData, typesData] = await Promise.all([
          automationsApi.list(storeId),
          automationsApi.getTriggerTypes(),
        ]);
        setAutomations(automationsData);
        setTriggerTypes(typesData);
      } catch (error) {
        logger.error('Failed to load automations', error);
        toast.error('Erro ao carregar automações');
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [storeId]);

  // =============================================================================
  // HANDLERS
  // =============================================================================

  const handleToggle = async (automation: EmailAutomation) => {
    try {
      const updated = await automationsApi.toggle(automation.id);
      setAutomations(prev => 
        prev.map(a => a.id === automation.id ? updated : a)
      );
      toast.success(updated.is_active ? 'Automação ativada' : 'Automação pausada');
    } catch (error) {
      logger.error('Failed to toggle automation', error);
      toast.error('Erro ao alterar automação');
    }
  };

  const handleDelete = async (automation: EmailAutomation) => {
    if (!confirm(`Excluir automação "${automation.name}"?`)) return;

    try {
      await automationsApi.delete(automation.id);
      setAutomations(prev => prev.filter(a => a.id !== automation.id));
      toast.success('Automação excluída');
    } catch (error) {
      logger.error('Failed to delete automation', error);
      toast.error('Erro ao excluir automação');
    }
  };

  const handleCreate = async () => {
    if (!storeId || !formData.name || !formData.trigger_type || !formData.subject) {
      toast.error('Preencha todos os campos obrigatórios');
      return;
    }

    try {
      const newAutomation = await automationsApi.create({
        store: storeId,
        ...formData,
      });
      setAutomations(prev => [...prev, newAutomation]);
      setShowCreateModal(false);
      resetForm();
      toast.success('Automação criada com sucesso!');
    } catch (error) {
      logger.error('Failed to create automation', error);
      toast.error('Erro ao criar automação');
    }
  };

  const handleTest = async () => {
    if (!selectedAutomation || !testEmail) {
      toast.error('Informe um email para teste');
      return;
    }

    try {
      const result = await automationsApi.test(selectedAutomation.id, testEmail);
      if (result.success) {
        toast.success('Email de teste enviado!');
        setShowTestModal(false);
        setTestEmail('');
      } else {
        toast.error(result.error || 'Erro ao enviar teste');
      }
    } catch (error) {
      logger.error('Failed to send test', error);
      toast.error('Erro ao enviar email de teste');
    }
  };

  const resetForm = () => {
    setFormData({
      name: '',
      trigger_type: '',
      subject: '',
      html_content: '',
      delay_minutes: 0,
      is_active: true,
    });
  };

  const openTestModal = (automation: EmailAutomation) => {
    setSelectedAutomation(automation);
    setShowTestModal(true);
  };

  // =============================================================================
  // RENDER
  // =============================================================================

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loading size="lg" />
      </div>
    );
  }

  if (!storeId) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500 dark:text-zinc-400">Selecione uma loja para gerenciar automações</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Automações de Email</h1>
          <p className="text-gray-500 dark:text-zinc-400 mt-1">
            Configure emails automáticos para eventos do sistema
          </p>
        </div>
        <Button onClick={() => setShowCreateModal(true)}>
          <PlusIcon className="w-5 h-5 mr-2" />
          Nova Automação
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary-100 rounded-lg">
              <BoltIcon className="w-6 h-6 text-primary-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{automations.length}</p>
              <p className="text-sm text-gray-500 dark:text-zinc-400">Total</p>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-100 dark:bg-green-900/40 rounded-lg">
              <PlayIcon className="w-6 h-6 text-green-600 dark:text-green-400" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {automations.filter(a => a.is_active).length}
              </p>
              <p className="text-sm text-gray-500 dark:text-zinc-400">Ativas</p>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 dark:bg-blue-900/40 rounded-lg">
              <EnvelopeIcon className="w-6 h-6 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {automations.reduce((sum, a) => sum + a.total_sent, 0)}
              </p>
              <p className="text-sm text-gray-500 dark:text-zinc-400">Emails Enviados</p>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-100 dark:bg-purple-900/40 rounded-lg">
              <CheckCircleIcon className="w-6 h-6 text-purple-600 dark:text-purple-400" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {automations.reduce((sum, a) => sum + a.total_opened, 0)}
              </p>
              <p className="text-sm text-gray-500 dark:text-zinc-400">Abertos</p>
            </div>
          </div>
        </Card>
      </div>

      {/* Automations List */}
      {automations.length === 0 ? (
        <Card className="p-12 text-center">
          <BoltIcon className="w-12 h-12 text-gray-400 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
            Nenhuma automação configurada
          </h3>
          <p className="text-gray-500 dark:text-zinc-400 mb-4">
            Crie automações para enviar emails automaticamente quando eventos ocorrerem
          </p>
          <Button onClick={() => setShowCreateModal(true)}>
            <PlusIcon className="w-5 h-5 mr-2" />
            Criar Primeira Automação
          </Button>
        </Card>
      ) : (
        <div className="grid gap-4">
          {automations.map(automation => {
            const config = TRIGGER_CONFIG[automation.trigger_type] || {
              icon: '📧',
              color: 'text-gray-600',
              bgColor: 'bg-gray-100',
            };

            return (
              <Card key={automation.id} className="p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className={`p-3 rounded-lg ${config.bgColor}`}>
                      <span className="text-2xl">{config.icon}</span>
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-medium text-gray-900 dark:text-white">{automation.name}</h3>
                        {automation.is_active ? (
                          <span className="px-2 py-0.5 text-xs bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300 rounded-full">
                            Ativa
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-zinc-400 rounded-full">
                            Pausada
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-gray-500 dark:text-zinc-400">
                        {automation.trigger_type_display}
                        {automation.delay_minutes > 0 && (
                          <span className="ml-2">
                            <ClockIcon className="w-4 h-4 inline mr-1" />
                            {automation.delay_minutes} min de delay
                          </span>
                        )}
                      </p>
                      <p className="text-xs text-gray-400 mt-1">
                        Assunto: {automation.subject}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-4">
                    <div className="text-right text-sm">
                      <p className="text-gray-900 dark:text-white font-medium">{automation.total_sent}</p>
                      <p className="text-gray-500 dark:text-zinc-400">enviados</p>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => openTestModal(automation)}
                        className="p-2 text-gray-400 hover:text-blue-600 dark:text-blue-400 hover:bg-blue-50 rounded-lg"
                        title="Enviar teste"
                      >
                        <BeakerIcon className="w-5 h-5" />
                      </button>
                      <button
                        onClick={() => handleToggle(automation)}
                        className={`p-2 rounded-lg ${
                          automation.is_active
                            ? 'text-yellow-600 hover:bg-yellow-50'
                            : 'text-green-600 hover:bg-green-50'
                        }`}
                        title={automation.is_active ? 'Pausar' : 'Ativar'}
                      >
                        {automation.is_active ? (
                          <PauseIcon className="w-5 h-5" />
                        ) : (
                          <PlayIcon className="w-5 h-5" />
                        )}
                      </button>
                      <button
                        onClick={() => handleDelete(automation)}
                        className="p-2 text-gray-400 hover:text-red-600 dark:text-red-400 hover:bg-red-50 rounded-lg"
                        title="Excluir"
                      >
                        <TrashIcon className="w-5 h-5" />
                      </button>
                    </div>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Create Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => {
          setShowCreateModal(false);
          resetForm();
        }}
        title="Nova Automação de Email"
        size="lg"
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
              Nome da Automação *
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={e => setFormData(prev => ({ ...prev, name: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
              placeholder="Ex: Email de confirmação de pedido"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
              Gatilho (Quando enviar) *
            </label>
            <select
              value={formData.trigger_type}
              onChange={e => setFormData(prev => ({ ...prev, trigger_type: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option value="">Selecione um gatilho...</option>
              {triggerTypes.map(type => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
              Assunto do Email *
            </label>
            <input
              type="text"
              value={formData.subject}
              onChange={e => setFormData(prev => ({ ...prev, subject: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
              placeholder="Ex: Seu pedido #{{order_number}} foi confirmado!"
            />
          </div>

          {/* Variables Info */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <h4 className="text-sm font-medium text-blue-900 mb-2">📝 Variáveis Disponíveis</h4>
            <p className="text-xs text-blue-700 dark:text-blue-300 mb-2">
              Use estas variáveis no assunto e conteúdo - serão preenchidas automaticamente:
            </p>
            <div className="flex flex-wrap gap-1">
              <code className="text-xs bg-blue-100 dark:bg-blue-900/40 text-blue-800 px-1.5 py-0.5 rounded">{'{{customer_name}}'}</code>
              <code className="text-xs bg-blue-100 dark:bg-blue-900/40 text-blue-800 px-1.5 py-0.5 rounded">{'{{first_name}}'}</code>
              <code className="text-xs bg-blue-100 dark:bg-blue-900/40 text-blue-800 px-1.5 py-0.5 rounded">{'{{email}}'}</code>
              <code className="text-xs bg-blue-100 dark:bg-blue-900/40 text-blue-800 px-1.5 py-0.5 rounded">{'{{store_name}}'}</code>
              <code className="text-xs bg-blue-100 dark:bg-blue-900/40 text-blue-800 px-1.5 py-0.5 rounded">{'{{order_number}}'}</code>
              <code className="text-xs bg-blue-100 dark:bg-blue-900/40 text-blue-800 px-1.5 py-0.5 rounded">{'{{order_total}}'}</code>
              <code className="text-xs bg-blue-100 dark:bg-blue-900/40 text-blue-800 px-1.5 py-0.5 rounded">{'{{tracking_code}}'}</code>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
              Conteúdo HTML *
            </label>
            <textarea
              value={formData.html_content}
              onChange={e => setFormData(prev => ({ ...prev, html_content: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500 font-mono text-sm"
              rows={8}
              placeholder="<html>...</html>"
            />
            <p className="text-xs text-gray-500 dark:text-zinc-400 mt-1">
              💡 Dica: Copie um template da página de Marketing e personalize aqui
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
              Delay (minutos)
            </label>
            <input
              type="number"
              min="0"
              value={formData.delay_minutes}
              onChange={e => setFormData(prev => ({ ...prev, delay_minutes: parseInt(e.target.value) || 0 }))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
            />
            <p className="text-xs text-gray-500 dark:text-zinc-400 mt-1">
              0 = envio imediato. Use delay para emails como "solicitar avaliação" (ex: 1440 = 24h)
            </p>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="is_active"
              checked={formData.is_active}
              onChange={e => setFormData(prev => ({ ...prev, is_active: e.target.checked }))}
              className="rounded border-gray-300 dark:border-zinc-700 text-primary-600 focus:ring-primary-500"
            />
            <label htmlFor="is_active" className="text-sm text-gray-700 dark:text-zinc-300">
              Ativar automação imediatamente
            </label>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t">
            <Button
              variant="secondary"
              onClick={() => {
                setShowCreateModal(false);
                resetForm();
              }}
            >
              Cancelar
            </Button>
            <Button onClick={handleCreate}>
              Criar Automação
            </Button>
          </div>
        </div>
      </Modal>

      {/* Test Modal */}
      <Modal
        isOpen={showTestModal}
        onClose={() => {
          setShowTestModal(false);
          setTestEmail('');
          setSelectedAutomation(null);
        }}
        title="Enviar Email de Teste"
      >
        <div className="space-y-4">
          <p className="text-gray-600 dark:text-zinc-400">
            Envie um email de teste para verificar como a automação 
            <strong> "{selectedAutomation?.name}"</strong> será exibida.
          </p>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
              Email para teste
            </label>
            <input
              type="email"
              value={testEmail}
              onChange={e => setTestEmail(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
              placeholder="seu@email.com"
            />
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t">
            <Button
              variant="secondary"
              onClick={() => {
                setShowTestModal(false);
                setTestEmail('');
              }}
            >
              Cancelar
            </Button>
            <Button onClick={handleTest}>
              <BeakerIcon className="w-5 h-5 mr-2" />
              Enviar Teste
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
