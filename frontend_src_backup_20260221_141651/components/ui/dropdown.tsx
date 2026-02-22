/**
 * Dropdown Component - Modern animated dropdown menu
 * Design inspired by Linear, Vercel, and Raycast
 */
import React, { useState, useRef, useEffect, useCallback } from 'react';
import { cn } from '../../utils/cn';
import { ChevronDownIcon, ChevronRightIcon } from '@heroicons/react/24/outline';

export interface DropdownItem {
  id: string;
  label: string;
  icon?: React.ReactNode;
  description?: string;
  disabled?: boolean;
  danger?: boolean;
  divider?: boolean;
  children?: DropdownItem[];
  onClick?: () => void;
}

export interface DropdownProps {
  trigger: React.ReactNode;
  items: DropdownItem[];
  align?: 'left' | 'right' | 'center';
  width?: 'auto' | 'trigger' | number;
  className?: string;
}

export const Dropdown: React.FC<DropdownProps> = ({
  trigger,
  items,
  align = 'left',
  width = 'auto',
  className,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [activeSubmenu, setActiveSubmenu] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLDivElement>(null);

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
        setActiveSubmenu(null);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Close on Escape
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
        setActiveSubmenu(null);
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, []);

  const handleItemClick = useCallback((item: DropdownItem) => {
    if (item.disabled) return;
    if (item.children) {
      setActiveSubmenu(activeSubmenu === item.id ? null : item.id);
      return;
    }
    item.onClick?.();
    setIsOpen(false);
    setActiveSubmenu(null);
  }, [activeSubmenu]);

  const alignStyles = {
    left: 'left-0',
    right: 'right-0',
    center: 'left-1/2 -translate-x-1/2',
  };

  const getWidth = () => {
    if (width === 'auto') return 'min-w-[200px]';
    if (width === 'trigger') return 'min-w-full';
    return `w-[${width}px]`;
  };

  const renderItem = (item: DropdownItem, isSubmenuItem = false) => {
    if (item.divider) {
      return (
        <div
          key={item.id}
          className="my-1 h-px bg-gray-200 dark:bg-zinc-700"
        />
      );
    }

    const hasChildren = item.children && item.children.length > 0;
    const isSubmenuOpen = activeSubmenu === item.id;

    return (
      <div key={item.id} className="relative">
        <button
          onClick={() => handleItemClick(item)}
          onMouseEnter={() => hasChildren && setActiveSubmenu(item.id)}
          disabled={item.disabled}
          className={cn(
            // Base
            'w-full flex items-center gap-3 px-3 py-2 text-sm rounded-lg',
            'transition-all duration-150 ease-out',
            // States
            !item.disabled && !item.danger && 'hover:bg-gray-100 dark:hover:bg-zinc-800',
            !item.disabled && item.danger && 'hover:bg-red-50 dark:hover:bg-red-950/30 text-red-600 dark:text-red-400',
            item.disabled && 'opacity-50 cursor-not-allowed',
            // Active submenu
            isSubmenuOpen && 'bg-gray-100 dark:bg-zinc-800'
          )}
        >
          {/* Icon */}
          {item.icon && (
            <span className={cn(
              'shrink-0',
              item.danger
                ? 'text-red-500'
                : 'text-gray-500 dark:text-zinc-400'
            )}>
              {item.icon}
            </span>
          )}

          {/* Content */}
          <div className="flex-1 text-left">
            <span className={cn(
              'block font-medium',
              item.danger
                ? 'text-red-600 dark:text-red-400'
                : 'text-gray-900 dark:text-white'
            )}>
              {item.label}
            </span>
            {item.description && (
              <span className="block text-xs text-gray-500 dark:text-zinc-400 mt-0.5">
                {item.description}
              </span>
            )}
          </div>

          {/* Submenu arrow */}
          {hasChildren && (
            <ChevronRightIcon className="w-4 h-4 text-gray-400 dark:text-zinc-500" />
          )}
        </button>

        {/* Submenu */}
        {hasChildren && isSubmenuOpen && (
          <div
            className={cn(
              'absolute top-0 left-full ml-1 z-10',
              'bg-white dark:bg-zinc-900 rounded-xl shadow-xl border border-gray-200 dark:border-zinc-700',
              'min-w-[180px] py-2 px-1',
              'animate-in fade-in slide-in-from-left-1 duration-200'
            )}
          >
            {item.children!.map((child) => renderItem(child, true))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div ref={dropdownRef} className={cn('relative inline-block', className)}>
      {/* Trigger */}
      <div
        ref={triggerRef}
        onClick={() => setIsOpen(!isOpen)}
        className="cursor-pointer"
      >
        {trigger}
      </div>

      {/* Dropdown Menu */}
      {isOpen && (
        <div
          className={cn(
            'absolute z-50 mt-2',
            'bg-white dark:bg-zinc-900 rounded-xl shadow-xl',
            'border border-gray-200 dark:border-zinc-700',
            'py-2 px-1',
            // Animation
            'animate-in fade-in slide-in-from-top-2 duration-200',
            // Alignment
            alignStyles[align],
            // Width
            getWidth()
          )}
        >
          {items.map((item) => renderItem(item))}
        </div>
      )}
    </div>
  );
};

// Dropdown Trigger Button Component
export interface DropdownButtonProps {
  children: React.ReactNode;
  className?: string;
}

export const DropdownButton: React.FC<DropdownButtonProps> = ({
  children,
  className,
}) => {
  return (
    <button
      className={cn(
        'inline-flex items-center gap-2 px-4 py-2',
        'text-sm font-medium text-gray-700 dark:text-zinc-200',
        'bg-white dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700',
        'rounded-lg shadow-sm',
        'hover:bg-gray-50 dark:hover:bg-zinc-700',
        'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
        'transition-all duration-150',
        className
      )}
    >
      {children}
      <ChevronDownIcon className="w-4 h-4" />
    </button>
  );
};

export default Dropdown;
