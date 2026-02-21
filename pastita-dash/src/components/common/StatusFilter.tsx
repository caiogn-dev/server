import React from 'react';
import { ORDER_STATUS_CONFIG, CONVERSATION_STATUS_CONFIG } from './Badge';

interface StatusFilterOption {
  value: string;
  label: string;
  count?: number;
  color?: string;
}

interface StatusFilterProps {
  options: StatusFilterOption[];
  value: string | null;
  onChange: (value: string | null) => void;
  showCounts?: boolean;
  className?: string;
}

export const StatusFilter: React.FC<StatusFilterProps> = ({
  options,
  value,
  onChange,
  showCounts = true,
  className = '',
}) => {
  const colorMap: Record<string, string> = {
    warning: 'bg-yellow-500',
    info: 'bg-blue-500',
    purple: 'bg-purple-500',
    orange: 'bg-orange-500',
    success: 'bg-green-500',
    teal: 'bg-teal-500',
    indigo: 'bg-indigo-500',
    danger: 'bg-red-500',
    gray: 'bg-gray-500',
  };

  return (
    <div className={`flex flex-wrap gap-2 ${className}`}>
      <button
        onClick={() => onChange(null)}
        className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
          value === null
            ? 'bg-gray-900 dark:bg-white text-white dark:text-gray-900 shadow-md'
            : 'bg-white dark:bg-zinc-900 text-gray-700 dark:text-zinc-300 border border-gray-200 dark:border-zinc-800 hover:bg-gray-50 dark:hover:bg-zinc-700'
        }`}
      >
        Todos
      </button>
      {options.map((option) => (
        <button
          key={option.value}
          onClick={() => onChange(option.value)}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${
            value === option.value
              ? 'bg-gray-900 dark:bg-white text-white dark:text-gray-900 shadow-md'
              : 'bg-white dark:bg-zinc-900 text-gray-700 dark:text-zinc-300 border border-gray-200 dark:border-zinc-800 hover:bg-gray-50 dark:hover:bg-zinc-700'
          }`}
        >
          {option.color && (
            <span className={`w-2 h-2 rounded-full ${colorMap[option.color] || 'bg-gray-400'}`} />
          )}
          <span>{option.label}</span>
          {showCounts && option.count !== undefined && (
            <span className={`px-1.5 py-0.5 rounded-full text-xs ${
              value === option.value
                ? 'bg-white/20 text-white dark:bg-black/20 dark:text-gray-900'
                : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-zinc-400'
            }`}>
              {option.count}
            </span>
          )}
        </button>
      ))}
    </div>
  );
};

// Pre-configured Order Status Filter
interface OrderStatusFilterProps {
  value: string | null;
  onChange: (value: string | null) => void;
  counts?: Record<string, number>;
  className?: string;
}

export const OrderStatusFilter: React.FC<OrderStatusFilterProps> = ({
  value,
  onChange,
  counts = {},
  className = '',
}) => {
  const options: StatusFilterOption[] = Object.entries(ORDER_STATUS_CONFIG).map(([key, config]) => ({
    value: key,
    label: config.label,
    count: counts[key],
    color: config.variant,
  }));

  return (
    <StatusFilter
      options={options}
      value={value}
      onChange={onChange}
      className={className}
    />
  );
};

// Pre-configured Conversation Status Filter
interface ConversationStatusFilterProps {
  value: string | null;
  onChange: (value: string | null) => void;
  counts?: Record<string, number>;
  className?: string;
}

export const ConversationStatusFilter: React.FC<ConversationStatusFilterProps> = ({
  value,
  onChange,
  counts = {},
  className = '',
}) => {
  const options: StatusFilterOption[] = Object.entries(CONVERSATION_STATUS_CONFIG).map(([key, config]) => ({
    value: key,
    label: config.label,
    count: counts[key],
    color: config.variant,
  }));

  return (
    <StatusFilter
      options={options}
      value={value}
      onChange={onChange}
      className={className}
    />
  );
};

// Tabs-style Status Filter
interface StatusTabsProps {
  tabs: Array<{
    value: string | null;
    label: string;
    count?: number;
    icon?: React.ReactNode;
  }>;
  value: string | null;
  onChange: (value: string | null) => void;
  className?: string;
}

export const StatusTabs: React.FC<StatusTabsProps> = ({
  tabs,
  value,
  onChange,
  className = '',
}) => {
  return (
    <div className={`border-b border-gray-200 dark:border-zinc-800 ${className}`}>
      <nav className="-mb-px flex space-x-8" aria-label="Tabs">
        {tabs.map((tab) => (
          <button
            key={tab.value ?? 'all'}
            onClick={() => onChange(tab.value)}
            className={`whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center gap-2 transition-colors ${
              value === tab.value
                ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                : 'border-transparent text-gray-500 dark:text-zinc-400 hover:text-gray-700 dark:hover:text-zinc-300 hover:border-gray-300 dark:hover:border-gray-600'
            }`}
          >
            {tab.icon}
            <span>{tab.label}</span>
            {tab.count !== undefined && (
              <span className={`ml-2 py-0.5 px-2 rounded-full text-xs ${
                value === tab.value
                  ? 'bg-primary-100 dark:bg-primary-900/40 text-primary-600 dark:text-primary-400'
                  : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-zinc-400'
              }`}>
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </nav>
    </div>
  );
};

// Order Status Tabs
export const OrderStatusTabs: React.FC<{
  value: string | null;
  onChange: (value: string | null) => void;
  counts?: Record<string, number>;
  className?: string;
}> = ({ value, onChange, counts = {}, className = '' }) => {
  const tabs = [
    { value: null, label: 'Todos', count: Object.values(counts).reduce((a, b) => a + b, 0) },
    { value: 'pending', label: 'Pendentes', count: counts.pending },
    { value: 'processing', label: 'Processando', count: counts.processing },
    { value: 'confirmed', label: 'Confirmados', count: counts.confirmed },
    { value: 'paid', label: 'Pagos', count: counts.paid },
    { value: 'preparing', label: 'Preparando', count: counts.preparing },
    { value: 'ready', label: 'Prontos', count: counts.ready },
    { value: 'shipped', label: 'Enviados', count: counts.shipped },
    { value: 'out_for_delivery', label: 'Em Entrega', count: counts.out_for_delivery },
    { value: 'delivered', label: 'Entregues', count: counts.delivered },
    { value: 'cancelled', label: 'Cancelados', count: counts.cancelled },
    { value: 'refunded', label: 'Reembolsados', count: counts.refunded },
    { value: 'failed', label: 'Falhou', count: counts.failed },
  ];

  return <StatusTabs tabs={tabs} value={value} onChange={onChange} className={className} />;
};

// Quick Filter Pills
interface QuickFilterPillsProps {
  filters: Array<{
    key: string;
    label: string;
    active: boolean;
  }>;
  onToggle: (key: string) => void;
  className?: string;
}

export const QuickFilterPills: React.FC<QuickFilterPillsProps> = ({
  filters,
  onToggle,
  className = '',
}) => {
  return (
    <div className={`flex flex-wrap gap-2 ${className}`}>
      {filters.map((filter) => (
        <button
          key={filter.key}
          onClick={() => onToggle(filter.key)}
          className={`px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
            filter.active
              ? 'bg-primary-100 dark:bg-primary-900/40 text-primary-700 dark:text-primary-300 border border-primary-200 dark:border-primary-700'
              : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-zinc-400 border border-transparent hover:bg-gray-200 dark:hover:bg-gray-600'
          }`}
        >
          {filter.label}
        </button>
      ))}
    </div>
  );
};
