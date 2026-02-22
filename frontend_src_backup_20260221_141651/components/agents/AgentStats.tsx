import React from 'react';
import { 
  ChatBubbleLeftRightIcon,
  EnvelopeIcon,
  ClockIcon,
  BoltIcon
} from '@heroicons/react/24/outline';
import { cn } from '../../utils/cn';

interface AgentStatsProps {
  stats: {
    total_conversations: number;
    total_messages: number;
    avg_response_time_ms: number;
    active_sessions: number;
  };
  isLoading?: boolean;
}

export const AgentStats: React.FC<AgentStatsProps> = ({ stats, isLoading }) => {
  const statItems = [
    {
      label: 'Conversas Totais',
      value: stats.total_conversations,
      icon: ChatBubbleLeftRightIcon,
      color: 'text-blue-500 bg-blue-100 dark:bg-blue-900/30',
    },
    {
      label: 'Mensagens Totais',
      value: stats.total_messages,
      icon: EnvelopeIcon,
      color: 'text-green-500 bg-green-100 dark:bg-green-900/30',
    },
    {
      label: 'Tempo Médio de Resposta',
      value: `${Math.round(stats.avg_response_time_ms)}ms`,
      icon: ClockIcon,
      color: 'text-yellow-500 bg-yellow-100 dark:bg-yellow-900/30',
    },
    {
      label: 'Sessões Ativas',
      value: stats.active_sessions,
      icon: BoltIcon,
      color: 'text-purple-500 bg-purple-100 dark:bg-purple-900/30',
    },
  ];

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="bg-white dark:bg-zinc-900 rounded-xl p-5 border border-zinc-200 dark:border-zinc-800 animate-pulse">
            <div className="w-10 h-10 rounded-lg bg-zinc-200 dark:bg-zinc-700 mb-3" />
            <div className="h-8 w-20 bg-zinc-200 dark:bg-zinc-700 rounded mb-2" />
            <div className="h-4 w-24 bg-zinc-100 dark:bg-zinc-800 rounded" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {statItems.map((item, index) => (
        <div 
          key={index}
          className="bg-white dark:bg-zinc-900 rounded-xl p-5 border border-zinc-200 dark:border-zinc-800 hover:shadow-md transition-shadow"
        >
          <div className={cn("w-10 h-10 rounded-lg flex items-center justify-center mb-3", item.color)}>
            <item.icon className="w-5 h-5" />
          </div>
          <div className="text-2xl font-bold text-zinc-900 dark:text-white mb-1">
            {item.value}
          </div>
          <div className="text-sm text-zinc-500 dark:text-zinc-400">
            {item.label}
          </div>
        </div>
      ))}
    </div>
  );
};

export default AgentStats;
