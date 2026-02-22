/**
 * Modal Component - Modern modal with animations and backdrop blur
 */
import React, { forwardRef, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '../../utils/cn';

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
  className?: string;
  size?: 'sm' | 'md' | 'lg' | 'xl' | 'full';
  closeOnOverlayClick?: boolean;
  closeOnEscape?: boolean;
  showCloseButton?: boolean;
}

const sizes = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  full: 'max-w-4xl',
};

export const Modal = forwardRef<HTMLDivElement, ModalProps>(
  (
    {
      open,
      onClose,
      children,
      className,
      size = 'md',
      closeOnOverlayClick = true,
      closeOnEscape = true,
      showCloseButton = true,
    },
    ref
  ) => {
    const overlayRef = useRef<HTMLDivElement>(null);

    // Handle escape key
    useEffect(() => {
      if (!closeOnEscape) return;

      const handleEscape = (e: KeyboardEvent) => {
        if (e.key === 'Escape') onClose();
      };

      if (open) {
        document.addEventListener('keydown', handleEscape);
        document.body.style.overflow = 'hidden';
      }

      return () => {
        document.removeEventListener('keydown', handleEscape);
        document.body.style.overflow = '';
      };
    }, [open, onClose, closeOnEscape]);

    // Handle overlay click
    const handleOverlayClick = (e: React.MouseEvent) => {
      if (closeOnOverlayClick && e.target === overlayRef.current) {
        onClose();
      }
    };

    if (!open) return null;

    return createPortal(
      <div
        ref={overlayRef}
        onClick={handleOverlayClick}
        className={cn(
          'fixed inset-0 z-50',
          'flex items-center justify-center p-4',
          'bg-black/60 backdrop-blur-sm',
          'animate-fade-in'
        )}
      >
        <div
          ref={ref}
          className={cn(
            'relative w-full',
            'bg-white dark:bg-zinc-900',
            'rounded-2xl shadow-2xl',
            'border border-gray-200 dark:border-zinc-800',
            'animate-scale-in',
            'max-h-[90vh] overflow-hidden flex flex-col',
            sizes[size],
            className
          )}
        >
          {showCloseButton && (
            <button
              onClick={onClose}
              className={cn(
                'absolute top-4 right-4 z-10',
                'p-2 rounded-lg',
                'text-gray-400 hover:text-gray-600 dark:text-zinc-500 dark:hover:text-zinc-300',
                'hover:bg-gray-100 dark:hover:bg-zinc-800',
                'transition-colors'
              )}
              aria-label="Fechar"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
          {children}
        </div>
      </div>,
      document.body
    );
  }
);

Modal.displayName = 'Modal';

// Modal Header
export interface ModalHeaderProps extends React.HTMLAttributes<HTMLDivElement> {
  title?: string;
  subtitle?: string;
}

export const ModalHeader = forwardRef<HTMLDivElement, ModalHeaderProps>(
  ({ className, title, subtitle, children, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'px-6 py-4 border-b border-gray-200 dark:border-zinc-800',
        className
      )}
      {...props}
    >
      {(title || subtitle) && (
        <div className="pr-8">
          {title && (
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              {title}
            </h2>
          )}
          {subtitle && (
            <p className="text-sm text-gray-500 dark:text-zinc-400 mt-1">
              {subtitle}
            </p>
          )}
        </div>
      )}
      {children}
    </div>
  )
);

ModalHeader.displayName = 'ModalHeader';

// Modal Body
export const ModalBody = forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn('flex-1 overflow-y-auto px-6 py-4', className)}
      {...props}
    />
  )
);

ModalBody.displayName = 'ModalBody';

// Modal Footer
export const ModalFooter = forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'flex items-center justify-end gap-3',
        'px-6 py-4 border-t border-gray-200 dark:border-zinc-800',
        'bg-gray-50 dark:bg-zinc-900/50',
        className
      )}
      {...props}
    />
  )
);

ModalFooter.displayName = 'ModalFooter';

// Confirm Modal
export interface ConfirmModalProps extends Omit<ModalProps, 'children'> {
  title: string;
  description?: string;
  confirmText?: string;
  cancelText?: string;
  variant?: 'danger' | 'warning' | 'default';
  loading?: boolean;
  onConfirm: () => void;
  icon?: React.ReactNode;
}

const variantStyles = {
  danger: {
    icon: 'text-error-500 bg-error-100 dark:bg-error-900/30',
    button: 'bg-error-600 hover:bg-error-700 text-white',
  },
  warning: {
    icon: 'text-warning-500 bg-warning-100 dark:bg-warning-900/30',
    button: 'bg-warning-600 hover:bg-warning-700 text-white',
  },
  default: {
    icon: 'text-primary-500 bg-primary-100 dark:bg-primary-900/30',
    button: 'bg-primary-600 hover:bg-primary-700 text-white',
  },
};

export const ConfirmModal = forwardRef<HTMLDivElement, ConfirmModalProps>(
  (
    {
      title,
      description,
      confirmText = 'Confirmar',
      cancelText = 'Cancelar',
      variant = 'default',
      loading = false,
      onConfirm,
      onClose,
      icon,
      ...props
    },
    ref
  ) => {
    const styles = variantStyles[variant];

    const defaultIcon = variant === 'danger' ? (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    ) : variant === 'warning' ? (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ) : (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    );

    return (
      <Modal ref={ref} onClose={onClose} size="sm" showCloseButton={false} {...props}>
        <div className="p-6 text-center">
          <div className={cn('inline-flex p-3 rounded-full mb-4', styles.icon)}>
            {icon || defaultIcon}
          </div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
            {title}
          </h3>
          {description && (
            <p className="text-sm text-gray-500 dark:text-zinc-400 mb-6">
              {description}
            </p>
          )}
          <div className="flex gap-3 justify-center">
            <button
              onClick={onClose}
              disabled={loading}
              className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-zinc-300 bg-gray-100 dark:bg-zinc-800 rounded-lg hover:bg-gray-200 dark:hover:bg-zinc-700 transition-colors disabled:opacity-50"
            >
              {cancelText}
            </button>
            <button
              onClick={onConfirm}
              disabled={loading}
              className={cn(
                'px-4 py-2 text-sm font-medium rounded-lg transition-colors disabled:opacity-50',
                styles.button
              )}
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Carregando...
                </span>
              ) : (
                confirmText
              )}
            </button>
          </div>
        </div>
      </Modal>
    );
  }
);

ConfirmModal.displayName = 'ConfirmModal';

export default Modal;
