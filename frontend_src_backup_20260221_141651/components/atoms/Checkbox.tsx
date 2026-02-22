import React from 'react';
import { cn } from '../../utils/cn';
import { CheckIcon } from '@heroicons/react/24/outline';

export interface CheckboxProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  ({ label, error, className, ...props }, ref) => {
    return (
      <div className="flex items-start">
        <div className="flex items-center h-5">
          <input
            type="checkbox"
            ref={ref}
            className={cn(
              'w-4 h-4 rounded border appearance-none cursor-pointer',
              'checked:bg-primary-600 checked:border-primary-600',
              'focus:ring-2 focus:ring-primary-500 focus:outline-none',
              error
                ? 'border-red-500'
                : 'border-zinc-300 dark:border-zinc-600',
              className
            )}
            {...props}
          />
        </div>
        {label && (
          <label className="ml-2 text-sm text-zinc-700 dark:text-zinc-300 cursor-pointer">
            {label}
          </label>
        )}
      </div>
    );
  }
);

Checkbox.displayName = 'Checkbox';
