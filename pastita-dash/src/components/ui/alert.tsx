/**
 * Alert Component
 */
import React, { forwardRef } from 'react';
import { cn } from '../../utils/cn';

const variants = {
  default: 'bg-gray-100 text-gray-800 dark:bg-zinc-800 dark:text-zinc-100',
  destructive: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400 border-red-200 dark:border-red-800',
  warning: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  success: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
};

export interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: keyof typeof variants;
}

export const Alert = forwardRef<HTMLDivElement, AlertProps>(
  ({ className, variant = 'default', children, ...props }, ref) => (
    <div
      ref={ref}
      role="alert"
      className={cn(
        'relative w-full rounded-lg border p-4',
        '[&>svg~*]:pl-7 [&>svg+div]:translate-y-[-3px]',
        '[&>svg]:absolute [&>svg]:left-4 [&>svg]:top-4 [&>svg]:text-current',
        variants[variant],
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
);

Alert.displayName = 'Alert';

export interface AlertDescriptionProps extends React.HTMLAttributes<HTMLParagraphElement> {}

export const AlertDescription = forwardRef<HTMLParagraphElement, AlertDescriptionProps>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn('text-sm [&_p]:leading-relaxed', className)}
      {...props}
    />
  )
);

AlertDescription.displayName = 'AlertDescription';

export interface AlertTitleProps extends React.HTMLAttributes<HTMLHeadingElement> {}

export const AlertTitle = forwardRef<HTMLHeadingElement, AlertTitleProps>(
  ({ className, ...props }, ref) => (
    <h5
      ref={ref}
      className={cn('mb-1 font-medium leading-none tracking-tight', className)}
      {...props}
    />
  )
);

AlertTitle.displayName = 'AlertTitle';

export default Alert;
