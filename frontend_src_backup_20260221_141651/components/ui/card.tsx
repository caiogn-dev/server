/** * Card Component - Modern card with CVA variants and glass morphism * Design inspired by Linear and Vercel */ import React, { forwardRef } from 'react'; import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '../../utils/cn';

// CVA Configuration for card variants
const cardVariants = cva(
  // Base styles
  'rounded-xl transition-all duration-300 ease-out',
  {
    variants: {
      variant: {
        default: 'bg-white dark:bg-zinc-900 border border-gray-100 dark:border-zinc-800 shadow-sm',
        glass: 'bg-white/70 dark:bg-zinc-900/70 backdrop-blur-xl backdrop-saturate-150 border border-white/20 dark:border-zinc-700/50 shadow-glass',
        bordered: 'bg-white dark:bg-zinc-900 border-2 border-gray-200 dark:border-zinc-700',
        elevated: 'bg-white dark:bg-zinc-900 border border-gray-100 dark:border-zinc-800 shadow-lg shadow-gray-200/50 dark:shadow-black/20',
      },
      padding: {
        none: '',
        sm: 'p-3',
        md: 'p-4 md:p-6',
        lg: 'p-6 md:p-8',
      },
      hover: {
        true: 'hover:shadow-lg hover:-translate-y-1 hover:border-gray-200 dark:hover:border-zinc-700 cursor-pointer',
        false: '',
      },
    },
    defaultVariants: {
      variant: 'default',
      padding: 'md',
      hover: false,
    },
  }
);

export interface CardProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof cardVariants> {}

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ className, variant, padding, hover, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(cardVariants({ variant, padding, hover }), className)}
        {...props}
      >
        {children}
      </div>
    );
  }
);

Card.displayName = 'Card';

// Card Header with CVA
const cardHeaderVariants = cva(
  'flex items-start justify-between gap-4 pb-4 border-b border-gray-100 dark:border-zinc-800 mb-4'
);

export interface CardHeaderProps extends React.HTMLAttributes<HTMLDivElement> {
  title?: string;
  subtitle?: string;
  action?: React.ReactNode;
}

export const CardHeader = forwardRef<HTMLDivElement, CardHeaderProps>(
  ({ className, title, subtitle, action, children, ...props }, ref) => {
    return (
      <div ref={ref} className={cn(cardHeaderVariants(), className)} {...props}>
        {(title || subtitle) && (
          <div className="space-y-1">
            {title && (
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white leading-tight">
                {title}
              </h3>
            )}
            {subtitle && (
              <p className="text-sm text-gray-500 dark:text-zinc-400">
                {subtitle}
              </p>
            )}
          </div>
        )}
        {children}
        {action && <div className="shrink-0">{action}</div>}
      </div>
    );
  }
);

CardHeader.displayName = 'CardHeader';

// Card Content
export const CardContent = forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('', className)} {...props} />
  )
);

CardContent.displayName = 'CardContent';

// Card Footer
const cardFooterVariants = cva(
  'flex items-center justify-end gap-2 pt-4 border-t border-gray-100 dark:border-zinc-800 mt-4'
);

export const CardFooter = forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn(cardFooterVariants(), className)} {...props} />
  )
);

CardFooter.displayName = 'CardFooter';

// Stat Card - For dashboard metrics with improved CVA
const trendIndicatorVariants = cva('inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium', {
  variants: {
    changeType: {
      positive: 'text-success-600 bg-success-50 dark:text-success-400 dark:bg-success-900/30',
      negative: 'text-error-600 bg-error-50 dark:text-error-400 dark:bg-error-900/30',
      neutral: 'text-gray-600 bg-gray-100 dark:text-zinc-400 dark:bg-zinc-800',
    },
  },
  defaultVariants: {
    changeType: 'neutral',
  },
});

export interface StatCardProps extends React.HTMLAttributes<HTMLDivElement> {
  title: string;
  value: string | number;
  change?: string;
  changeType?: 'positive' | 'negative' | 'neutral';
  icon?: React.ReactNode;
  trend?: 'up' | 'down';
  loading?: boolean;
}

const TrendUpIcon = () => (
  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
  </svg>
);

const TrendDownIcon = () => (
  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
  </svg>
);

export const StatCard = forwardRef<HTMLDivElement, StatCardProps>(
  (
    { className, title, value, change, changeType = 'neutral', icon, trend, loading = false, ...props },
    ref
  ) => {
    const TrendIcon = trend === 'up' ? TrendUpIcon : trend === 'down' ? TrendDownIcon : null;

    if (loading) {
      return (
        <Card ref={ref} className={cn('animate-pulse', className)} {...props}>
          <div className="flex items-center justify-between gap-3">
            <div className="flex-1 space-y-2">
              <div className="h-4 bg-gray-200 dark:bg-zinc-700 rounded w-24" />
              <div className="h-8 bg-gray-200 dark:bg-zinc-700 rounded w-32" />
            </div>
            <div className="w-12 h-12 bg-gray-200 dark:bg-zinc-700 rounded-xl" />
          </div>
        </Card>
      );
    }

    return (
      <Card ref={ref} hover className={cn('group', className)} {...props}>
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1 space-y-1">
            <p className="text-xs md:text-sm font-medium text-gray-500 dark:text-zinc-400 truncate">
              {title}
            </p>
            <p className="text-xl md:text-2xl lg:text-3xl font-bold text-gray-900 dark:text-white truncate transition-transform group-hover:scale-[1.02]">
              {value}
            </p>
            {change && (
              <span className={cn(trendIndicatorVariants({ changeType }))}>
                {TrendIcon && <TrendIcon />}
                {change}
              </span>
            )}
          </div>
          {icon && (
            <div className="p-2.5 md:p-3 bg-primary-50 dark:bg-primary-900/30 rounded-xl text-primary-600 dark:text-primary-400 shrink-0 transition-transform group-hover:scale-110 group-hover:rotate-3">
              {icon}
            </div>
          )}
        </div>
      </Card>
    );
  }
);

StatCard.displayName = 'StatCard';

// Utility exports
export { cardVariants, cardHeaderVariants, cardFooterVariants, trendIndicatorVariants };
export type { VariantProps };

export default Card;
