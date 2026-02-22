import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  ArrowLeftIcon,
  PlusIcon,
  PencilIcon,
  TrashIcon,
  PlayIcon,
  ChatBubbleLeftRightIcon,
} from '@heroicons/react/24/outline';
import {
  autoMessageApi,
  companyProfileApi,
  eventTypeLabels,
  messageVariables,
} from '../../services/automation';
import { AutoMessage, CompanyProfile, AutoMessageEventType, CreateAutoMessage } from '../../types';
import { Loading as LoadingSpinner } from '../../components/common/Loading';
import { toast } from 'react-hot-toast';

const AutoMessagesPage: React.FC = () => {
  const { companyId } = useParams<{ companyId: string }>();
  const [company, setCompany] = useState<CompanyProfile | null>(null);
  const [messages, setMessages] = useState<AutoMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingMessage, setEditingMessage] = useState<AutoMessage | null>(null);
  const [testModal, setTestModal] = useState<AutoMessage | null>(null);
  const [testPhone, setTestPhone] = useState('');
  const [testResult, setTestResult] = useState<string | null>(null);

  const [formData, setFormData] = useState<CreateAutoMessage>({
    company_id: companyId || '',
    event_type: 'welcome',
    name: '',
    message_text: '',
    is_active: true,
    delay_seconds: 0,
    priority: 100,
    buttons: [],
  });

  useEffect(() => {
    if (companyId) {
      loadData();
    }
  }, [companyId]);

  const loadData = async () => {
    try {
      setLoading(true);
      const [companyData, messagesData] = await Promise.all([
        companyProfileApi.get(companyId!),
        autoMessageApi.list({ company_id: companyId }),
      ]);
      setCompany(companyData);
      setMessages(messagesData.results);
    } catch (error) {
      toast.error('Erro ao carregar dados');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (editingMessage) {
        await autoMessageApi.update(editingMessage.id, formData);
        toast.success('Mensagem atualizada!');
      } else {
        await autoMessageApi.create(formData);
        toast.success('Mensagem criada!');
      }
      setShowModal(false);
      setEditingMessage(null);
      resetForm();
      loadData();
    } catch (error) {
      toast.error('Erro ao salvar mensagem');
    }
  };

  const handleEdit = (message: AutoMessage) => {
    setEditingMessage(message);
    setFormData({
      company_id: companyId || '',
      event_type: message.event_type,
      name: message.name,
      message_text: message.message_text,
      media_url: message.media_url || undefined,
      media_type: message.media_type || undefined,
      buttons: message.buttons,
      is_active: message.is_active,
      delay_seconds: message.delay_seconds,
      priority: message.priority,
    });
    setShowModal(true);
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Tem certeza que deseja excluir esta mensagem?')) return;
    try {
      await autoMessageApi.delete(id);
      toast.success('Mensagem excluída!');
      loadData();
    } catch (error) {
      toast.error('Erro ao excluir mensagem');
    }
  };

  const handleToggleActive = async (message: AutoMessage) => {
    try {
      await autoMessageApi.update(message.id, { is_active: !message.is_active });
      toast.success(message.is_active ? 'Mensagem desativada' : 'Mensagem ativada');
      loadData();
    } catch (error) {
      toast.error('Erro ao atualizar mensagem');
    }
  };

  const handleTest = async () => {
    if (!testModal || !testPhone) return;
    try {
      const result = await autoMessageApi.test(testModal.id, {
        phone_number: testPhone,
        send: false,
      });
      setTestResult(result.rendered_message);
    } catch (error) {
      toast.error('Erro ao testar mensagem');
    }
  };

  const handleSendTest = async () => {
    if (!testModal || !testPhone) return;
    try {
      await autoMessageApi.test(testModal.id, {
        phone_number: testPhone,
        send: true,
      });
      toast.success('Mensagem de teste enviada!');
      setTestModal(null);
      setTestPhone('');
      setTestResult(null);
    } catch (error) {
      toast.error('Erro ao enviar mensagem de teste');
    }
  };

  const resetForm = () => {
    setFormData({
      company_id: companyId || '',
      event_type: 'welcome',
      name: '',
      message_text: '',
      is_active: true,
      delay_seconds: 0,
      priority: 100,
      buttons: [],
    });
  };

  const insertVariable = (variable: string) => {
    setFormData(prev => ({
      ...prev,
      message_text: prev.message_text + `{${variable}}`,
    }));
  };

  const addButton = () => {
    setFormData(prev => ({
      ...prev,
      buttons: [...(prev.buttons || []), { id: `btn_${Date.now()}`, title: '' }],
    }));
  };

  const updateButton = (index: number, field: 'id' | 'title', value: string) => {
    setFormData(prev => ({
      ...prev,
      buttons: prev.buttons?.map((btn, i) =>
        i === index ? { ...btn, [field]: value } : btn
      ),
    }));
  };

  const removeButton = (index: number) => {
    setFormData(prev => ({
      ...prev,
      buttons: prev.buttons?.filter((_, i) => i !== index),
    }));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  // Group messages by event type
  const groupedMessages = messages.reduce((acc, msg) => {
    if (!acc[msg.event_type]) {
      acc[msg.event_type] = [];
    }
    acc[msg.event_type].push(msg);
    return acc;
  }, {} as Record<string, AutoMessage[]>);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Link
            to={`/automation/companies/${companyId}`}
            className="p-2 text-gray-400 hover:text-gray-600 dark:text-zinc-400"
          >
            <ArrowLeftIcon className="h-5 w-5" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Mensagens Automáticas</h1>
            <p className="text-sm text-gray-500 dark:text-zinc-400">{company?.company_name}</p>
          </div>
        </div>
        <button
          onClick={() => {
            resetForm();
            setEditingMessage(null);
            setShowModal(true);
          }}
          className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-green-600 hover:bg-green-700"
        >
          <PlusIcon className="h-5 w-5 mr-2" />
          Nova Mensagem
        </button>
      </div>

      {/* Messages by Event Type */}
      {Object.keys(eventTypeLabels).map((eventType) => {
        const eventMessages = groupedMessages[eventType] || [];
        return (
          <div key={eventType} className="bg-white dark:bg-zinc-900 shadow rounded-lg overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200 dark:border-zinc-800 bg-gray-50 dark:bg-black">
              <h3 className="text-lg font-medium text-gray-900 dark:text-white">
                {eventTypeLabels[eventType as AutoMessageEventType]}
              </h3>
            </div>
            {eventMessages.length === 0 ? (
              <div className="px-6 py-8 text-center text-gray-500 dark:text-zinc-400">
                <ChatBubbleLeftRightIcon className="mx-auto h-8 w-8 text-gray-400" />
                <p className="mt-2">Nenhuma mensagem configurada</p>
                <button
                  onClick={() => {
                    resetForm();
                    setFormData(prev => ({ ...prev, event_type: eventType as AutoMessageEventType }));
                    setShowModal(true);
                  }}
                  className="mt-2 text-green-600 dark:text-green-400 hover:text-green-700 dark:text-green-300 text-sm font-medium"
                >
                  + Adicionar mensagem
                </button>
              </div>
            ) : (
              <ul className="divide-y divide-gray-200">
                {eventMessages.map((message) => (
                  <li key={message.id} className="px-6 py-4">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center space-x-3">
                          <h4 className="text-sm font-medium text-gray-900 dark:text-white truncate">
                            {message.name}
                          </h4>
                          <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                            message.is_active
                              ? 'bg-green-100 text-green-800'
                              : 'bg-gray-100 text-gray-800'
                          }`}>
                            {message.is_active ? 'Ativo' : 'Inativo'}
                          </span>
                          {message.delay_seconds > 0 && (
                            <span className="text-xs text-gray-500 dark:text-zinc-400">
                              Delay: {message.delay_seconds}s
                            </span>
                          )}
                        </div>
                        <p className="mt-1 text-sm text-gray-500 dark:text-zinc-400 line-clamp-2">
                          {message.message_text}
                        </p>
                        {message.buttons && message.buttons.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-1">
                            {message.buttons.map((btn, i) => (
                              <span
                                key={i}
                                className="inline-flex items-center px-2 py-1 rounded bg-blue-100 dark:bg-blue-900/40 text-blue-800 text-xs"
                              >
                                {btn.title}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className="flex items-center space-x-2 ml-4">
                        <button
                          onClick={() => setTestModal(message)}
                          className="p-2 text-gray-400 hover:text-blue-600 dark:text-blue-400"
                          title="Testar"
                        >
                          <PlayIcon className="h-5 w-5" />
                        </button>
                        <button
                          onClick={() => handleEdit(message)}
                          className="p-2 text-gray-400 hover:text-green-600 dark:text-green-400"
                          title="Editar"
                        >
                          <PencilIcon className="h-5 w-5" />
                        </button>
                        <button
                          onClick={() => handleToggleActive(message)}
                          className={`p-2 ${
                            message.is_active
                              ? 'text-green-600 hover:text-gray-400'
                              : 'text-gray-400 hover:text-green-600'
                          }`}
                          title={message.is_active ? 'Desativar' : 'Ativar'}
                        >
                          <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                          </svg>
                        </button>
                        <button
                          onClick={() => handleDelete(message.id)}
                          className="p-2 text-gray-400 hover:text-red-600 dark:text-red-400"
                          title="Excluir"
                        >
                          <TrashIcon className="h-5 w-5" />
                        </button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}

      {/* Create/Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex items-center justify-center min-h-screen px-4">
            <div className="fixed inset-0 bg-gray-50 dark:bg-black0 bg-opacity-75" onClick={() => setShowModal(false)} />
            <div className="relative bg-white dark:bg-zinc-900 rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
              <form onSubmit={handleSubmit}>
                <div className="px-6 py-4 border-b border-gray-200 dark:border-zinc-800">
                  <h3 className="text-lg font-medium text-gray-900 dark:text-white">
                    {editingMessage ? 'Editar Mensagem' : 'Nova Mensagem'}
                  </h3>
                </div>
                <div className="px-6 py-4 space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">
                        Tipo de Evento
                      </label>
                      <select
                        value={formData.event_type}
                        onChange={(e) => setFormData({ ...formData, event_type: e.target.value as AutoMessageEventType })}
                        className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-green-500 focus:ring-green-500"
                      >
                        {Object.entries(eventTypeLabels).map(([value, label]) => (
                          <option key={value} value={value}>{label}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">
                        Nome Interno
                      </label>
                      <input
                        type="text"
                        value={formData.name}
                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                        required
                        className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-green-500 focus:ring-green-500"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">
                      Texto da Mensagem
                    </label>
                    <textarea
                      rows={5}
                      value={formData.message_text}
                      onChange={(e) => setFormData({ ...formData, message_text: e.target.value })}
                      required
                      className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-green-500 focus:ring-green-500"
                    />
                    <div className="mt-2">
                      <p className="text-xs text-gray-500 dark:text-zinc-400 mb-1">Variáveis disponíveis:</p>
                      <div className="flex flex-wrap gap-1">
                        {messageVariables.map((v) => (
                          <button
                            key={v.key}
                            type="button"
                            onClick={() => insertVariable(v.key)}
                            className="inline-flex items-center px-2 py-1 rounded bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-zinc-300 text-xs hover:bg-gray-200"
                            title={v.description}
                          >
                            {`{${v.key}}`}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">
                        Delay (segundos)
                      </label>
                      <input
                        type="number"
                        min="0"
                        value={formData.delay_seconds}
                        onChange={(e) => setFormData({ ...formData, delay_seconds: parseInt(e.target.value) })}
                        className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-green-500 focus:ring-green-500"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">
                        Prioridade
                      </label>
                      <input
                        type="number"
                        min="1"
                        value={formData.priority}
                        onChange={(e) => setFormData({ ...formData, priority: parseInt(e.target.value) })}
                        className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-green-500 focus:ring-green-500"
                      />
                    </div>
                    <div className="flex items-end">
                      <label className="flex items-center">
                        <input
                          type="checkbox"
                          checked={formData.is_active}
                          onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                          className="h-4 w-4 text-green-600 dark:text-green-400 focus:ring-green-500 border-gray-300 dark:border-zinc-700 rounded"
                        />
                        <span className="ml-2 text-sm text-gray-700 dark:text-zinc-300">Ativo</span>
                      </label>
                    </div>
                  </div>

                  {/* Buttons */}
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">
                        Botões Interativos (máx. 3)
                      </label>
                      {(formData.buttons?.length || 0) < 3 && (
                        <button
                          type="button"
                          onClick={addButton}
                          className="text-sm text-green-600 dark:text-green-400 hover:text-green-700 dark:text-green-300"
                        >
                          + Adicionar botão
                        </button>
                      )}
                    </div>
                    {formData.buttons?.map((btn, index) => (
                      <div key={index} className="flex items-center space-x-2 mb-2">
                        <input
                          type="text"
                          placeholder="ID"
                          value={btn.id}
                          onChange={(e) => updateButton(index, 'id', e.target.value)}
                          className="w-32 rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-green-500 focus:ring-green-500 text-sm"
                        />
                        <input
                          type="text"
                          placeholder="Título do botão"
                          value={btn.title}
                          onChange={(e) => updateButton(index, 'title', e.target.value)}
                          className="flex-1 rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-green-500 focus:ring-green-500 text-sm"
                        />
                        <button
                          type="button"
                          onClick={() => removeButton(index)}
                          className="p-1 text-red-500 hover:text-red-700 dark:text-red-300"
                        >
                          <TrashIcon className="h-4 w-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="px-6 py-4 border-t border-gray-200 dark:border-zinc-800 flex justify-end space-x-3">
                  <button
                    type="button"
                    onClick={() => {
                      setShowModal(false);
                      setEditingMessage(null);
                      resetForm();
                    }}
                    className="px-4 py-2 border border-gray-300 dark:border-zinc-700 rounded-md shadow-sm text-sm font-medium text-gray-700 dark:text-zinc-300 bg-white dark:bg-zinc-900 hover:bg-gray-50 dark:hover:bg-zinc-700 dark:bg-black"
                  >
                    Cancelar
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-green-600 hover:bg-green-700"
                  >
                    {editingMessage ? 'Atualizar' : 'Criar'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Test Modal */}
      {testModal && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex items-center justify-center min-h-screen px-4">
            <div className="fixed inset-0 bg-gray-50 dark:bg-black0 bg-opacity-75" onClick={() => {
              setTestModal(null);
              setTestPhone('');
              setTestResult(null);
            }} />
            <div className="relative bg-white dark:bg-zinc-900 rounded-lg shadow-xl max-w-lg w-full">
              <div className="px-6 py-4 border-b border-gray-200 dark:border-zinc-800">
                <h3 className="text-lg font-medium text-gray-900 dark:text-white">
                  Testar Mensagem: {testModal.name}
                </h3>
              </div>
              <div className="px-6 py-4 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300">
                    Número de Telefone
                  </label>
                  <input
                    type="text"
                    value={testPhone}
                    onChange={(e) => setTestPhone(e.target.value)}
                    placeholder="5511999999999"
                    className="mt-1 block w-full rounded-md border-gray-300 dark:border-zinc-700 shadow-sm focus:border-green-500 focus:ring-green-500"
                  />
                </div>
                <button
                  type="button"
                  onClick={handleTest}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-zinc-700 rounded-md shadow-sm text-sm font-medium text-gray-700 dark:text-zinc-300 bg-white dark:bg-zinc-900 hover:bg-gray-50 dark:hover:bg-zinc-700 dark:bg-black"
                >
                  Visualizar Preview
                </button>
                {testResult && (
                  <div className="bg-gray-50 dark:bg-black rounded-lg p-4">
                    <p className="text-sm font-medium text-gray-700 dark:text-zinc-300 mb-2">Preview:</p>
                    <div className="bg-green-100 dark:bg-green-900/40 rounded-lg p-3 text-sm whitespace-pre-wrap">
                      {testResult}
                    </div>
                    {testModal.buttons && testModal.buttons.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {testModal.buttons.map((btn, i) => (
                          <span
                            key={i}
                            className="inline-flex items-center px-3 py-1 rounded-full bg-white dark:bg-zinc-900 border border-green-500 text-green-700 dark:text-green-300 text-sm"
                          >
                            {btn.title}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
              <div className="px-6 py-4 border-t border-gray-200 dark:border-zinc-800 flex justify-end space-x-3">
                <button
                  type="button"
                  onClick={() => {
                    setTestModal(null);
                    setTestPhone('');
                    setTestResult(null);
                  }}
                  className="px-4 py-2 border border-gray-300 dark:border-zinc-700 rounded-md shadow-sm text-sm font-medium text-gray-700 dark:text-zinc-300 bg-white dark:bg-zinc-900 hover:bg-gray-50 dark:hover:bg-zinc-700 dark:bg-black"
                >
                  Fechar
                </button>
                {testResult && (
                  <button
                    type="button"
                    onClick={handleSendTest}
                    className="px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-green-600 hover:bg-green-700"
                  >
                    Enviar Teste
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AutoMessagesPage;
