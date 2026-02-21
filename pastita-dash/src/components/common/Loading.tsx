import React from 'react';

interface LoadingProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export const Loading: React.FC<LoadingProps> = ({ size = 'md', className = '' }) => {
  const sizes = {
    sm: 'h-4 w-4',
    md: 'h-8 w-8',
    lg: 'h-12 w-12',
  };

  return (
    <div className={`flex items-center justify-center ${className}`}>
      <div className={`animate-spin rounded-full border-b-2 border-primary-500 ${sizes[size]}`}></div>
    </div>
  );
};

export const PageLoading: React.FC = () => {
  return (
    <div className="flex items-center justify-center min-h-[400px]">
      <div className="text-center">
        <Loading size="lg" />
        <p className="mt-4 text-gray-500 dark:text-zinc-400">Carregando...</p>
      </div>
    </div>
  );
};

export const FullPageLoading: React.FC = () => {
  return (
    <div className="fixed inset-0 bg-white dark:bg-black flex items-center justify-center z-50 transition-colors">
      <div className="text-center">
        <img 
          src="/pastita-logo.svg" 
          alt="Pastita" 
          className="w-20 h-20 mx-auto mb-4 animate-pulse"
        />
        <Loading size="md" />
        <p className="mt-4 text-gray-600 dark:text-zinc-400 font-medium">Pastita Dashboard</p>
      </div>
    </div>
  );
};
