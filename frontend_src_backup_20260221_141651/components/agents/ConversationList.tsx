import React from 'react';
import { 
  ChatBubbleLeftRightIcon,
  PhoneIcon,
  ClockIcon,
  ChevronRightIcon
} from '@heroicons/react/24/outline';
import { cn } from '../../utils/cn';

interface Conversation {
  id: string;
  session_id: string;
  phone_number: string;
  message_count: number;
  last_message_at: string;
  created_at: string;
}

interface ConversationListProps {
  conversations: Conversation[];
  selectedId?: string;
  onSelect: (conversation: Conversation) => void;
  isLoading?: boolean;
}

export const ConversationList: React.FC<ConversationListProps> = ({
  conversations,
  selectedId,
  onSelect,
  isLoading,
}) => {
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Agora';
    if (diffMins < 60) return `${diffMins}min atrás`;
    if (diffHours < 24) return `${diffHours}h atrás`;
    if (diffDays < 7) return `${diffDays}d atrás`;
    return date.toLocaleDateString('pt-BR');
  };

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[...Array(5)].map((_, i) => (
          <div 
            key={i}
            className="p-4 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 animate-pulse"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-zinc-200 dark:bg-zinc-700" />
              <div className="flex-1">
                <div className="h-4 w-32 bg-zinc-200 dark:bg-zinc-700 rounded mb-2" />
                <div className="h-3 w-24 bg-zinc-100 dark:bg-zinc-800 rounded" />
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (conversations.length === 0) {
    return (
      <div className="text-center py-12">
        <ChatBubbleLeftRightIcon className="w-16 h-16 mx-auto text-zinc-200 dark:text-zinc-700 mb-4" />
        <p className="text-zinc-500 dark:text-zinc-400 mb-2">
          Nenhuma conversa encontrada
        </p>
        <p className="text-sm text-zinc-400 dark:text-zinc-500">
          As conversas aparecerão aqui quando o agente for utilizado
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {conversations.map(conversation => (
        <button
          key={conversation.id}
          onClick={() => onSelect(conversation)}
          className={cn(
            "w-full p-4 rounded-lg border text-left transition-all",
            "hover:shadow-md",
            selectedId === conversation.id
              ? "border-primary-500 bg-primary-50 dark:bg-primary-900/20"
              : "border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 hover:border-zinc-300"
          )}
        >
          <div className="flex items-center gap-3">
            {/* Avatar */}
            <div className={cn(
              "w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0",
              "bg-zinc-100 dark:bg-zinc-800"
            )}>
              <PhoneIcon className="w-5 h-5 text-zinc-500 dark:text-zinc-400" />
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <span className="font-medium text-zinc-900 dark:text-white truncate">
                  {conversation.phone_number || 'Teste'}
                </span>
                <span className="text-xs text-zinc-500 dark:text-zinc-400 flex-shrink-0">
                  {formatDate(conversation.last_message_at)}
                </span>
              </div>
              
              <div className="flex items-center gap-3 mt-1">
                <span className="text-sm text-zinc-500 dark:text-zinc-400">
                  {conversation.message_count} mensagens
                </span>
                <span className="text-xs text-zinc-400 dark:text-zinc-500 font-mono">
                  {conversation.session_id.slice(0, 8)}...
                </span>
              </div>
            </div>

            {/* Arrow */}
            <ChevronRightIcon className="w-5 h-5 text-zinc-400 flex-shrink-0" />
          </div>
        </button>
      ))}
    </div>
  );
};

export default ConversationList;
