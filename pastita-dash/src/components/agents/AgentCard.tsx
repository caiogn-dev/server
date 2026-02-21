import React from 'react';
import { 
  CpuChipIcon, 
  PlayIcon, 
  PauseIcon, 
  PencilIcon,
  TrashIcon,
  ChatBubbleLeftRightIcon,
  ClockIcon,
  SparklesIcon
} from '@heroicons/react/24/outline';
import { cn } from '../../utils/cn';

interface AgentCardProps {
  agent: {
    id: string;
    name: string;
    description: string;
    provider: 'kimi' | 'openai' | 'anthropic' | 'ollama';
    model_name: string;
    status: 'active' | 'inactive' | 'draft';
    temperature: number;
    max_tokens: number;
    use_memory: boolean;
    created_at: string;
    updated_at: string;
  };
  onEdit?: (id: string) => void;
  onDelete?: (id: string) => void;
  onToggleStatus?: (id: string) => void;
  onTest?: (id: string) => void;
  onViewConversations?: (id: string) => void;
}

const providerColors: Record<string, { bg: string; text: string; border: string }> = {
  kimi: { bg: 'bg-purple-100 dark:bg-purple-900/30', text: 'text-purple-700 dark:text-purple-300', border: 'border-purple-200 dark:border-purple-800' },
  openai: { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-700 dark:text-green-300', border: 'border-green-200 dark:border-green-800' },
  anthropic: { bg: 'bg-orange-100 dark:bg-orange-900/30', text: 'text-orange-700 dark:text-orange-300', border: 'border-orange-200 dark:border-orange-800' },
  ollama: { bg: 'bg-blue-100 dark:bg-blue-900/30', text: 'text-blue-700 dark:text-blue-300', border: 'border-blue-200 dark:border-blue-800' },
};

const statusColors: Record<string, { bg: string; text: string; dot: string }> = {
  active: { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-700 dark:text-green-300', dot: 'bg-green-500' },
  inactive: { bg: 'bg-gray-100 dark:bg-gray-800', text: 'text-gray-700 dark:text-gray-300', dot: 'bg-gray-400' },
  draft: { bg: 'bg-yellow-100 dark:bg-yellow-900/30', text: 'text-yellow-700 dark:text-yellow-300', dot: 'bg-yellow-500' },
};

const providerNames: Record<string, string> = {
  kimi: 'Kimi',
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  ollama: 'Ollama',
};

const statusNames: Record<string, string> = {
  active: 'Ativo',
  inactive: 'Inativo',
  draft: 'Rascunho',
};

export const AgentCard: React.FC<AgentCardProps> = ({
  agent,
  onEdit,
  onDelete,
  onToggleStatus,
  onTest,
  onViewConversations,
}) => {
  const providerStyle = providerColors[agent.provider] || providerColors.kimi;
  const statusStyle = statusColors[agent.status] || statusColors.draft;

  return (
    <div className={cn(
      "bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800",
      "shadow-sm hover:shadow-md transition-all duration-200",
      "overflow-hidden"
    )}>
      {/* Header */}
      <div className="p-5 border-b border-zinc-100 dark:border-zinc-800">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className={cn(
              "w-10 h-10 rounded-lg flex items-center justify-center",
              providerStyle.bg, providerStyle.border, "border"
            )}>
              <CpuChipIcon className={cn("w-5 h-5", providerStyle.text)} />
            </div>
            <div>
              <h3 className="font-semibold text-zinc-900 dark:text-white text-lg">
                {agent.name}
              </h3>
              <div className="flex items-center gap-2 mt-1">
                <span className={cn(
                  "px-2 py-0.5 rounded-full text-xs font-medium",
                  providerStyle.bg, providerStyle.text
                )}>
                  {providerNames[agent.provider]}
                </span>
                <span className="text-zinc-400 dark:text-zinc-500 text-xs">
                  {agent.model_name}
                </span>
              </div>
            </div>
          </div>
          
          {/* Status Badge */}
          <div className={cn(
            "flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium",
            statusStyle.bg, statusStyle.text
          )}>
            <span className={cn("w-1.5 h-1.5 rounded-full", statusStyle.dot)} />
            {statusNames[agent.status]}
          </div>
        </div>
        
        {agent.description && (
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400 line-clamp-2">
            {agent.description}
          </p>
        )}
      </div>

      {/* Stats */}
      <div className="px-5 py-3 bg-zinc-50 dark:bg-zinc-800/50 grid grid-cols-3 gap-4">
        <div className="text-center">
          <div className="text-xs text-zinc-500 dark:text-zinc-400 mb-0.5">Temperatura</div>
          <div className="font-semibold text-zinc-900 dark:text-white">{agent.temperature}</div>
        </div>
        <div className="text-center">
          <div className="text-xs text-zinc-500 dark:text-zinc-400 mb-0.5">Max Tokens</div>
          <div className="font-semibold text-zinc-900 dark:text-white">{agent.max_tokens}</div>
        </div>
        <div className="text-center">
          <div className="text-xs text-zinc-500 dark:text-zinc-400 mb-0.5">Memória</div>
          <div className={cn(
            "font-semibold",
            agent.use_memory ? "text-green-600 dark:text-green-400" : "text-zinc-400"
          )}>
            {agent.use_memory ? 'Ativa' : 'Desativada'}
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="p-3 border-t border-zinc-100 dark:border-zinc-800 flex items-center justify-between">
        <div className="flex items-center gap-1">
          {onTest && (
            <button
              onClick={() => onTest(agent.id)}
              className={cn(
                "p-2 rounded-lg transition-colors",
                "text-zinc-500 hover:text-primary-600 hover:bg-primary-50",
                "dark:text-zinc-400 dark:hover:text-primary-400 dark:hover:bg-primary-900/30"
              )}
              title="Testar agente"
            >
              <SparklesIcon className="w-5 h-5" />
            </button>
          )}
          
          {onViewConversations && (
            <button
              onClick={() => onViewConversations(agent.id)}
              className={cn(
                "p-2 rounded-lg transition-colors",
                "text-zinc-500 hover:text-blue-600 hover:bg-blue-50",
                "dark:text-zinc-400 dark:hover:text-blue-400 dark:hover:bg-blue-900/30"
              )}
              title="Ver conversas"
            >
              <ChatBubbleLeftRightIcon className="w-5 h-5" />
            </button>
          )}
          
          {onToggleStatus && (
            <button
              onClick={() => onToggleStatus(agent.id)}
              className={cn(
                "p-2 rounded-lg transition-colors",
                agent.status === 'active' 
                  ? "text-yellow-500 hover:text-yellow-600 hover:bg-yellow-50 dark:hover:bg-yellow-900/30"
                  : "text-green-500 hover:text-green-600 hover:bg-green-50 dark:hover:bg-green-900/30"
              )}
              title={agent.status === 'active' ? 'Desativar' : 'Ativar'}
            >
              {agent.status === 'active' 
                ? <PauseIcon className="w-5 h-5" />
                : <PlayIcon className="w-5 h-5" />
              }
            </button>
          )}
        </div>
        
        <div className="flex items-center gap-1">
          {onEdit && (
            <button
              onClick={() => onEdit(agent.id)}
              className={cn(
                "p-2 rounded-lg transition-colors",
                "text-zinc-500 hover:text-zinc-700 hover:bg-zinc-100",
                "dark:text-zinc-400 dark:hover:text-zinc-200 dark:hover:bg-zinc-800"
              )}
              title="Editar"
            >
              <PencilIcon className="w-5 h-5" />
            </button>
          )}
          
          {onDelete && (
            <button
              onClick={() => onDelete(agent.id)}
              className={cn(
                "p-2 rounded-lg transition-colors",
                "text-zinc-500 hover:text-red-600 hover:bg-red-50",
                "dark:text-zinc-400 dark:hover:text-red-400 dark:hover:bg-red-900/30"
              )}
              title="Excluir"
            >
              <TrashIcon className="w-5 h-5" />
            </button>
          )}
        </div>
      </div>

      {/* Footer - Timestamp */}
      <div className="px-5 py-2 bg-zinc-50 dark:bg-zinc-800/30 border-t border-zinc-100 dark:border-zinc-800">
        <div className="flex items-center gap-1 text-xs text-zinc-400 dark:text-zinc-500">
          <ClockIcon className="w-3.5 h-3.5" />
          <span>Atualizado em {new Date(agent.updated_at).toLocaleDateString('pt-BR')}</span>
        </div>
      </div>
    </div>
  );
};

export default AgentCard;
