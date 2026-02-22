import React from 'react';

export interface BadgeProps {
  children: React.ReactNode;
  variant?: 'success' | 'warning' | 'danger' | 'info' | 'gray' | 'primary' | 'purple' | 'orange' | 'teal' | 'indigo';
  size?: 'sm' | 'md' | 'lg';
  className?: string;
  dot?: boolean;
  icon?: React.ReactNode;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'gray',
  size = 'sm',
  className = '',
  dot = false,
  icon,
}) => {
  const variants = {
    success: 'bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-300 border-green-200 dark:border-green-800',
    warning: 'bg-yellow-100 dark:bg-yellow-900/40 text-yellow-800 dark:text-yellow-300 border-yellow-200 dark:border-yellow-800',
    danger: 'bg-red-100 dark:bg-red-900/40 text-red-800 dark:text-red-300 border-red-200 dark:border-red-800',
    info: 'bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-300 border-blue-200 dark:border-blue-800',
    gray: 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-zinc-300 border-gray-200 dark:border-zinc-700',
    primary: 'bg-primary-100 dark:bg-primary-900/40 text-primary-800 dark:text-primary-300 border-primary-200 dark:border-primary-800',
    purple: 'bg-purple-100 dark:bg-purple-900/40 text-purple-800 dark:text-purple-300 border-purple-200 dark:border-purple-800',
    orange: 'bg-orange-100 dark:bg-orange-900/40 text-orange-800 dark:text-orange-300 border-orange-200 dark:border-orange-800',
    teal: 'bg-teal-100 dark:bg-teal-900/40 text-teal-800 dark:text-teal-300 border-teal-200 dark:border-teal-800',
    indigo: 'bg-indigo-100 dark:bg-indigo-900/40 text-indigo-800 dark:text-indigo-300 border-indigo-200 dark:border-indigo-800',
  };

  const dotColors = {
    success: 'bg-green-500',
    warning: 'bg-yellow-500',
    danger: 'bg-red-500',
    info: 'bg-blue-500',
    gray: 'bg-gray-500',
    primary: 'bg-primary-500',
    purple: 'bg-purple-500',
    orange: 'bg-orange-500',
    teal: 'bg-teal-500',
    indigo: 'bg-indigo-500',
  };

  const sizes = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-2.5 py-1 text-sm',
    lg: 'px-3 py-1.5 text-sm',
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 font-medium rounded-full border ${variants[variant]} ${sizes[size]} ${className}`}
    >
      {dot && (
        <span className={`w-1.5 h-1.5 rounded-full ${dotColors[variant]}`} />
      )}
      {icon && <span className="w-3.5 h-3.5">{icon}</span>}
      {children}
    </span>
  );
};

// Order status configuration with specific colors and icons
// SEMANTIC FLOW: received -> processing -> confirmed (paid) -> preparing -> ready -> out_for_delivery -> delivered
export const ORDER_STATUS_CONFIG: Record<string, { variant: BadgeProps['variant']; label: string; description: string; icon?: string }> = {
  // Initial states
  pending: { variant: 'gray', label: 'Recebido', description: 'Pedido recebido', icon: '📥' },
  received: { variant: 'gray', label: 'Recebido', description: 'Pedido recebido', icon: '📥' },
  
  // Payment states
  processing: { variant: 'orange', label: 'Processando', description: 'Pagamento em processamento', icon: '⏳' },
  awaiting_payment: { variant: 'orange', label: 'Processando', description: 'Pagamento em processamento', icon: '⏳' },
  payment_pending: { variant: 'orange', label: 'Pagamento Pendente', description: 'Aguardando confirmação de pagamento', icon: '💳' },
  
  // Confirmed states (payment received)
  confirmed: { variant: 'info', label: 'Confirmado', description: 'Pagamento confirmado - Pronto para produção', icon: '✅' },
  paid: { variant: 'success', label: 'Pago', description: 'Pagamento confirmado', icon: '✅' },
  payment_confirmed: { variant: 'success', label: 'Pago', description: 'Pagamento confirmado via webhook', icon: '✅' },
  
  // Production states
  preparing: { variant: 'warning', label: 'Preparando', description: 'Em produção na cozinha', icon: '🔥' },
  in_production: { variant: 'warning', label: 'Em Produção', description: 'Sendo preparado', icon: '🔥' },
  ready: { variant: 'purple', label: 'Pronto', description: 'Pronto para entrega/retirada', icon: '📦' },
  
  // Delivery states
  shipped: { variant: 'teal', label: 'Enviado', description: 'Pedido enviado', icon: '🚚' },
  out_for_delivery: { variant: 'indigo', label: 'Em Entrega', description: 'Saiu para entrega', icon: '🚚' },
  delivered: { variant: 'success', label: 'Entregue', description: 'Pedido entregue', icon: '🏠' },
  completed: { variant: 'success', label: 'Finalizado', description: 'Pedido concluído', icon: '✔️' },
  
  // Cancelled states
  cancelled: { variant: 'danger', label: 'Cancelado', description: 'Pedido cancelado', icon: '❌' },
  refunded: { variant: 'gray', label: 'Reembolsado', description: 'Valor reembolsado', icon: '↩️' },
  failed: { variant: 'danger', label: 'Falhou', description: 'Falha no processamento', icon: '❌' },
};

// Payment status configuration (separate from order status)
export const PAYMENT_STATUS_CONFIG: Record<string, { variant: BadgeProps['variant']; label: string; icon: string }> = {
  pending: { variant: 'warning', label: 'Aguardando', icon: '💳' },
  processing: { variant: 'orange', label: 'Processando', icon: '⏳' },
  paid: { variant: 'success', label: 'Pago', icon: '✅' },
  failed: { variant: 'danger', label: 'Falhou', icon: '❌' },
  refunded: { variant: 'purple', label: 'Reembolsado', icon: '↩️' },
  partially_refunded: { variant: 'warning', label: 'Reembolso Parcial', icon: '↩️' },
};

// Conversation status configuration
export const CONVERSATION_STATUS_CONFIG: Record<string, { variant: BadgeProps['variant']; label: string; description: string }> = {
  open: { variant: 'success', label: 'Aberta', description: 'Conversa ativa' },
  closed: { variant: 'gray', label: 'Fechada', description: 'Conversa encerrada' },
  pending: { variant: 'warning', label: 'Pendente', description: 'Aguardando resposta' },
  resolved: { variant: 'info', label: 'Resolvida', description: 'Problema resolvido' },
};

// Conversation mode configuration
export const CONVERSATION_MODE_CONFIG: Record<string, { variant: BadgeProps['variant']; label: string; description: string }> = {
  auto: { variant: 'info', label: 'Automático', description: 'Respondido por IA' },
  human: { variant: 'warning', label: 'Humano', description: 'Atendimento humano' },
  hybrid: { variant: 'purple', label: 'Híbrido', description: 'IA + Humano' },
};

// Status badge helper
export const StatusBadge: React.FC<{ status: string; showDot?: boolean; size?: BadgeProps['size'] }> = ({ 
  status, 
  showDot = false,
  size = 'sm' 
}) => {
  const statusConfig: Record<string, { variant: BadgeProps['variant']; label: string }> = {
    // Account statuses
    active: { variant: 'success', label: 'Ativo' },
    inactive: { variant: 'gray', label: 'Inativo' },
    suspended: { variant: 'danger', label: 'Suspenso' },
    
    // Message statuses
    sent: { variant: 'info', label: 'Enviada' },
    delivered: { variant: 'success', label: 'Entregue' },
    read: { variant: 'primary', label: 'Lida' },
    failed: { variant: 'danger', label: 'Falhou' },
    
    // Conversation statuses
    ...Object.fromEntries(
      Object.entries(CONVERSATION_STATUS_CONFIG).map(([k, v]) => [k, { variant: v.variant, label: v.label }])
    ),
    
    // Conversation modes
    ...Object.fromEntries(
      Object.entries(CONVERSATION_MODE_CONFIG).map(([k, v]) => [k, { variant: v.variant, label: v.label }])
    ),
    
    // Order statuses
    ...Object.fromEntries(
      Object.entries(ORDER_STATUS_CONFIG).map(([k, v]) => [k, { variant: v.variant, label: v.label }])
    ),
    
    // Payment statuses
    completed: { variant: 'success', label: 'Concluído' },
    partially_refunded: { variant: 'warning', label: 'Reembolso Parcial' },
    
    // AI Agent statuses
    testing: { variant: 'warning', label: 'Testando' },
    success: { variant: 'success', label: 'Sucesso' },
    error: { variant: 'danger', label: 'Erro' },
    timeout: { variant: 'warning', label: 'Timeout' },
    
    // Template statuses
    approved: { variant: 'success', label: 'Aprovado' },
    rejected: { variant: 'danger', label: 'Rejeitado' },
  };

  const config = statusConfig[status] || { variant: 'gray' as const, label: status };

  return <Badge variant={config.variant} dot={showDot} size={size}>{config.label}</Badge>;
};

// Order Status Badge with more details
export const OrderStatusBadge: React.FC<{ status: string; showDot?: boolean; size?: BadgeProps['size'] }> = ({ 
  status, 
  showDot = true,
  size = 'sm' 
}) => {
  const config = ORDER_STATUS_CONFIG[status] || { variant: 'gray' as const, label: status, description: '' };
  return <Badge variant={config.variant} dot={showDot} size={size}>{config.label}</Badge>;
};

// Conversation Status Badge
export const ConversationStatusBadge: React.FC<{ status: string; showDot?: boolean; size?: BadgeProps['size'] }> = ({ 
  status, 
  showDot = true,
  size = 'sm' 
}) => {
  const config = CONVERSATION_STATUS_CONFIG[status] || { variant: 'gray' as const, label: status, description: '' };
  return <Badge variant={config.variant} dot={showDot} size={size}>{config.label}</Badge>;
};

// Conversation Mode Badge
export const ConversationModeBadge: React.FC<{ mode: string; showDot?: boolean; size?: BadgeProps['size'] }> = ({ 
  mode, 
  showDot = false,
  size = 'sm' 
}) => {
  const config = CONVERSATION_MODE_CONFIG[mode] || { variant: 'gray' as const, label: mode, description: '' };
  return <Badge variant={config.variant} dot={showDot} size={size}>{config.label}</Badge>;
};
