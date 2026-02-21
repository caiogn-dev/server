import React, { useState, useEffect, useCallback } from 'react';
import { 
  XMarkIcon,
  InformationCircleIcon,
  CpuChipIcon,
  ChatBubbleBottomCenterTextIcon,
  LinkIcon
} from '@heroicons/react/24/outline';
import { cn } from '../../utils/cn';
import agentsService, { 
  PROVIDER_CONFIGS, 
  DEFAULT_AGENT_VALUES, 
  AgentProvider,
  CreateAgentData,
  getBackendProviderConfig,
} from '../../services/agents';

interface AgentFormProps {
  agent?: {
    id?: string;
    name: string;
    description: string;
    provider: AgentProvider;
    model_name: string;
    base_url?: string;
    temperature: number;
    max_tokens: number;
    timeout: number;
    system_prompt: string;
    context_prompt: string;
    status: 'active' | 'inactive' | 'draft';
    use_memory: boolean;
    memory_ttl: number;
    accounts?: string[];
  };
  whatsappAccounts?: Array<{ id: string; name: string; phone_number: string }>;
  onSubmit: (data: CreateAgentData) => void;
  onCancel: () => void;
  isLoading?: boolean;
}

type Tab = 'basic' | 'model' | 'prompts' | 'accounts';

