/**
 * Skeleton loading component
 * Provides visual feedback while content is loading
 */
import React from 'react';
import { cn } from '../../utils/cn';

interface SkeletonProps {
  className?: string;
  variant?: 'default' | 'card' | 'text' | 'avatar' | 'image';
  count?: number;
}

const variantStyles = {
  default: 'h-4 w-full',
  card: 'h-32 w-full rounded-xl',
  text: 'h-4 w-full rounded',
  avatar: 'h-12 w-12 rounded-full',
  image: 'aspect-video w-full rounded-xl',
};

export const Skeleton: React.FC<SkeletonProps> = ({
  className,
  variant = 'default',
  count = 1,
}) => {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className={cn(
            'animate-shimmer bg-gradient-to-r from-gray-200 via-gray-100 to-gray-200 dark:from-zinc-800 dark:via-zinc-700 dark:to-zinc-800 bg-[length:200%_100%]',
            variantStyles[variant],
            className
          )}
          style={{
            animationDelay: `${i * 0.1}s`,
          }}
        />
      ))}
    </div>
  );
};

// Table skeleton with multiple rows
export const TableSkeleton: React.FC<{ rows?: number; columns?: number }> = ({
  rows = 5,
  columns = 4,
}) => {
  return (
    <div className="space-y-2">
      {/* Header */}
      <div className="flex gap-4 pb-4 border-b border-gray-200 dark:border-zinc-800">
        {Array.from({ length: columns }).map((_, i) => (
          <Skeleton key={i} variant="text" className="flex-1 h-6" />
        ))}
      </div>
      {/* Rows */}
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="flex gap-4 py-3 border-b border-gray-100 dark:border-zinc-800"
        >
          {Array.from({ length: columns }).map((_, j) => (
            <Skeleton key={j} variant="text" className="flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
};

// Card skeleton for cards/sections
export const CardSkeleton: React.FC<{
  hasHeader?: boolean;
  hasImage?: boolean;
  lines?: number;
}>

= ({ hasHeader = true, hasImage = false, lines = 3 }) => {
  return (
    <div className="space-y-4 p-6 rounded-xl border border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900">
      {hasHeader && <Skeleton variant="text" className="w-1/3 h-6" />}
      {hasImage && <Skeleton variant="card" />}
      <div className="space-y-2">
        {Array.from({ length: lines }).map((_, i) => (
          <Skeleton key={i} variant="text" />
        ))}
      </div>
    </div>
  );
};

// Stats cards skeleton
export const StatsSkeleton: React.FC<{ count?: number }> = ({ count = 4 }) => {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <CardSkeleton key={i} hasHeader={false} lines={2} />
      ))}
    </div>
  );
};

export default Skeleton;
