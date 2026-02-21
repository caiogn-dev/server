/**
 * Dialog Component - Alias for Modal with Dialog-like API
 */
import React from 'react';
import { Modal, ModalHeader, ModalBody } from './modal';
import { cn } from '../../utils/cn';

// Dialog is just an alias for Modal
export interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: React.ReactNode;
  className?: string;
}

export const Dialog: React.FC<DialogProps> = ({
  open,
  onOpenChange,
  children,
  className,
}) => (
  <Modal
    open={open}
    onClose={() => onOpenChange(false)}
    className={className}
    showCloseButton={false}
  >
    {children}
  </Modal>
);

// DialogContent wraps ModalBody
export interface DialogContentProps extends React.HTMLAttributes<HTMLDivElement> {}

export const DialogContent: React.FC<DialogContentProps> = ({
  children,
  className,
  ...props
}) => (
  <div className={cn('p-6', className)} {...props}>
    {children}
  </div>
);

// DialogHeader
export interface DialogHeaderProps extends React.HTMLAttributes<HTMLDivElement> {}

export const DialogHeader: React.FC<DialogHeaderProps> = ({
  children,
  className,
  ...props
}) => (
  <div className={cn('mb-4', className)} {...props}>
    {children}
  </div>
);

// DialogTitle
export interface DialogTitleProps extends React.HTMLAttributes<HTMLHeadingElement> {}

export const DialogTitle: React.FC<DialogTitleProps> = ({
  children,
  className,
  ...props
}) => (
  <h2
    className={cn('text-lg font-semibold text-gray-900 dark:text-white', className)}
    {...props}
  >
    {children}
  </h2>
);

// DialogDescription
export interface DialogDescriptionProps extends React.HTMLAttributes<HTMLParagraphElement> {}

export const DialogDescription: React.FC<DialogDescriptionProps> = ({
  children,
  className,
  ...props
}) => (
  <p
    className={cn('text-sm text-gray-500 dark:text-zinc-400 mt-1', className)}
    {...props}
  >
    {children}
  </p>
);

export default Dialog;
