/**
 * Centralized formatting utilities
 * 
 * Use these functions throughout the dashboard for consistent formatting.
 */

// ==================== Currency Formatting ====================

/**
 * Format a number as Brazilian Real (BRL) currency
 * @param value - Number to format
 * @param options - Optional Intl.NumberFormatOptions
 */
export function formatCurrency(value: number, options?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    ...options,
  }).format(value);
}

/**
 * Alias for formatCurrency (backwards compatibility)
 */
export const formatMoney = formatCurrency;

/**
 * Format as compact currency (e.g., R$ 1,5K, R$ 2,3M)
 */
export function formatCompactCurrency(value: number): string {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value);
}

// ==================== Number Formatting ====================

/**
 * Format a number with Brazilian locale
 */
export function formatNumber(value: number, options?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat('pt-BR', options).format(value);
}

/**
 * Format as compact number (e.g., 1.5K, 2.3M)
 */
export function formatCompactNumber(value: number): string {
  return new Intl.NumberFormat('pt-BR', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value);
}

/**
 * Format as percentage
 */
export function formatPercent(value: number, decimals: number = 1): string {
  return new Intl.NumberFormat('pt-BR', {
    style: 'percent',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value / 100);
}

// ==================== Date/Time Formatting ====================

/**
 * Format a date string or Date object
 */
export function formatDate(
  date: string | Date | null | undefined,
  options?: Intl.DateTimeFormatOptions
): string {
  if (!date) return '-';
  
  const d = typeof date === 'string' ? new Date(date) : date;
  
  if (isNaN(d.getTime())) return '-';
  
  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    ...options,
  }).format(d);
}

/**
 * Format a date with time
 */
export function formatDateTime(
  date: string | Date | null | undefined,
  options?: Intl.DateTimeFormatOptions
): string {
  if (!date) return '-';
  
  const d = typeof date === 'string' ? new Date(date) : date;
  
  if (isNaN(d.getTime())) return '-';
  
  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    ...options,
  }).format(d);
}

/**
 * Format time only
 */
export function formatTime(
  date: string | Date | null | undefined,
  options?: Intl.DateTimeFormatOptions
): string {
  if (!date) return '-';
  
  const d = typeof date === 'string' ? new Date(date) : date;
  
  if (isNaN(d.getTime())) return '-';
  
  return new Intl.DateTimeFormat('pt-BR', {
    hour: '2-digit',
    minute: '2-digit',
    ...options,
  }).format(d);
}

/**
 * Format as relative time (e.g., "há 2 minutos", "em 3 dias")
 */
export function formatRelativeTime(date: string | Date | null | undefined): string {
  if (!date) return '-';
  
  const d = typeof date === 'string' ? new Date(date) : date;
  
  if (isNaN(d.getTime())) return '-';
  
  const now = new Date();
  const diffMs = d.getTime() - now.getTime();
  const diffSecs = Math.round(diffMs / 1000);
  const diffMins = Math.round(diffSecs / 60);
  const diffHours = Math.round(diffMins / 60);
  const diffDays = Math.round(diffHours / 24);
  
  const rtf = new Intl.RelativeTimeFormat('pt-BR', { numeric: 'auto' });
  
  if (Math.abs(diffSecs) < 60) {
    return rtf.format(diffSecs, 'second');
  } else if (Math.abs(diffMins) < 60) {
    return rtf.format(diffMins, 'minute');
  } else if (Math.abs(diffHours) < 24) {
    return rtf.format(diffHours, 'hour');
  } else if (Math.abs(diffDays) < 30) {
    return rtf.format(diffDays, 'day');
  } else {
    return formatDate(d);
  }
}

/**
 * Format as "short" relative time for chat (e.g., "Agora", "5m", "2h", "Ontem")
 */
export function formatChatTime(date: string | Date | null | undefined): string {
  if (!date) return '';
  
  const d = typeof date === 'string' ? new Date(date) : date;
  
  if (isNaN(d.getTime())) return '';
  
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);
  
  if (diffMins < 1) {
    return 'Agora';
  } else if (diffMins < 60) {
    return `${diffMins}m`;
  } else if (diffHours < 24) {
    return `${diffHours}h`;
  } else if (diffDays === 1) {
    return 'Ontem';
  } else if (diffDays < 7) {
    return `${diffDays}d`;
  } else {
    return formatDate(d, { day: '2-digit', month: 'short' });
  }
}

// ==================== Phone Formatting ====================

/**
 * Format Brazilian phone number
 * Input: 5511999999999 → Output: +55 (11) 99999-9999
 */
