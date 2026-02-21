import React from 'react';

interface PageTitleProps {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  className?: string;
}

/**
 * PageTitle component for consistent page headers.
 * 
 * Use this instead of <Header /> inside pages to avoid duplication
 * with the MainLayout header.
 * 
 * @example
 * <PageTitle 
 *   title="Dashboard" 
 *   subtitle="Última atualização: 10:30"
 *   actions={<Button>Ação</Button>}
 * />
 */
export const PageTitle: React.FC<PageTitleProps> = ({
  title,
  subtitle,
  actions,
  className = '',
}) => {
  return (
    <div className={`flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 sm:gap-4 mb-4 md:mb-6 ${className}`}>
      <div>
        <h1 className="text-xl md:text-2xl font-bold text-gray-900 dark:text-white">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-1 text-sm text-gray-500 dark:text-zinc-400">
            {subtitle}
          </p>
        )}
      </div>
      {actions && (
        <div className="flex items-center gap-2 sm:gap-3">
          {actions}
        </div>
      )}
    </div>
  );
};

export default PageTitle;