export const AgentForm: React.FC<AgentFormProps> = ({
  agent,
  whatsappAccounts = [],
  onSubmit,
  onCancel,
  isLoading = false,
}) => {
  const [activeTab, setActiveTab] = useState<Tab>('basic');
  const [formData, setFormData] = useState(agent || DEFAULT_AGENT_VALUES);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [backendBaseUrl, setBackendBaseUrl] = useState<string>('');

  const isEditing = Boolean(agent?.id);

  // Fetch backend provider config on mount
  useEffect(() => {
    const loadBackendConfig = async () => {
      const config = await getBackendProviderConfig(formData.provider || 'kimi');
      if (config?.base_url) {
        setBackendBaseUrl(config.base_url);
      }
    };
    loadBackendConfig();
  }, [formData.provider]);

  useEffect(() => {
    if (agent) {
      setFormData({ ...DEFAULT_AGENT_VALUES, ...agent });
    }
  }, [agent]);

  const handleProviderChange = useCallback(async (provider: AgentProvider) => {
    const config = PROVIDER_CONFIGS[provider];
    
    // Fetch base URL from backend
    const backendConfig = await getBackendProviderConfig(provider);
    const baseUrl = backendConfig?.base_url || '';
    
    setFormData(prev => ({
      ...prev,
      provider,
      model_name: config.models[0],
      base_url: baseUrl,
    }));
    
    if (baseUrl) {
      setBackendBaseUrl(baseUrl);
    }
  }, []);

  const handleChange = (field: string, value: unknown) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: '' }));
    }
  };

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};
    
    if (!formData.name?.trim()) {
      newErrors.name = 'Nome é obrigatório';
    }
    if (!formData.system_prompt?.trim()) {
      newErrors.system_prompt = 'System prompt é obrigatório';
    }
    
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (validate()) {
      // Prepare data for submission (api_key is handled by backend)
      const submitData: CreateAgentData = {
        name: formData.name || '',
        description: formData.description,
        provider: formData.provider || 'kimi',
        model_name: formData.model_name || '',
        base_url: formData.base_url,
        temperature: formData.temperature,
        max_tokens: formData.max_tokens,
        timeout: formData.timeout,
        system_prompt: formData.system_prompt,
        context_prompt: formData.context_prompt,
        status: formData.status,
        use_memory: formData.use_memory,
        memory_ttl: formData.memory_ttl,
        accounts: formData.accounts,
      };
      onSubmit(submitData);
    }
  };

  const tabs = [
    { id: 'basic' as Tab, label: 'Informações', icon: InformationCircleIcon },
    { id: 'model' as Tab, label: 'Modelo', icon: CpuChipIcon },
    { id: 'prompts' as Tab, label: 'Prompts', icon: ChatBubbleBottomCenterTextIcon },
    { id: 'accounts' as Tab, label: 'Contas', icon: LinkIcon },
  ];

  const currentProvider = PROVIDER_CONFIGS[formData.provider || 'kimi'];

  return (
    <form onSubmit={handleSubmit} className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-200 dark:border-zinc-700">
        <h2 className="text-xl font-semibold text-zinc-900 dark:text-white">
          {isEditing ? 'Editar Agente' : 'Novo Agente'}
        </h2>
        <button
          type="button"
          onClick={onCancel}
          className="p-2 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
        >
          <XMarkIcon className="w-5 h-5 text-zinc-500" />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-zinc-200 dark:border-zinc-700 px-6">
        {tabs.map(tab => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors",
              activeTab === tab.id
                ? "border-primary-500 text-primary-600 dark:text-primary-400"
                : "border-transparent text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
            )}
          >
            <tab.icon className="w-4 h-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {/* Basic Tab */}
        {activeTab === 'basic' && (
          <div className="space-y-6">
            {/* Name */}
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                Nome do Agente *
              </label>
              <input
                type="text"
                value={formData.name || ''}
                onChange={e => handleChange('name', e.target.value)}
                placeholder="Ex: Assistente de Vendas"
                className={cn(
                  "w-full px-4 py-2.5 rounded-lg border transition-colors",
                  "bg-white dark:bg-zinc-800",
                  "text-zinc-900 dark:text-white placeholder-zinc-400",
                  errors.name
                    ? "border-red-300 dark:border-red-600 focus:ring-red-500"
                    : "border-zinc-200 dark:border-zinc-700 focus:ring-primary-500"
                )}
              />
              {errors.name && <p className="mt-1 text-sm text-red-500">{errors.name}</p>}
            </div>

            {/* Description */}
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                Descrição
              </label>
              <textarea
                value={formData.description || ''}
                onChange={e => handleChange('description', e.target.value)}
                placeholder="Descreva a função deste agente..."
                rows={3}
                className={cn(
                  "w-full px-4 py-2.5 rounded-lg border transition-colors resize-none",
                  "bg-white dark:bg-zinc-800",
                  "text-zinc-900 dark:text-white placeholder-zinc-400",
                  "border-zinc-200 dark:border-zinc-700 focus:ring-primary-500"
                )}
              />
            </div>

            {/* Status */}
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                Status
              </label>
              <select
                value={formData.status || 'draft'}
                onChange={e => handleChange('status', e.target.value)}
                className={cn(
                  "w-full px-4 py-2.5 rounded-lg border transition-colors",
                  "bg-white dark:bg-zinc-800",
                  "text-zinc-900 dark:text-white",
                  "border-zinc-200 dark:border-zinc-700 focus:ring-primary-500"
                )}
              >
                <option value="draft">Rascunho</option>
                <option value="active">Ativo</option>
                <option value="inactive">Inativo</option>
              </select>
            </div>
          </div>
        )}

        {/* Model Tab */}
        {activeTab === 'model' && (
          <div className="space-y-6">
            {/* Provider */}
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                Provedor *
              </label>
              <div className="grid grid-cols-2 gap-3">
                {Object.entries(PROVIDER_CONFIGS).map(([key, config]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => handleProviderChange(key as AgentProvider)}
                    className={cn(
                      "px-4 py-3 rounded-lg border-2 text-left transition-all",
                      formData.provider === key
                        ? "border-primary-500 bg-primary-50 dark:bg-primary-900/20"
                        : "border-zinc-200 dark:border-zinc-700 hover:border-zinc-300"
                    )}
                  >
                    <div className="font-medium text-zinc-900 dark:text-white">
                      {config.name}
                    </div>
                    <div className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">
                      {config.models.length} modelos
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {/* Model */}
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                Modelo
              </label>
              <select
                value={formData.model_name || ''}
                onChange={e => handleChange('model_name', e.target.value)}
                className={cn(
                  "w-full px-4 py-2.5 rounded-lg border transition-colors",
                  "bg-white dark:bg-zinc-800",
                  "text-zinc-900 dark:text-white",
                  "border-zinc-200 dark:border-zinc-700 focus:ring-primary-500"
                )}
              >
                {currentProvider.models.map(model => (
                  <option key={model} value={model}>{model}</option>
                ))}
              </select>
              {formData.provider === 'kimi' && (
                <p className="mt-1 text-xs text-blue-600 dark:text-blue-400">
                  ℹ️ Kimi usa API no estilo Anthropic (backend gerencia)
                </p>
              )}
            </div>

            {/* Base URL - Loaded from Backend */}
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                Base URL
                <span className="ml-2 text-xs text-blue-600 dark:text-blue-400 font-normal">
                  (carregado do backend)
                </span>
              </label>
              <input
                type="url"
                value={formData.base_url || backendBaseUrl || ''}
                readOnly
                className={cn(
                  "w-full px-4 py-2.5 rounded-lg border transition-colors",
                  "bg-zinc-100 dark:bg-zinc-800",
                  "text-zinc-600 dark:text-zinc-400",
                  "border-zinc-200 dark:border-zinc-700",
                  "cursor-not-allowed"
                )}
              />
              <p className="mt-1 text-xs text-zinc-500">
                Esta URL é configurada automaticamente pelo backend para garantir compatibilidade com a API Anthropic.
              </p>
            </div>

            {/* API Key Notice */}
            <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
              <p className="text-sm text-blue-700 dark:text-blue-300">
                <strong>Nota:</strong> A API Key é configurada no backend pelo administrador do sistema. 
                {currentProvider.requiresApiKey 
                  ? 'Entre em contato com o suporte para configurar a API Key.' 
                  : 'Este provedor não requer API Key.'}
              </p>
            </div>

            {/* Temperature & Max Tokens */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  Temperatura: {formData.temperature}
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.1"
                  value={formData.temperature || 0.7}
                  onChange={e => handleChange('temperature', parseFloat(e.target.value))}
                  className="w-full accent-primary-500"
                />
                <div className="flex justify-between text-xs text-zinc-400 mt-1">
                  <span>Preciso</span>
                  <span>Criativo</span>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  Max Tokens
                </label>
                <input
                  type="number"
                  min="100"
                  max="128000"
                  step="100"
                  value={formData.max_tokens || 32768}
                  onChange={e => handleChange('max_tokens', parseInt(e.target.value))}
                  className={cn(
                    "w-full px-4 py-2.5 rounded-lg border transition-colors",
                    "bg-white dark:bg-zinc-800",
                    "text-zinc-900 dark:text-white",
                    "border-zinc-200 dark:border-zinc-700"
                  )}
                />
                {formData.model_name === 'kimi-for-coding' && (
                  <p className="mt-1 text-xs text-zinc-500">Máx: 32768 para kimi-for-coding</p>
                )}
              </div>
            </div>

            {/* Timeout & Memory */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  Timeout (segundos)
                </label>
                <input
                  type="number"
                  min="5"
                  max="120"
                  value={formData.timeout || 30}
                  onChange={e => handleChange('timeout', parseInt(e.target.value))}
                  className={cn(
                    "w-full px-4 py-2.5 rounded-lg border transition-colors",
                    "bg-white dark:bg-zinc-800",
                    "text-zinc-900 dark:text-white",
                    "border-zinc-200 dark:border-zinc-700"
                  )}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  TTL da Memória (segundos)
                </label>
                <input
                  type="number"
                  min="60"
                  max="86400"
                  step="60"
                  value={formData.memory_ttl || 3600}
                  onChange={e => handleChange('memory_ttl', parseInt(e.target.value))}
                  disabled={!formData.use_memory}
                  className={cn(
                    "w-full px-4 py-2.5 rounded-lg border transition-colors",
                    "bg-white dark:bg-zinc-800",
                    "text-zinc-900 dark:text-white",
                    "border-zinc-200 dark:border-zinc-700",
                    "disabled:opacity-50"
                  )}
                />
              </div>
            </div>

            {/* Use Memory Toggle */}
            <div className="flex items-center justify-between p-4 bg-zinc-50 dark:bg-zinc-800/50 rounded-lg">
              <div>
                <div className="font-medium text-zinc-900 dark:text-white">
                  Usar Memória de Contexto
                </div>
                <div className="text-sm text-zinc-500 dark:text-zinc-400">
                  Mantém histórico de conversas no Redis
                </div>
              </div>
              <button
                type="button"
                onClick={() => handleChange('use_memory', !formData.use_memory)}
                className={cn(
                  "relative w-12 h-6 rounded-full transition-colors",
                  formData.use_memory ? "bg-primary-500" : "bg-zinc-300 dark:bg-zinc-600"
                )}
              >
                <span className={cn(
                  "absolute top-0.5 w-5 h-5 rounded-full bg-white shadow-sm transition-transform",
                  formData.use_memory ? "translate-x-6" : "translate-x-0.5"
                )} />
              </button>
            </div>
          </div>
        )}

        {/* Prompts Tab */}
        {activeTab === 'prompts' && (
          <div className="space-y-6">
            {/* System Prompt */}
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                System Prompt *
              </label>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-2">
                Define a personalidade e comportamento base do agente
              </p>
              <textarea
                value={formData.system_prompt || ''}
                onChange={e => handleChange('system_prompt', e.target.value)}
                placeholder="Você é um assistente..."
                rows={8}
                className={cn(
                  "w-full px-4 py-3 rounded-lg border transition-colors resize-none font-mono text-sm",
                  "bg-white dark:bg-zinc-800",
                  "text-zinc-900 dark:text-white placeholder-zinc-400",
                  errors.system_prompt
                    ? "border-red-300 dark:border-red-600"
                    : "border-zinc-200 dark:border-zinc-700"
                )}
              />
              {errors.system_prompt && <p className="mt-1 text-sm text-red-500">{errors.system_prompt}</p>}
            </div>

            {/* Context Prompt */}
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                Contexto Adicional
              </label>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-2">
                Informações adicionais sobre o negócio, produtos, políticas, etc.
              </p>
              <textarea
                value={formData.context_prompt || ''}
                onChange={e => handleChange('context_prompt', e.target.value)}
                placeholder="Informações sobre o cardápio, horários de funcionamento..."
                rows={8}
                className={cn(
                  "w-full px-4 py-3 rounded-lg border transition-colors resize-none font-mono text-sm",
                  "bg-white dark:bg-zinc-800",
                  "text-zinc-900 dark:text-white placeholder-zinc-400",
                  "border-zinc-200 dark:border-zinc-700"
                )}
              />
            </div>

            {/* Preview */}
            <div className="p-4 bg-zinc-100 dark:bg-zinc-800 rounded-lg">
              <div className="text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                Preview do Prompt Completo
              </div>
              <pre className="text-xs text-zinc-600 dark:text-zinc-400 whitespace-pre-wrap font-mono">
                {formData.system_prompt}
                {formData.context_prompt ? `\n\n${formData.context_prompt}` : ''}
              </pre>
            </div>
          </div>
        )}

        {/* Accounts Tab */}
        {activeTab === 'accounts' && (
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                Contas WhatsApp Associadas
              </label>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-4">
                Selecione as contas WhatsApp que este agente irá atender
              </p>

              {whatsappAccounts.length === 0 ? (
                <div className="p-8 text-center bg-zinc-50 dark:bg-zinc-800/50 rounded-lg">
                  <LinkIcon className="w-12 h-12 mx-auto text-zinc-300 dark:text-zinc-600 mb-3" />
                  <p className="text-zinc-500 dark:text-zinc-400">
                    Nenhuma conta WhatsApp cadastrada
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {whatsappAccounts.map(account => (
                    <label
                      key={account.id}
                      className={cn(
                        "flex items-center gap-3 p-4 rounded-lg border cursor-pointer transition-colors",
                        formData.accounts?.includes(account.id)
                          ? "border-primary-500 bg-primary-50 dark:bg-primary-900/20"
                          : "border-zinc-200 dark:border-zinc-700 hover:bg-zinc-50 dark:hover:bg-zinc-800"
                      )}
                    >
                      <input
                        type="checkbox"
                        checked={formData.accounts?.includes(account.id) || false}
                        onChange={(e) => {
                          const newAccounts = e.target.checked
                            ? [...(formData.accounts || []), account.id]
                            : (formData.accounts || []).filter(id => id !== account.id);
                          handleChange('accounts', newAccounts);
                        }}
                        className="w-4 h-4 rounded border-zinc-300 text-primary-600 focus:ring-primary-500"
                      />
                      <div className="flex-1">
                        <div className="font-medium text-zinc-900 dark:text-white">
                          {account.name}
                        </div>
                        <div className="text-sm text-zinc-500 dark:text-zinc-400">
                          {account.phone_number}
                        </div>
                      </div>
                    </label>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-zinc-200 dark:border-zinc-700">
        <button
          type="button"
          onClick={onCancel}
          disabled={isLoading}
          className={cn(
            "px-4 py-2 rounded-lg font-medium transition-colors",
            "text-zinc-700 dark:text-zinc-300",
            "hover:bg-zinc-100 dark:hover:bg-zinc-800",
            "disabled:opacity-50"
          )}
        >
          Cancelar
        </button>
        <button
          type="submit"
          disabled={isLoading}
          className={cn(
            "px-6 py-2 rounded-lg font-medium transition-colors",
            "bg-primary-600 hover:bg-primary-700 text-white",
            "disabled:opacity-50 disabled:cursor-not-allowed"
          )}
        >
          {isLoading ? 'Salvando...' : isEditing ? 'Salvar' : 'Criar Agente'}
        </button>
      </div>
    </form>
  );
};

export default AgentForm;
