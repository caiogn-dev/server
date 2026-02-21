/** * Button Component - Modern, animated button with CVA variants * Design inspired by Linear, Vercel, and Raycast */ import React, { forwardRef } from 'react'; import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '../../utils/cn';

// CVA Configuration for button variants
const buttonVariants = cva(
  // Base styles
  'inline-flex items-center justify-center font-medium transition-all duration-200 ease-out focus:outline-none disabled:opacity-60 disabled:cursor-not-allowed disabled:transform-none',
  {
    variants: {
      variant: {
        primary: 'bg-gradient-to-b from-primary-500 to-primary-600 text-white shadow-sm hover:from-primary-600 hover:to-primary-700 hover:shadow-md hover:-translate-y-0.5 active:from-primary-700 active:to-primary-800 active:translate-y-0 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:from-primary-600 dark:to-primary-700 dark:hover:from-primary-500 dark:hover:to-primary-600',
        secondary: 'bg-gray-100 text-gray-800 border border-gray-200 hover:bg-gray-200 hover:border-gray-300 hover:-translate-y-0.5 active:bg-gray-300 active:translate-y-0 focus-visible:ring-2 focus-visible:ring-gray-500 focus-visible:ring-offset-2 dark:bg-zinc-800 dark:text-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-700 dark:hover:border-zinc-600',
        outline: 'bg-transparent text-primary-600 border-2 border-primary-500 hover:bg-primary-50 hover:-translate-y-0.5 active:bg-primary-100 active:translate-y-0 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:text-primary-400 dark:border-primary-500 dark:hover:bg-primary-950',
        ghost: 'bg-transparent text-gray-600 hover:bg-gray-100 hover:text-gray-900 active:bg-gray-200 focus-visible:ring-2 focus-visible:ring-gray-500 focus-visible:ring-offset-2 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100',
        danger: 'bg-gradient-to-b from-error-500 to-error-600 text-white shadow-sm hover:from-error-600 hover:to-error-700 hover:shadow-md hover:-translate-y-0.5 active:from-error-700 active:to-error-800 active:translate-y-0 focus-visible:ring-2 focus-visible:ring-error-500 focus-visible:ring-offset-2',
        success: 'bg-gradient-to-b from-success-500 to-success-600 text-white shadow-sm hover:from-success-600 hover:to-success-700 hover:shadow-md hover:-translate-y-0.5 active:from-success-700 active:to-success-800 active:translate-y-0 focus-visible:ring-2 focus-visible:ring-success-500 focus-visible:ring-offset-2',
      },
      size: {
        xs: 'px-2 py-1 text-xs gap-1 rounded-md',
        sm: 'px-3 py-1.5 text-sm gap-1.5 rounded-lg',
        md: 'px-4 py-2 text-sm gap-2 rounded-lg',
        lg: 'px-5 py-2.5 text-base gap-2 rounded-lg',
        xl: 'px-6 py-3 text-lg gap-2.5 rounded-xl',
      },
    },
    defaultVariants: {
      variant: 'primary',
      size: 'md',
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  loading?: boolean;
  icon?: React.ReactNode;
  iconPosition?: 'left' | 'right';
  fullWidth?: boolean;
}

const LoadingSpinner = ({ className }: { className?: string }) => (
  <svg
    className={cn('animate-spin', className)}
    xmlns="http://www.w3.org/2000/svg"
    fill="none"
    viewBox="0 0 24 24"
  >
    <circle
      className="opacity-25"
      cx="12"
      cy="12"
      r="10"
      stroke="currentColor"
      strokeWidth="4"
    />
    <path
      className="opacity-75"
      fill="currentColor"
      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
    />
  </svg>
);

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant,
      size,
      loading = false,
      icon,
      iconPosition = 'left',
      fullWidth = false,
      disabled,
      children,
      ...props
    },
    ref
  ) => {
    const isDisabled = disabled || loading;

    return (
      <button
        ref={ref}
        disabled={isDisabled}
        className={cn(
          buttonVariants({ variant, size }),
          fullWidth && 'w-full',
          className
        )}
        {...props}
      >
        {loading ? (
          <>
            <LoadingSpinner className="w-4 h-4" />
            <span className="ml-2">{children}</span>
          </>
        ) : (
          <>
            {icon && iconPosition === 'left' && (
              <span className="shrink-0">{icon}</span>
            )}
            {children}
            {icon && iconPosition === 'right' && (
              <span className="shrink-0">{icon}</span>
            )}
          </>
        )}
      </button>
    );
  }
);

Button.displayName = 'Button';

// Utility type export for external use
export type { VariantProps };
export { buttonVariants };

export default Button;
