import api from './api';
import {
  CompanyProfile,
  CreateCompanyProfile,
  UpdateCompanyProfile,
  AutoMessage,
  CreateAutoMessage,
  CustomerSession,
  AutomationLog,
  CompanyProfileStats,
  AutomationLogStats,
  PaginatedResponse,
  AutoMessageEventType,
} from '../types';

// Company Profile API
export const companyProfileApi = {
  list: async (params?: {
    account_id?: string;
    business_type?: string;
    page?: number;
    page_size?: number;
  }): Promise<PaginatedResponse<CompanyProfile>> => {
    const response = await api.get('/automation/companies/', { params });
    return response.data;
  },

  get: async (id: string): Promise<CompanyProfile> => {
    const response = await api.get(`/automation/companies/${id}/`);
    return response.data;
  },

  create: async (data: CreateCompanyProfile): Promise<CompanyProfile> => {
    const response = await api.post('/automation/companies/', data);
    return response.data;
  },

  update: async (id: string, data: UpdateCompanyProfile): Promise<CompanyProfile> => {
    const response = await api.put(`/automation/companies/${id}/`, data);
    return response.data;
  },

  delete: async (id: string): Promise<void> => {
    await api.delete(`/automation/companies/${id}/`);
  },

  regenerateApiKey: async (id: string): Promise<{ api_key: string; message: string }> => {
    const response = await api.post(`/automation/companies/${id}/regenerate_api_key/`);
    return response.data;
  },

  regenerateWebhookSecret: async (id: string): Promise<{ webhook_secret: string; message: string }> => {
    const response = await api.post(`/automation/companies/${id}/regenerate_webhook_secret/`);
    return response.data;
  },

  getStats: async (id: string): Promise<CompanyProfileStats> => {
    const response = await api.get(`/automation/companies/${id}/stats/`);
    return response.data;
  },
};

// Auto Message API
export const autoMessageApi = {
  list: async (params?: {
    company_id?: string;
    event_type?: AutoMessageEventType;
    is_active?: boolean;
    page?: number;
    page_size?: number;
  }): Promise<PaginatedResponse<AutoMessage>> => {
    const response = await api.get('/automation/messages/', { params });
    return response.data;
  },

  get: async (id: string): Promise<AutoMessage> => {
    const response = await api.get(`/automation/messages/${id}/`);
    return response.data;
  },

  create: async (data: CreateAutoMessage): Promise<AutoMessage> => {
    const response = await api.post('/automation/messages/', data);
    return response.data;
  },

  update: async (id: string, data: Partial<AutoMessage>): Promise<AutoMessage> => {
    const response = await api.put(`/automation/messages/${id}/`, data);
    return response.data;
  },

  delete: async (id: string): Promise<void> => {
    await api.delete(`/automation/messages/${id}/`);
  },

  test: async (
    id: string,
    data: {
      phone_number: string;
      customer_name?: string;
      cart_total?: string;
      order_number?: string;
      send?: boolean;
    }
  ): Promise<{
    success: boolean;
    message: string;
    rendered_message: string;
    buttons?: Array<{ id: string; title: string }>;
    error?: string;
  }> => {
    const response = await api.post(`/automation/messages/${id}/test/`, data);
    return response.data;
  },

  bulkUpdate: async (
    updates: Array<{
      id: string;
      is_active?: boolean;
      priority?: number;
      message_text?: string;
      delay_seconds?: number;
    }>
  ): Promise<{ updated: number; errors: string[] }> => {
    const response = await api.post('/automation/messages/bulk_update/', { updates });
    return response.data;
  },
};

// Customer Session API
export const customerSessionApi = {
  list: async (params?: {
    company_id?: string;
    status?: string;
    phone_number?: string;
    start_date?: string;
    end_date?: string;
    page?: number;
    page_size?: number;
  }): Promise<PaginatedResponse<CustomerSession>> => {
    const response = await api.get('/automation/sessions/', { params });
    return response.data;
  },

  get: async (id: string): Promise<CustomerSession> => {
    const response = await api.get(`/automation/sessions/${id}/`);
    return response.data;
  },

  getByPhone: async (params: {
    phone_number: string;
    company_id?: string;
  }): Promise<CustomerSession[]> => {
    const response = await api.get('/automation/sessions/by_phone/', { params });
    return response.data;
  },

  sendNotification: async (
    id: string,
    data: {
      event_type: AutoMessageEventType;
      context?: Record<string, unknown>;
    }
  ): Promise<{ success: boolean; message: string }> => {
    const response = await api.post(`/automation/sessions/${id}/send_notification/`, data);
    return response.data;
  },

  updateStatus: async (
    id: string,
    status: string
  ): Promise<CustomerSession> => {
    const response = await api.post(`/automation/sessions/${id}/update_status/`, { status });
    return response.data;
  },
};

// Automation Log API
export const automationLogApi = {
  list: async (params?: {
    company_id?: string;
    action_type?: string;
    is_error?: boolean;
    phone_number?: string;
    start_date?: string;
    end_date?: string;
    page?: number;
    page_size?: number;
  }): Promise<PaginatedResponse<AutomationLog>> => {
    const response = await api.get('/automation/logs/', { params });
    return response.data;
  },

  get: async (id: string): Promise<AutomationLog> => {
    const response = await api.get(`/automation/logs/${id}/`);
    return response.data;
  },

  getStats: async (params?: { company_id?: string }): Promise<AutomationLogStats> => {
    const response = await api.get('/automation/logs/stats/', { params });
    return response.data;
  },
};

