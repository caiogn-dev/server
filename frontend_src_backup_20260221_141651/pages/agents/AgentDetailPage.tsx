import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { 
  ArrowLeftIcon,
  PencilIcon,
  TrashIcon,
  PlayIcon,
  PauseIcon,
  DocumentDuplicateIcon,
  ChatBubbleLeftRightIcon,
  SparklesIcon
} from '@heroicons/react/24/outline';
import { cn } from '../../utils/cn';
import { AgentForm, AgentStats, AgentChatTest, ConversationList } from '../../components/agents';
import agentsService, { AgentDetail, AgentStats as Stats, AgentConversation } from '../../services/agents';

type Tab = 'overview' | 'edit' | 'test' | 'conversations';

export const AgentDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  
  const [agent, setAgent] = useState<AgentDetail | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [conversations, setConversations] = useState<AgentConversation[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>('overview');
  const [selectedConversation, setSelectedConversation] = useState<AgentConversation | null>(null);

  const loadAgent = useCallback(async () => {
    if (!id) return;
    
    setIsLoading(true);
    try {
      const [agentData, statsData, conversationsData] = await Promise.all([
        agentsService.getAgent(id),
        agentsService.getAgentStats(id),
        agentsService.getAgentConversations(id),
      ]);
      
      setAgent(agentData);
      setStats(statsData);
      setConversations(conversationsData);
    } catch (error) {
      console.error('Erro ao carregar agente:', error);
    } finally {
      setIsLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadAgent();
  }, [loadAgent]);

  const handleUpdate = async (data: any) => {
    if (!id) return;
    
    setIsSaving(true);
    try {
      const updated = await agentsService.updateAgent(id, data);
      setAgent(updated as AgentDetail);
      setActiveTab('overview');
    } catch (error) {
      console.error('Erro ao atualizar agente:', error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleToggleStatus = async () => {
    if (!agent || !id) return;
    
    try {
      const newStatus = agent.status === 'active' ? 'inactive' : 'active';
      const updated = await agentsService.updateAgent(id, { status: newStatus });
      setAgent(updated as AgentDetail);
    } catch (error) {
      console.error('Erro ao atualizar status:', error);
    }
  };

  const handleDelete = async () => {
    if (!id) return;
    if (!confirm('Tem certeza que deseja excluir este agente?')) return;
    
    try {
      await agentsService.deleteAgent(id);
      navigate('/agents');
    } catch (error) {
      console.error('Erro ao excluir agente:', error);
    }
  };

  const handleDuplicate = async () => {
    if (!agent) return;
    
    try {
      const newAgent = await agentsService.createAgent({
        name: `${agent.name} (cópia)`,
        description: agent.description,
        provider: agent.provider,
        model_name: agent.model_name,
        base_url: agent.base_url,
        temperature: agent.temperature,
        max_tokens: agent.max_tokens,
        timeout: agent.timeout,
        system_prompt: agent.system_prompt,
        context_prompt: agent.context_prompt,
        status: 'draft',
        use_memory: agent.use_memory,
        memory_ttl: agent.memory_ttl,
        // api_key is handled by backend, not sent from frontend
      });
      navigate(`/agents/${newAgent.id}`);
    } catch (error) {
      console.error('Erro ao duplicar agente:', error);
    }
  };

  const handleSendTestMessage = async (message: string, sessionId?: string) => {
    if (!id) throw new Error('ID do agente não encontrado');
    
    return await agentsService.processMessage(id, {
      message,
      session_id: sessionId,
      context: { test: true },
    });
  };

  const tabs = [
    { id: 'overview' as Tab, label: 'Visão Geral', icon: SparklesIcon },
    { id: 'edit' as Tab, label: 'Editar', icon: PencilIcon },
    { id: 'test' as Tab, label: 'Testar', icon: ChatBubbleLeftRightIcon },
    { id: 'conversations' as Tab, label: 'Conversas', icon: ChatBubbleLeftRightIcon },
  ];

  if (isLoading) {
    return (
      <div className="p-6 max-w-7xl mx-auto">
        <div className="animate-pulse">
          <div className="h-8 w-64 bg-zinc-200 dark:bg-zinc-700 rounded mb-4" />
          <div className="h-4 w-96 bg-zinc-100 dark:bg-zinc-800 rounded mb-8" />
          <div className="grid grid-cols-4 gap-4 mb-8">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-24 bg-zinc-200 dark:bg-zinc-700 rounded-xl" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="p-6 max-w-7xl mx-auto">
        <div className="text-center py-16">
          <p className="text-xl font-medium text-zinc-900 dark:text-white mb-2">
            Agente não encontrado
          </p>
          <button
            onClick={() => navigate('/agents')}
            className="text-primary-600 hover:text-primary-700"
          >
            Voltar para lista
          </button>
        </div>
      </div>
    );
  }

  const statusColors = {
    active: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
    inactive: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
    draft: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300',
  };

  const providerColors = {
    kimi: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300',
    openai: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
    anthropic: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300',
    ollama: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div className="flex items-start gap-4">
          <button
            onClick={() => navigate('/agents')}
            className="p-2 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
          >
            <ArrowLeftIcon className="w-5 h-5 text-zinc-500" />
          </button>
          
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-2xl font-bold text-zinc-900 dark:text-white">
                {agent.name}
              </h1>
              <span className={cn(
                "px-2.5 py-0.5 rounded-full text-xs font-medium",
                statusColors[agent.status]
              )}>
                {agent.status === 'active' ? 'Ativo' : agent.status === 'inactive' ? 'Inativo' : 'Rascunho'}
              </span>
              <span className={cn(
                "px-2.5 py-0.5 rounded-full text-xs font-medium",
                providerColors[agent.provider]
              )}>
                {agent.provider.toUpperCase()}
              </span>
            </div>
            <p className="text-zinc-500 dark:text-zinc-400">
              {agent.description || `Modelo: ${agent.model_name}`}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleToggleStatus}
            className={cn(
              "inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
              agent.status === 'active'
                ? "bg-yellow-100 text-yellow-700 hover:bg-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-300"
                : "bg-green-100 text-green-700 hover:bg-green-200 dark:bg-green-900/30 dark:text-green-300"
            )}
          >
            {agent.status === 'active' ? (
              <>
                <PauseIcon className="w-4 h-4" />
                Desativar
              </>
            ) : (
              <>
                <PlayIcon className="w-4 h-4" />
                Ativar
              </>
            )}
          </button>
          
          <button
            onClick={handleDuplicate}
            className={cn(
              "inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
              "bg-zinc-100 text-zinc-700 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300"
            )}
          >
            <DocumentDuplicateIcon className="w-4 h-4" />
            Duplicar
          </button>
          
          <button
            onClick={handleDelete}
            className={cn(
              "inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
              "bg-red-100 text-red-700 hover:bg-red-200 dark:bg-red-900/30 dark:text-red-300"
            )}
          >
            <TrashIcon className="w-4 h-4" />
            Excluir
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-zinc-200 dark:border-zinc-700 mb-6">
        {tabs.map(tab => (
          <button
            key={tab.id}
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
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Stats */}
          {stats && <AgentStats stats={stats} />}
          
          {/* Config Overview */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Model Config */}
            <div className="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-6">
              <h3 className="font-semibold text-zinc-900 dark:text-white mb-4">
                Configuração do Modelo
              </h3>
              <dl className="space-y-3">
                <div className="flex justify-between">
                  <dt className="text-zinc-500 dark:text-zinc-400">Provedor</dt>
                  <dd className="font-medium text-zinc-900 dark:text-white capitalize">{agent.provider}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-zinc-500 dark:text-zinc-400">Modelo</dt>
                  <dd className="font-medium text-zinc-900 dark:text-white">{agent.model_name}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-zinc-500 dark:text-zinc-400">Temperatura</dt>
                  <dd className="font-medium text-zinc-900 dark:text-white">{agent.temperature}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-zinc-500 dark:text-zinc-400">Max Tokens</dt>
                  <dd className="font-medium text-zinc-900 dark:text-white">{agent.max_tokens}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-zinc-500 dark:text-zinc-400">Timeout</dt>
                  <dd className="font-medium text-zinc-900 dark:text-white">{agent.timeout}s</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-zinc-500 dark:text-zinc-400">Memória</dt>
                  <dd className={cn(
                    "font-medium",
                    agent.use_memory ? "text-green-600" : "text-zinc-400"
                  )}>
                    {agent.use_memory ? `Ativa (TTL: ${agent.memory_ttl}s)` : 'Desativada'}
                  </dd>
                </div>
              </dl>
            </div>

            {/* System Prompt Preview */}
            <div className="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-6">
              <h3 className="font-semibold text-zinc-900 dark:text-white mb-4">
                System Prompt
              </h3>
              <pre className="text-sm text-zinc-600 dark:text-zinc-400 whitespace-pre-wrap font-mono bg-zinc-50 dark:bg-zinc-800 p-4 rounded-lg max-h-48 overflow-y-auto">
                {agent.system_prompt}
              </pre>
            </div>
          </div>

          {/* Associated Accounts */}
          {agent.accounts && agent.accounts.length > 0 && (
            <div className="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-6">
              <h3 className="font-semibold text-zinc-900 dark:text-white mb-4">
                Contas WhatsApp Associadas
              </h3>
              <div className="flex flex-wrap gap-2">
                {agent.accounts.map(account => (
                  <span
                    key={account.id}
                    className="px-3 py-1.5 rounded-lg bg-zinc-100 dark:bg-zinc-800 text-sm"
                  >
                    {account.name} ({account.phone_number})
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'edit' && (
        <div className="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 overflow-hidden">
          <AgentForm
            agent={{
              ...agent,
              accounts: agent.accounts?.map(a => a.id) || []
            }}
            onSubmit={handleUpdate}
            onCancel={() => setActiveTab('overview')}
            isLoading={isSaving}
          />
        </div>
      )}

      {activeTab === 'test' && (
        <AgentChatTest
          agentName={agent.name}
          onSendMessage={handleSendTestMessage}
          onClearChat={() => {}}
        />
      )}

      {activeTab === 'conversations' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Conversation List */}
          <div className="lg:col-span-1">
            <div className="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-4">
              <h3 className="font-semibold text-zinc-900 dark:text-white mb-4">
                Conversas ({conversations.length})
              </h3>
              <ConversationList
                conversations={conversations}
                selectedId={selectedConversation?.id}
                onSelect={setSelectedConversation}
              />
            </div>
          </div>

          {/* Conversation Detail */}
          <div className="lg:col-span-2">
            {selectedConversation ? (
              <div className="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-semibold text-zinc-900 dark:text-white">
                    Conversa com {selectedConversation.phone_number || 'Teste'}
                  </h3>
                  <span className="text-xs text-zinc-500 font-mono">
                    {selectedConversation.session_id}
                  </span>
                </div>
                
                {selectedConversation.messages ? (
                  <div className="space-y-4 max-h-[500px] overflow-y-auto">
                    {selectedConversation.messages.map(message => (
                      <div
                        key={message.id}
                        className={cn(
                          "p-3 rounded-lg max-w-[80%]",
                          message.role === 'user'
                            ? "ml-auto bg-primary-600 text-white"
                            : "bg-zinc-100 dark:bg-zinc-800"
                        )}
                      >
                        <p className="whitespace-pre-wrap">{message.content}</p>
                        <p className="text-xs opacity-70 mt-1">
                          {new Date(message.created_at).toLocaleTimeString('pt-BR')}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-zinc-500 dark:text-zinc-400">
                    Carregando mensagens...
                  </p>
                )}
              </div>
            ) : (
              <div className="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-12 text-center">
                <ChatBubbleLeftRightIcon className="w-16 h-16 mx-auto text-zinc-200 dark:text-zinc-700 mb-4" />
                <p className="text-zinc-500 dark:text-zinc-400">
                  Selecione uma conversa para ver os detalhes
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default AgentDetailPage;