export function formatPhone(phone: string | null | undefined): string {
  if (!phone) return '-';
  
  // Remove non-digits
  const digits = phone.replace(/\D/g, '');
  
  // Brazilian mobile with country code (13 digits)
  if (digits.length === 13 && digits.startsWith('55')) {
    return `+${digits.slice(0, 2)} (${digits.slice(2, 4)}) ${digits.slice(4, 9)}-${digits.slice(9)}`;
  }
  
  // Brazilian landline with country code (12 digits)
  if (digits.length === 12 && digits.startsWith('55')) {
    return `+${digits.slice(0, 2)} (${digits.slice(2, 4)}) ${digits.slice(4, 8)}-${digits.slice(8)}`;
  }
  
  // Brazilian mobile without country code (11 digits)
  if (digits.length === 11) {
    return `(${digits.slice(0, 2)}) ${digits.slice(2, 7)}-${digits.slice(7)}`;
  }
  
  // Brazilian landline without country code (10 digits)
  if (digits.length === 10) {
    return `(${digits.slice(0, 2)}) ${digits.slice(2, 6)}-${digits.slice(6)}`;
  }
  
  // Return original if can't format
  return phone;
}

/**
 * Format phone for WhatsApp link
 */
export function formatPhoneForWhatsApp(phone: string | null | undefined): string {
  if (!phone) return '';
  
  // Remove non-digits
  let digits = phone.replace(/\D/g, '');
  
  // Add country code if missing
  if (!digits.startsWith('55') && digits.length <= 11) {
    digits = '55' + digits;
  }
  
  return digits;
}

// ==================== Text Formatting ====================

/**
 * Truncate text with ellipsis
 */
export function truncate(text: string | null | undefined, maxLength: number): string {
  if (!text) return '';
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength - 3) + '...';
}

/**
 * Capitalize first letter
 */
export function capitalize(text: string | null | undefined): string {
  if (!text) return '';
  return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
}

/**
 * Convert to title case
 */
export function titleCase(text: string | null | undefined): string {
  if (!text) return '';
  return text
    .toLowerCase()
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

/**
 * Format CPF
 * Input: 12345678901 → Output: 123.456.789-01
 */
export function formatCPF(cpf: string | null | undefined): string {
  if (!cpf) return '-';
  
  const digits = cpf.replace(/\D/g, '');
  
  if (digits.length !== 11) return cpf;
  
  return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6, 9)}-${digits.slice(9)}`;
}

/**
 * Format CNPJ
 * Input: 12345678000190 → Output: 12.345.678/0001-90
 */
export function formatCNPJ(cnpj: string | null | undefined): string {
  if (!cnpj) return '-';
  
  const digits = cnpj.replace(/\D/g, '');
  
  if (digits.length !== 14) return cnpj;
  
  return `${digits.slice(0, 2)}.${digits.slice(2, 5)}.${digits.slice(5, 8)}/${digits.slice(8, 12)}-${digits.slice(12)}`;
}

/**
 * Format CEP
 * Input: 01310100 → Output: 01310-100
 */
export function formatCEP(cep: string | null | undefined): string {
  if (!cep) return '-';
  
  const digits = cep.replace(/\D/g, '');
  
  if (digits.length !== 8) return cep;
  
  return `${digits.slice(0, 5)}-${digits.slice(5)}`;
}

// ==================== File Size Formatting ====================

/**
 * Format file size in human-readable format
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const size = bytes / Math.pow(1024, i);
  
  return `${size.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

// ==================== Order Status Formatting ====================

export const ORDER_STATUS_LABELS: Record<string, string> = {
  pending: 'Pendente',
  confirmed: 'Confirmado',
  preparing: 'Preparando',
  ready: 'Pronto',
  out_for_delivery: 'Em Entrega',
  delivered: 'Entregue',
  cancelled: 'Cancelado',
};

export const ORDER_STATUS_COLORS: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  confirmed: 'bg-blue-100 text-blue-800',
  preparing: 'bg-orange-100 text-orange-800',
  ready: 'bg-purple-100 text-purple-800',
  out_for_delivery: 'bg-indigo-100 text-indigo-800',
  delivered: 'bg-green-100 text-green-800',
  cancelled: 'bg-red-100 text-red-800',
};

export function formatOrderStatus(status: string): string {
  return ORDER_STATUS_LABELS[status] || status;
}

// ==================== Payment Status Formatting ====================

export const PAYMENT_STATUS_LABELS: Record<string, string> = {
  pending: 'Pendente',
  processing: 'Processando',
  approved: 'Aprovado',
  rejected: 'Rejeitado',
  refunded: 'Reembolsado',
  cancelled: 'Cancelado',
};

export const PAYMENT_STATUS_COLORS: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  processing: 'bg-blue-100 text-blue-800',
  approved: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  refunded: 'bg-purple-100 text-purple-800',
  cancelled: 'bg-gray-100 text-gray-800',
};

export function formatPaymentStatus(status: string): string {
  return PAYMENT_STATUS_LABELS[status] || status;
}

// ==================== Message Status Formatting ====================

export const MESSAGE_STATUS_LABELS: Record<string, string> = {
  pending: 'Pendente',
  sent: 'Enviada',
  delivered: 'Entregue',
  read: 'Lida',
  seen: 'Visualizada',
  failed: 'Falhou',
};

export function formatMessageStatus(status: string): string {
  return MESSAGE_STATUS_LABELS[status] || status;
}
