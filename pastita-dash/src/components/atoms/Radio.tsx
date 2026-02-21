import React from 'react';
import { cn } from '../../utils/cn';

export interface RadioOption {
  value: string;
  label: string;
}

export interface RadioGroupProps {
  name: string;
  options: RadioOption[];
  value?: string;
  onChange?: (value: string) => void;
  label?: string;
  error?: string;
}

export function RadioGroup({
  name,
  options,
  value,
  onChange,
  label,
  error,
}: RadioGroupProps) {
  return (
    <div>
      {label && (
        <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
          {label}
        </label>
      )}
      <div className="space-y-2">
        {options.map((option) => (
          <label
            key={option.value}
            className="flex items-center cursor-pointer"
          >
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={value === option.value}
              onChange={(e) => onChange?.(e.target.value)}
              className={cn(
                'w-4 h-4 border-2 appearance-none rounded-full cursor-pointer',
                'checked:border-primary-600 checked:bg-primary-600',
                'focus:ring-2 focus:ring-primary-500 focus:outline-none',
                error ? 'border-red-500' : 'border-zinc-300 dark:border-zinc-600'
              )}
            />
            <span className="ml-2 text-sm text-zinc-700 dark:text-zinc-300">
              {option.label}
            </span>
          </label>
        ))}
      </div>
      {error && (
        <p className="mt-1 text-sm text-red-500">{error}</p>
      )}
    </div>
  );
}
