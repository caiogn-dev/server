/**
 * Skeleton Loading Component
 * 
 * Used to show loading states with animated placeholders.
 */
import React from 'react';

interface SkeletonProps {
  className?: string;
  width?: string | number;
  height?: string | number;
  variant?: 'text' | 'circular' | 'rectangular' | 'rounded';
  animation?: 'pulse' | 'wave' | 'none';
}

export const Skeleton: React.FC<SkeletonProps> = ({
  className = '',
  width,
  height,
  variant = 'rectangular',
  animation = 'pulse',
}) => {
  const baseClasses = 'bg-gray-200 dark:bg-gray-700';
  
  const animationClasses = {
    pulse: 'animate-pulse',
    wave: 'animate-shimmer',
    none: '',
  };
  
  const variantClasses = {
    text: 'rounded',
    circular: 'rounded-full',
    rectangular: '',
    rounded: 'rounded-lg',
  };
  
  const style: React.CSSProperties = {};
  if (width) style.width = typeof width === 'number' ? `${width}px` : width;
  if (height) style.height = typeof height === 'number' ? `${height}px` : height;
  
  return (
    <div
      className={`${baseClasses} ${animationClasses[animation]} ${variantClasses[variant]} ${className}`}
      style={style}
    />
  );
};

// ==================== Preset Skeletons ====================

export const SkeletonText: React.FC<{ lines?: number; className?: string }> = ({
  lines = 1,
  className = '',
}) => (
  <div className={`space-y-2 ${className}`}>
    {Array.from({ length: lines }).map((_, i) => (
      <Skeleton
        key={i}
        variant="text"
        height={16}
        width={i === lines - 1 && lines > 1 ? '60%' : '100%'}
      />
    ))}
  </div>
);

export const SkeletonAvatar: React.FC<{ size?: number; className?: string }> = ({
  size = 40,
  className = '',
}) => (
  <Skeleton
    variant="circular"
    width={size}
    height={size}
    className={className}
  />
);

export const SkeletonButton: React.FC<{ width?: string | number; className?: string }> = ({
  width = 100,
  className = '',
}) => (
  <Skeleton
    variant="rounded"
    width={width}
    height={36}
    className={className}
  />
);

export const SkeletonCard: React.FC<{ className?: string }> = ({ className = '' }) => (
  <div className={`bg-white dark:bg-gray-800 rounded-lg shadow p-4 ${className}`}>
    <div className="flex items-start space-x-4">
      <SkeletonAvatar size={48} />
      <div className="flex-1">
        <Skeleton variant="text" height={20} width="40%" className="mb-2" />
        <SkeletonText lines={2} />
      </div>
    </div>
  </div>
);

export const SkeletonTableRow: React.FC<{ columns?: number; className?: string }> = ({
  columns = 5,
  className = '',
}) => (
  <tr className={className}>
    {Array.from({ length: columns }).map((_, i) => (
      <td key={i} className="px-4 py-3">
        <Skeleton variant="text" height={16} width={i === 0 ? '80%' : '60%'} />
      </td>
    ))}
  </tr>
);

export const SkeletonTable: React.FC<{ rows?: number; columns?: number; className?: string }> = ({
  rows = 5,
  columns = 5,
  className = '',
}) => (
  <div className={`bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden ${className}`}>
    <table className="min-w-full">
      <thead className="bg-gray-50 dark:bg-gray-900">
        <tr>
          {Array.from({ length: columns }).map((_, i) => (
            <th key={i} className="px-4 py-3">
              <Skeleton variant="text" height={14} width="70%" />
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
        {Array.from({ length: rows }).map((_, i) => (
          <SkeletonTableRow key={i} columns={columns} />
        ))}
      </tbody>
    </table>
  </div>
);

export const SkeletonList: React.FC<{ items?: number; className?: string }> = ({
  items = 5,
  className = '',
}) => (
  <div className={`space-y-3 ${className}`}>
    {Array.from({ length: items }).map((_, i) => (
      <div key={i} className="flex items-center space-x-3 p-3 bg-white dark:bg-gray-800 rounded-lg">
        <SkeletonAvatar size={40} />
        <div className="flex-1">
          <Skeleton variant="text" height={16} width="50%" className="mb-1" />
          <Skeleton variant="text" height={14} width="70%" />
        </div>
        <Skeleton variant="rounded" width={60} height={24} />
      </div>
    ))}
  </div>
);

export const SkeletonStats: React.FC<{ items?: number; className?: string }> = ({
  items = 4,
  className = '',
}) => (
  <div className={`grid grid-cols-2 md:grid-cols-4 gap-4 ${className}`}>
    {Array.from({ length: items }).map((_, i) => (
      <div key={i} className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
        <Skeleton variant="text" height={14} width="60%" className="mb-2" />
        <Skeleton variant="text" height={28} width="40%" className="mb-1" />
        <Skeleton variant="text" height={12} width="50%" />
      </div>
    ))}
  </div>
);

export const SkeletonChart: React.FC<{ height?: number; className?: string }> = ({
  height = 300,
  className = '',
}) => (
  <div className={`bg-white dark:bg-gray-800 rounded-lg shadow p-4 ${className}`}>
    <div className="flex justify-between items-center mb-4">
      <Skeleton variant="text" height={20} width={150} />
      <Skeleton variant="rounded" height={32} width={100} />
    </div>
    <Skeleton variant="rounded" height={height} />
  </div>
);

export const SkeletonProduct: React.FC<{ className?: string }> = ({ className = '' }) => (
  <div className={`bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden ${className}`}>
    <Skeleton height={200} />
    <div className="p-4">
      <Skeleton variant="text" height={18} width="70%" className="mb-2" />
      <Skeleton variant="text" height={14} width="40%" className="mb-3" />
      <div className="flex justify-between items-center">
        <Skeleton variant="text" height={20} width={80} />
        <Skeleton variant="rounded" height={32} width={32} />
      </div>
    </div>
  </div>
);

export const SkeletonProductGrid: React.FC<{ items?: number; className?: string }> = ({
  items = 8,
  className = '',
}) => (
  <div className={`grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 ${className}`}>
    {Array.from({ length: items }).map((_, i) => (
      <SkeletonProduct key={i} />
    ))}
  </div>
);

export const SkeletonChat: React.FC<{ messages?: number; className?: string }> = ({
  messages = 6,
  className = '',
}) => (
  <div className={`space-y-4 p-4 ${className}`}>
    {Array.from({ length: messages }).map((_, i) => {
      const isOutbound = i % 3 === 0;
      return (
        <div
          key={i}
          className={`flex ${isOutbound ? 'justify-end' : 'justify-start'}`}
        >
          <div className={`max-w-[70%] ${isOutbound ? 'items-end' : 'items-start'}`}>
            <Skeleton
              variant="rounded"
              height={i % 2 === 0 ? 60 : 40}
              width={150 + (i % 4) * 30}
            />
          </div>
        </div>
      );
    })}
  </div>
);

export const SkeletonForm: React.FC<{ fields?: number; className?: string }> = ({
  fields = 4,
  className = '',
}) => (
  <div className={`space-y-4 ${className}`}>
    {Array.from({ length: fields }).map((_, i) => (
      <div key={i}>
        <Skeleton variant="text" height={14} width={100} className="mb-1" />
        <Skeleton variant="rounded" height={40} />
      </div>
    ))}
    <div className="flex gap-3 pt-2">
      <SkeletonButton width={100} />
      <SkeletonButton width={80} />
    </div>
  </div>
);

export default Skeleton;
