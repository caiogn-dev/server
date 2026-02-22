import React from 'react';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  title?: string;
  subtitle?: string;
  actions?: React.ReactNode;
  noPadding?: boolean;
}

export const Card: React.FC<CardProps> = ({
  children,
  className = '',
  title,
  subtitle,
  actions,
  noPadding = false,
}) => {
  return (
    <div className={`bg-white dark:bg-zinc-900 rounded-xl shadow-sm border border-gray-100 dark:border-zinc-800 transition-colors ${className}`}>
      {(title || actions) && (
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 dark:border-zinc-800">
          <div>
            {title && <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h3>}
            {subtitle && <p className="text-sm text-gray-500 dark:text-zinc-400 mt-0.5">{subtitle}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={noPadding ? '' : 'p-6'}>{children}</div>
    </div>
  );
};

interface StatCardProps {
  title: string;
  value: string | number;
  change?: string;
  changeType?: 'positive' | 'negative' | 'neutral';
  icon?: React.ReactNode;
  className?: string;
}

export const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  change,
  changeType = 'neutral',
  icon,
  className = '',
}) => {
  const changeColors = {
    positive: 'text-green-600 bg-green-50 dark:text-green-400 dark:bg-green-900/30',
    negative: 'text-red-600 bg-red-50 dark:text-red-400 dark:bg-red-900/30',
    neutral: 'text-gray-600 bg-gray-50 dark:text-zinc-400 dark:bg-gray-700',
  };

  return (
    <div className={`bg-white dark:bg-zinc-900 rounded-xl shadow-sm border border-gray-100 dark:border-zinc-800 p-3 md:p-4 lg:p-6 transition-colors ${className}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-xs md:text-sm font-medium text-gray-500 dark:text-zinc-400 truncate">{title}</p>
          <p className="text-lg md:text-xl lg:text-2xl font-bold text-gray-900 dark:text-white mt-0.5 md:mt-1 truncate">{value}</p>
          {change && (
            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium mt-1 md:mt-2 ${changeColors[changeType]}`}>
              {change}
            </span>
          )}
        </div>
        {icon && (
          <div className="p-2 md:p-3 bg-primary-50 dark:bg-primary-900/30 rounded-lg text-primary-600 dark:text-primary-400 shrink-0">
            {icon}
          </div>
        )}
      </div>
    </div>
  );
};
