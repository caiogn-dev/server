import React, { useState } from 'react';
import { ChevronDownIcon, ChevronUpIcon } from '@heroicons/react/24/outline';
import { cn } from '../../utils/cn';

interface InteractiveListRow {
  id: string;
  title: string;
  description?: string;
}

interface InteractiveListSection {
  title: string;
  rows: InteractiveListRow[];
}

interface InteractiveListProps {
  body: string;
  button: string;
  sections: InteractiveListSection[];
  onRowSelect?: (rowId: string, rowTitle: string) => void;
  disabled?: boolean;
  className?: string;
}

/**
 * Componente para renderizar lista interativa do WhatsApp
 * Usado quando o bot envia catálogo ou opções em lista
 */
export const InteractiveList: React.FC<InteractiveListProps> = ({
  body,
  button,
  sections,
  onRowSelect,
  disabled = false,
  className,
}) => {
  const [isOpen, setIsOpen] = useState(false);

  const handleRowClick = (row: InteractiveListRow) => {
    if (disabled) return;
    onRowSelect?.(row.id, row.title);
    setIsOpen(false);
  };

  const totalRows = sections.reduce((acc, section) => acc + section.rows.length, 0);

  return (
    <div className={cn('bg-white dark:bg-zinc-800 rounded-lg overflow-hidden', className)}>
      {/* Body text */}
      <div className="p-4 text-sm text-zinc-800 dark:text-zinc-200 whitespace-pre-wrap">
        {body}
      </div>

      {/* Divider */}
      <div className="border-t border-zinc-200 dark:border-zinc-700" />

      {/* Button to open list */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        disabled={disabled}
        className={cn(
          'w-full py-3 px-4 flex items-center justify-between',
          'text-sm font-medium text-blue-600 dark:text-blue-400',
          'hover:bg-zinc-50 dark:hover:bg-zinc-700/50',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          'transition-colors duration-150'
        )}
      >
        <span>{button}</span>
        {isOpen ? (
          <ChevronUpIcon className="w-5 h-5" />
        ) : (
          <ChevronDownIcon className="w-5 h-5" />
        )}
      </button>

      {/* Expandable list */}
      {isOpen && (
        <div className="border-t border-zinc-200 dark:border-zinc-700 max-h-80 overflow-y-auto">
          {sections.map((section, sectionIndex) => (
            <div key={sectionIndex}>
              {/* Section title */}
              <div className="px-4 py-2 bg-zinc-100 dark:bg-zinc-700/50 text-xs font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider">
                {section.title}
              </div>

              {/* Section rows */}
              <div className="flex flex-col">
                {section.rows.map((row, rowIndex) => (
                  <React.Fragment key={row.id}>
                    <button
                      onClick={() => handleRowClick(row)}
                      disabled={disabled}
                      className={cn(
                        'w-full py-3 px-4 text-left',
                        'hover:bg-zinc-50 dark:hover:bg-zinc-700/50',
                        'active:bg-zinc-100 dark:active:bg-zinc-700',
                        'disabled:opacity-50 disabled:cursor-not-allowed',
                        'transition-colors duration-150'
                      )}
                    >
                      <div className="text-sm font-medium text-zinc-800 dark:text-zinc-200">
                        {row.title}
                      </div>
                      {row.description && (
                        <div className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">
                          {row.description}
                        </div>
                      )}
                    </button>
                    {rowIndex < section.rows.length - 1 && (
                      <div className="border-t border-zinc-100 dark:border-zinc-700 ml-4" />
                    )}
                  </React.Fragment>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Footer with count */}
      <div className="px-4 py-2 bg-zinc-50 dark:bg-zinc-700/30 text-xs text-zinc-500 dark:text-zinc-400 border-t border-zinc-200 dark:border-zinc-700">
        {totalRows} opções disponíveis
      </div>
    </div>
  );
};

export default InteractiveList;
