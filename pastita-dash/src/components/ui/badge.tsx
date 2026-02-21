/**
 * Badge Component - Modern badge with variants and animations
 */
import React, { forwardRef } from 'react';
import { cn } from '../../utils/cn';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'primary' | 'outline';
  size?: 'sm' | 'md' | 'lg';
  dot?: boolean;
  pulse?: boolean;
  icon?: React.ReactNode;
}

const variants = {
  default: 'bg-gray-100 text-gray-700 dark:bg-zinc-800 dark:text-zinc-300',
  success: 'bg-success-100 text-success-700 dark:bg-success-900/40 dark:text-success-400',
  warning: 'bg-warning-100 text-warning-700 dark:bg-warning-900/40 dark:text-warning-400',
  danger: 'bg-error-100 text-error-700 dark:bg-error-900/40 dark:text-error-400',
  info: 'bg-info-100 text-info-700 dark:bg-info-900/40 dark:text-info-400',
  primary: 'bg-primary-100 text-primary-700 dark:bg-primary-900/40 dark:text-primary-400',
  outline: 'bg-transparent border border-gray-300 text-gray-700 dark:border-zinc-600 dark:text-zinc-300',
};

const dotColors = {
  default: 'bg-gray-500',
  success: 'bg-success-500',
  warning: 'bg-warning-500',
  danger: 'bg-error-500',
  info: 'bg-info-500',
  primary: 'bg-primary-500',
  outline: 'bg-gray-500',
};

const sizes = {
  sm: 'px-1.5 py-0.5 text-xs',
  md: 'px-2.5 py-1 text-xs',
  lg: 'px-3 py-1.5 text-sm',
};

export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  (
    {
      className,
      variant = 'default',
      size = 'md',
      dot = false,
      pulse = false,
      icon,
      children,
      ...props
    },
    ref
  ) => {
    return (
      <span
        ref={ref}
        className={cn(
          'inline-flex items-center gap-1.5 font-medium rounded-full',
          'transition-all duration-200',
          variants[variant],
          sizes[size],
          className
        )}
        {...props}
      >
        {dot && (
          <span className="relative flex h-2 w-2">
            {pulse && (
              <span
                className={cn(
                  'absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping',
                  dotColors[variant]
                )}
              />
            )}
            <span
              className={cn(
                'relative inline-flex rounded-full h-2 w-2',
                dotColors[variant]
              )}
            />
          </span>
        )}
        {icon && <span className="shrink-0">{icon}</span>}
        {children}
      </span>
    );
  }
);

Badge.displayName = 'Badge';

// Status Badge with predefined statuses
export interface StatusBadgeProps extends Omit<BadgeProps, 'variant'> {
  status: 'online' | 'offline' | 'away' | 'busy' | 'pending' | 'completed' | 'cancelled';
}

const statusConfig: Record<StatusBadgeProps['status'], { variant: BadgeProps['variant']; label: string }> = {
  online: { variant: 'success', label: 'Online' },
  offline: { variant: 'default', label: 'Offline' },
  away: { variant: 'warning', label: 'Ausente' },
  busy: { variant: 'danger', label: 'Ocupado' },
  pending: { variant: 'warning', label: 'Pendente' },
  completed: { variant: 'success', label: 'Concluído' },
  cancelled: { variant: 'danger', label: 'Cancelado' },
};

export const StatusBadge = forwardRef<HTMLSpanElement, StatusBadgeProps>(
  ({ status, children, ...props }, ref) => {
    const config = statusConfig[status];
    return (
      <Badge ref={ref} variant={config.variant} dot pulse={status === 'online'} {...props}>
        {children || config.label}
      </Badge>
    );
  }
);

StatusBadge.displayName = 'StatusBadge';

// Count Badge for notifications
export interface CountBadgeProps extends Omit<BadgeProps, 'children'> {
  count: number;
  max?: number;
}

export const CountBadge = forwardRef<HTMLSpanElement, CountBadgeProps>(
  ({ count, max = 99, ...props }, ref) => {
    const displayCount = count > max ? `${max}+` : count;
    
    if (count <= 0) return null;
    
    return (
      <Badge ref={ref} size="sm" variant="danger" {...props}>
        {displayCount}
      </Badge>
    );
  }
);

CountBadge.displayName = 'CountBadge';

export default Badge;