// Event type labels for display
export const eventTypeLabels: Record<AutoMessageEventType, string> = {
  // Welcome & General
  welcome: 'Boas-vindas',
  menu: 'Cardápio/Catálogo',
  business_hours: 'Horário de Funcionamento',
  out_of_hours: 'Fora do Horário',
  faq: 'Perguntas Frequentes',
  // Cart
  cart_created: 'Carrinho Criado',
  cart_abandoned: 'Carrinho Abandonado',
  cart_reminder: 'Lembrete de Carrinho',
  cart_reminder_30: 'Lembrete Carrinho (30min)',
  cart_reminder_2h: 'Lembrete Carrinho (2h)',
  cart_reminder_24h: 'Lembrete Carrinho (24h)',
  // Payment
  pix_generated: 'PIX Gerado',
  pix_reminder: 'Lembrete de PIX',
  pix_expired: 'PIX Expirado',
  payment_reminder_1: 'Lembrete Pagamento (30min)',
  payment_reminder_2: 'Lembrete Pagamento (2h)',
  payment_confirmed: 'Pagamento Confirmado',
  payment_failed: 'Pagamento Falhou',
  // Order Status
  order_received: 'Pedido Recebido',
  order_confirmed: 'Pedido Confirmado',
  order_preparing: 'Pedido em Preparo',
  order_ready: 'Pedido Pronto',
  order_shipped: 'Pedido Enviado',
  order_out_for_delivery: 'Saiu para Entrega',
  order_delivered: 'Pedido Entregue',
  order_cancelled: 'Pedido Cancelado',
  // Feedback & Support
  feedback_request: 'Solicitar Avaliação',
  feedback_received: 'Avaliação Recebida',
  human_handoff: 'Transferido para Humano',
  human_assigned: 'Atendente Atribuído',
  // Custom
  custom: 'Personalizado',
};

// Business type labels
export const businessTypeLabels: Record<string, string> = {
  restaurant: 'Restaurante',
  ecommerce: 'E-commerce',
  services: 'Serviços',
  retail: 'Varejo',
  healthcare: 'Saúde',
  education: 'Educação',
  other: 'Outro',
};

// Session status labels
export const sessionStatusLabels: Record<string, string> = {
  active: 'Ativa',
  cart_created: 'Carrinho Criado',
  cart_abandoned: 'Carrinho Abandonado',
  checkout: 'Em Checkout',
  payment_pending: 'Aguardando Pagamento',
  payment_confirmed: 'Pagamento Confirmado',
  order_placed: 'Pedido Realizado',
  completed: 'Concluída',
  expired: 'Expirada',
};

// Message variables available for templates
export const messageVariables = [
  { key: 'customer_name', description: 'Nome do cliente' },
  { key: 'phone_number', description: 'Telefone do cliente' },
  { key: 'cart_total', description: 'Valor do carrinho' },
  { key: 'cart_items', description: 'Itens do carrinho' },
  { key: 'cart_item_count', description: 'Quantidade de itens no carrinho' },
  { key: 'order_number', description: 'Número do pedido' },
  { key: 'order_status', description: 'Status do pedido' },
  { key: 'amount', description: 'Valor do pagamento' },
  { key: 'pix_code', description: 'Código PIX copia e cola' },
  { key: 'time_remaining', description: 'Tempo restante (ex: 30 minutos)' },
  { key: 'tracking_code', description: 'Código de rastreio' },
  { key: 'delivery_estimate', description: 'Previsão de entrega' },
  { key: 'delivery_address', description: 'Endereço de entrega' },
  { key: 'company_name', description: 'Nome da empresa' },
  { key: 'store_name', description: 'Nome da loja' },
  { key: 'website_url', description: 'URL do site' },
  { key: 'menu_url', description: 'URL do cardápio' },
  { key: 'business_hours_today', description: 'Horário de hoje' },
  { key: 'discount_code', description: 'Código de desconto' },
  { key: 'discount_percentage', description: 'Porcentagem de desconto' },
];

// Intent type labels
export const intentTypeLabels: Record<string, string> = {
  greeting: 'Saudação',
  price_check: 'Consulta de Preço',
  business_hours: 'Horário de Funcionamento',
  delivery_info: 'Informações de Entrega',
  menu_request: 'Solicitação de Cardápio',
  track_order: 'Rastrear Pedido',
  payment_status: 'Status de Pagamento',
  location: 'Localização/Endereço',
  contact: 'Contato',
  faq: 'Pergunta Frequente',
  create_order: 'Criar Pedido',
  cancel_order: 'Cancelar Pedido',
  modify_order: 'Modificar Pedido',
  confirm_payment: 'Confirmar Pagamento',
  request_pix: 'Solicitar PIX',
  add_to_cart: 'Adicionar ao Carrinho',
  product_inquiry: 'Consulta de Produto',
  customization: 'Personalização',
  comparison: 'Comparação',
  recommendation: 'Recomendação',
  complaint: 'Reclamação',
  general_question: 'Pergunta Geral',
  unknown: 'Desconhecido',
  human_handoff: 'Transferir para Humano',
};
