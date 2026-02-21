import React from 'react';
import { cn } from '../../utils/cn';

interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export const Switch: React.FC<SwitchProps> = ({
  checked,
  onChange,
  disabled = false,
  size = 'md',
  className = '',
}) => {
  const sizeClasses = {
    sm: 'w-8 h-4',
    md: 'w-11 h-6',
    lg: 'w-14 h-8',
  };

  const thumbSizeClasses = {
    sm: 'w-3 h-3 translate-x-0.5',
    md: 'w-4 h-4 translate-x-0.5',
    lg: 'w-6 h-6 translate-x-1',
  };

  const thumbCheckedClasses = {
    sm: 'translate-x-4',
    md: 'translate-x-5',
    lg: 'translate-x-6',
  };

  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        'relative inline-flex items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
        checked ? 'bg-primary-500' : 'bg-gray-300 dark:bg-gray-600',
        disabled && 'opacity-50 cursor-not-allowed',
        sizeClasses[size],
        className
      )}
    >
      <span
        className={cn(
          'inline-block rounded-full bg-white transition-transform duration-200 ease-in-out',
          thumbSizeClasses[size],
          checked && thumbCheckedClasses[size]
        )}
      />
    </button>
  );
};
