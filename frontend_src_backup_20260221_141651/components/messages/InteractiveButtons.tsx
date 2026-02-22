import React from 'react';
import { cn } from '../../utils/cn';

interface InteractiveButton {
  id: string;
  title: string;
}

interface InteractiveButtonsProps {
  body: string;
  buttons: InteractiveButton[];
  onButtonClick?: (buttonId: string, buttonTitle: string) => void;
  disabled?: boolean;
  className?: string;
}

/**
 * Componente para renderizar botões interativos do WhatsApp
 * Usado quando o bot envia mensagens com ações rápidas
 */
export const InteractiveButtons: React.FC<InteractiveButtonsProps> = ({
  body,
  buttons,
  onButtonClick,
  disabled = false,
  className,
}) => {
  const handleClick = (button: InteractiveButton) => {
    if (disabled) return;
    onButtonClick?.(button.id, button.title);
  };

  return (
    <div className={cn('bg-white dark:bg-zinc-800 rounded-lg overflow-hidden', className)}>
      {/* Body text */}
      <div className="p-4 text-sm text-zinc-800 dark:text-zinc-200 whitespace-pre-wrap">
        {body}
      </div>

      {/* Divider */}
      <div className="border-t border-zinc-200 dark:border-zinc-700" />

      {/* Buttons */}
      <div className="flex flex-col">
        {buttons.map((button, index) => (
          <React.Fragment key={button.id}>
            <button
              onClick={() => handleClick(button)}
              disabled={disabled}
              className={cn(
                'w-full py-3 px-4 text-center text-sm font-medium',
                'text-blue-600 dark:text-blue-400',
                'hover:bg-zinc-50 dark:hover:bg-zinc-700/50',
                'active:bg-zinc-100 dark:active:bg-zinc-700',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                'transition-colors duration-150'
              )}
            >
              {button.title}
            </button>
            {index < buttons.length - 1 && (
              <div className="border-t border-zinc-200 dark:border-zinc-700" />
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
};

export default InteractiveButtons;
