/**
 * Input Component - Modern input with animations and validation states
 * Design inspired by Linear and Stripe
 */
import React, { forwardRef, useState } from 'react';
import { cn } from '../../utils/cn';

export interface InputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'size'> {
  label?: string;
  error?: string;
  hint?: string;
  size?: 'sm' | 'md' | 'lg';
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  leftAddon?: React.ReactNode;
  rightAddon?: React.ReactNode;
}

const sizes = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-4 py-2.5 text-sm',
  lg: 'px-4 py-3 text-base',
};

export const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    {
      className,
      label,
      error,
      hint,
      size = 'md',
      leftIcon,
      rightIcon,
      leftAddon,
      rightAddon,
      disabled,
      id,
      ...props
    },
    ref
  ) => {
    const [focused, setFocused] = useState(false);
    const inputId = id || `input-${Math.random().toString(36).substr(2, 9)}`;

    return (
      <div className="space-y-1.5">
        {label && (
          <label
            htmlFor={inputId}
            className={cn(
              'block text-sm font-medium transition-colors duration-200',
              focused ? 'text-primary-600 dark:text-primary-400' : 'text-gray-700 dark:text-zinc-300',
              error && 'text-error-600 dark:text-error-400'
            )}
          >
            {label}
          </label>
        )}
        
        <div className="relative flex">
          {leftAddon && (
            <span className="inline-flex items-center px-3 rounded-l-lg border border-r-0 border-gray-300 bg-gray-50 text-gray-500 text-sm dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-400">
              {leftAddon}
            </span>
          )}
          
          <div className="relative flex-1">
            {leftIcon && (
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <span className={cn(
                  'text-gray-400 dark:text-zinc-500 transition-colors',
                  focused && 'text-primary-500 dark:text-primary-400',
                  error && 'text-error-500'
                )}>
                  {leftIcon}
                </span>
              </div>
            )}
            
            <input
              ref={ref}
              id={inputId}
              disabled={disabled}
              onFocus={(e) => {
                setFocused(true);
                props.onFocus?.(e);
              }}
              onBlur={(e) => {
                setFocused(false);
                props.onBlur?.(e);
              }}
              className={cn(
                // Base styles
                'w-full bg-white dark:bg-zinc-900',
                'border border-gray-300 dark:border-zinc-700',
                'text-gray-900 dark:text-zinc-100',
                'placeholder-gray-400 dark:placeholder-zinc-500',
                'transition-all duration-200 ease-out',
                
                // Focus styles
                'focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500',
                'dark:focus:ring-primary-500/30 dark:focus:border-primary-500',
                
                // Hover styles
                'hover:border-gray-400 dark:hover:border-zinc-600',
                
                // Error styles
                error && 'border-error-500 focus:ring-error-500/20 focus:border-error-500',
                
                // Disabled styles
                disabled && 'opacity-60 cursor-not-allowed bg-gray-50 dark:bg-zinc-800',
                
                // Size
                sizes[size],
                
                // Border radius based on addons
                leftAddon ? 'rounded-l-none' : 'rounded-l-lg',
                rightAddon ? 'rounded-r-none' : 'rounded-r-lg',
                
                // Padding for icons
                leftIcon && 'pl-10',
                rightIcon && 'pr-10',
                
                className
              )}
              {...props}
            />
            
            {rightIcon && (
              <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
                <span className={cn(
                  'text-gray-400 dark:text-zinc-500 transition-colors',
                  focused && 'text-primary-500 dark:text-primary-400',
                  error && 'text-error-500'
                )}>
                  {rightIcon}
                </span>
              </div>
            )}
          </div>
          
          {rightAddon && (
            <span className="inline-flex items-center px-3 rounded-r-lg border border-l-0 border-gray-300 bg-gray-50 text-gray-500 text-sm dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-400">
              {rightAddon}
            </span>
          )}
        </div>
        
        {(error || hint) && (
          <p
            className={cn(
              'text-xs transition-colors',
              error ? 'text-error-600 dark:text-error-400' : 'text-gray-500 dark:text-zinc-400'
            )}
          >
            {error || hint}
          </p>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';

// Search Input with animation
export interface SearchInputProps extends Omit<InputProps, 'leftIcon'> {
  onSearch?: (value: string) => void;
  loading?: boolean;
}

export const SearchInput = forwardRef<HTMLInputElement, SearchInputProps>(
  ({ className, onSearch, loading, ...props }, ref) => {
    const [value, setValue] = useState('');

    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter' && onSearch) {
        onSearch(value);
      }
    };

    return (
      <Input
        ref={ref}
        type="search"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        leftIcon={
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        }
        rightIcon={
          loading ? (
            <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : value ? (
            <button
              type="button"
              onClick={() => setValue('')}
              className="cursor-pointer hover:text-gray-600 dark:hover:text-zinc-300"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          ) : undefined
        }
        placeholder="Buscar..."
        className={className}
        {...props}
      />
    );
  }
);

SearchInput.displayName = 'SearchInput';

export default Input;
