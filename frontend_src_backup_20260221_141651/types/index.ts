

// ============================================
// AUTO MESSAGE EVENT TYPES
// ============================================

export type AutoMessageEventType =
  | 'welcome' | 'menu' | 'business_hours' | 'out_of_hours' | 'faq'
  | 'cart_created' | 'cart_abandoned' | 'cart_reminder' | 'cart_reminder_30' | 'cart_reminder_2h' | 'cart_reminder_24h'
  | 'pix_generated' | 'pix_reminder' | 'pix_expired' | 'payment_confirmed' | 'payment_failed' | 'payment_reminder_1' | 'payment_reminder_2'
  | 'order_received' | 'order_confirmed' | 'order_preparing' | 'order_ready' | 'order_shipped' | 'order_out_for_delivery' | 'order_delivered' | 'order_cancelled'
  | 'feedback_request' | 'feedback_received' | 'human_handoff' | 'human_assigned' | 'custom';

// ============================================
// WHATSAPP ACCOUNT TYPES
// ============================================

export interface WhatsAppAccount {
  id: string;
  name: string;
  phone_number: string;
  display_phone_number?: string;
  phone_number_id?: string;
  business_account_id?: string;
  status: 'active' | 'inactive' | 'pending' | 'error';
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateWhatsAppAccount {
  name: string;
  phone_number: string;
}

// ============================================
// USER TYPES
// ============================================

export interface User {
  id: string;
  email: string;
  username: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
  is_staff: boolean;
  is_superuser: boolean;
  date_joined: string;
}

export interface LoginResponse {
  access: string;
  refresh: string;
  user: User;
}

// ============================================
// MESSAGE TYPES
// ============================================

export interface Message {
  id: string;
  message_id: string;
  conversation_id: string;
  account_id?: string;
  phone_number: string;
  from_number?: string;
  to_number?: string;
  text?: string;
  text_body?: string;
  message_type: 'text' | 'image' | 'document' | 'audio' | 'video' | 'template' | 'interactive';
  media_url?: string;
  caption?: string;
  timestamp: string;
  created_at: string;
  direction: 'inbound' | 'outbound';
  status: 'sent' | 'delivered' | 'read' | 'failed' | 'pending';
  whatsapp_message_id?: string;
  delivered_at?: string;
  read_at?: string;
  account_name?: string;
}

export interface Conversation {
  id: string;
  phone_number: string;
  contact_name: string;
  last_message?: string;
  last_message_at?: string;
  unread_count: number;
  status: 'open' | 'closed' | 'pending';
  mode: 'auto' | 'manual' | 'hybrid' | 'human';
  tags: string[];
  created_at: string;
}

// ============================================
// WHATSAPP MESSAGE TEMPLATES
// ============================================

export interface MessageTemplate {
  id: string;
  name: string;
  category: string;
  language: string;
  status: 'approved' | 'pending' | 'rejected';
  components: Array<{
    type: string;
    text?: string;
    format?: string;
    example?: unknown;
  }>;
}

export interface SendTextMessage {
  to: string;
  text: string;
  account_id?: string;
}

export interface SendTemplateMessage {
  to: string;
  template_name: string;
  language: string;
  components?: unknown[];
}

export interface SendInteractiveButtons {
  to: string;
  body: string;
  buttons: Array<{ id: string; title: string }>;
}

export interface SendInteractiveList {
  to: string;
  body: string;
  button: string;
  sections: Array<{
    title: string;
    rows: Array<{ id: string; title: string; description?: string }>;
  }>;
}

// ============================================
// PAGINATION
// ============================================

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ============================================
// COMPANY PROFILE TYPES
// ============================================

export interface CompanyProfile {
  id: string;
  company_name: string;
  business_type: string;
  description?: string;
  phone_number: string;
  email?: string;
  address?: string;
  city?: string;
  state?: string;
  website_url?: string;
  menu_url?: string;
  auto_reply_enabled: boolean;
  welcome_message_enabled: boolean;
  use_ai_agent: boolean;
  default_agent_id?: string;
  created_at: string;
  updated_at: string;
}

// ============================================
// CUSTOMER SESSION TYPES
// ============================================

export interface CustomerSession {
  id: string;
  company_id: string;
  phone_number: string;
  customer_name?: string;
  customer_email?: string;
  session_id: string;
  status: 'active' | 'cart_created' | 'cart_abandoned' | 'checkout' | 'payment_pending' | 'payment_confirmed' | 'order_placed' | 'completed' | 'expired';
  cart_data?: {
    items: Array<{
      quantity: number;
      name: string;
      total: number;
    }>;
    total: number;
  };
  cart_total: number;
  cart_items_count: number;
  pix_code?: string;
  pix_expires_at?: string;
  order_id?: string;
  external_order_id?: string;
  last_activity_at: string;
  created_at: string;
}

// ============================================
// AUTO MESSAGE TYPES
// ============================================

export interface AutoMessage {
  id: string;
  company_id: string;
  event_type: AutoMessageEventType;
  name: string;
  message_text: string;
  media_url?: string;
  media_type?: 'image' | 'document' | 'video';
  buttons?: Array<{ id: string; title: string }>;
  is_active: boolean;
  delay_seconds: number;
  priority: number;
  created_at: string;
  updated_at: string;
}

export interface CreateAutoMessage {
  event_type: AutoMessageEventType;
  name: string;
  message_text: string;
  media_url?: string;
  media_type?: 'image' | 'document' | 'video';
  buttons?: Array<{ id: string; title: string }>;
  is_active?: boolean;
  delay_seconds?: number;
  priority?: number;
}

export interface CreateCompanyProfile {
  company_name: string;
  business_type?: string;
  description?: string;
  phone_number?: string;
  email?: string;
  address?: string;
  city?: string;
  state?: string;
  website_url?: string;
  menu_url?: string;
  auto_reply_enabled?: boolean;
  welcome_message_enabled?: boolean;
  use_ai_agent?: boolean;
  default_agent_id?: string;
}

export interface UpdateCompanyProfile extends Partial<CreateCompanyProfile> {}

// ============================================
// SCHEDULING & REPORTS
// ============================================

export interface ReportSchedule {
  id: string;
  name: string;
  report_type: string;
  frequency: 'daily' | 'weekly' | 'monthly';
  status: 'active' | 'paused' | 'disabled';
  recipients: string[];
  last_run_at?: string;
  next_run_at?: string;
}

export interface GeneratedReport {
  id: string;
  name: string;
  report_type: string;
  status: 'generating' | 'completed' | 'failed';
  file_path?: string;
  file_size: number;
  period_start: string;
  period_end: string;
  created_at: string;
}

export interface GenerateReportRequest {
  report_type: string;
  period_start: string;
  period_end: string;
  format: 'csv' | 'xlsx';
}

// ============================================
// INTENT DETECTION TYPES (NOVO SISTEMA)
// ============================================

export type IntentType =
  | 'greeting' | 'price_check' | 'business_hours' | 'delivery_info'
  | 'menu_request' | 'track_order' | 'payment_status' | 'location'
  | 'contact' | 'faq' | 'create_order' | 'cancel_order'
  | 'modify_order' | 'confirm_payment' | 'request_pix' | 'add_to_cart'
  | 'product_inquiry' | 'customization' | 'comparison' | 'recommendation'
  | 'complaint' | 'general_question' | 'unknown' | 'human_handoff';

export interface IntentDetectionResult {
  intent: IntentType;
  method: 'regex' | 'llm' | 'none';
  confidence: number;
  entities: Record<string, unknown>;
  original_message: string;
}

export interface IntentStats {
  total_detected: number;
  by_type: Record<IntentType, number>;
  by_method: { regex: number; llm: number };
  avg_response_time_ms: number;
  top_intents: Array<{ intent: IntentType; count: number }>;
  period: { start: string; end: string };
}

export interface IntentLog {
  id: string;
  message_id: string;
  conversation_id: string;
  phone_number: string;
  message_text: string;
  intent_type: IntentType;
  method: 'regex' | 'llm' | 'none';
  confidence: number;
  handler_used: string;
  response_text: string;
  response_type: 'text' | 'buttons' | 'list' | 'interactive';
  processing_time_ms: number;
  created_at: string;
}

// ============================================
// INTERACTIVE MESSAGE TYPES
// ============================================

export interface InteractiveButton {
  id: string;
  title: string;
}

export interface InteractiveListRow {
  id: string;
  title: string;
  description?: string;
}

export interface InteractiveListSection {
  title: string;
  rows: InteractiveListRow[];
}

export interface InteractiveMessage {
  type: 'buttons' | 'list';
  body: string;
  buttons?: InteractiveButton[];
  button?: string;  // Texto do botão para abrir lista
  sections?: InteractiveListSection[];
}

// ============================================
// AUTOMATION LOG TYPES
// ============================================

export interface AutomationLog {
  id: string;
  company_id: string;
  session_id?: string;
  action_type: 'message_received' | 'message_sent' | 'webhook_received' | 'session_created' | 'session_updated' | 'notification_sent' | 'error';
  description: string;
  phone_number?: string;
  event_type?: string;
  request_data?: Record<string, unknown>;
  response_data?: Record<string, unknown>;
  is_error: boolean;
  error_message?: string;
  created_at: string;
}

export interface AutomationLogStats {
  total_logs: number;
  by_action_type: Record<string, number>;
  errors_count: number;
  period: { start: string; end: string };
}

export interface CompanyProfileStats {
  total_companies: number;
  active_companies: number;
  with_ai_enabled: number;
  with_store_linked: number;
  by_business_type: Record<string, number>;
}

// ============================================
// CONVERSATION NOTE TYPES
// ============================================

export interface ConversationNote {
  id: string;
  conversation_id: string;
  content: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

// ============================================
// DASHBOARD TYPES
// ============================================

export interface DashboardOverview {
  total_conversations: number;
  total_messages: number;
  total_orders: number;
  total_revenue: number;
  active_conversations: number;
  pending_orders: number;
  timestamp?: string;
  orders: {
    revenue_today?: number;
    revenue_month?: number;
    count?: number;
    today?: number;
  };
  payments: {
    pending?: number;
    completed_today?: number;
  };
  customers?: number;
  products?: number;
  agents: {
    interactions_today?: number;
    avg_response_time_ms?: number;
    success_rate?: number;
  };
  accounts: {
    active?: number;
  };
  messages: {
    by_status?: Record<string, number>;
    today?: number;
  };
  conversations: {
    by_mode?: Record<string, number>;
    active?: number;
  };
}

export interface DashboardActivity {
  id: string;
  type: 'message' | 'order' | 'payment' | 'system';
  description: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

export interface DashboardCharts {
  messages_by_day: Array<{ date: string; count: number; inbound?: number; outbound?: number }>;
  messages_per_day?: Array<{ date: string; count: number; new?: number; resolved?: number; inbound?: number; outbound?: number }>;
  orders_by_day: Array<{ date: string; count: number; revenue: number }>;
  orders_per_day?: Array<{ date: string; count: number; revenue: number }>;
  top_products: Array<{ name: string; sales: number }>;
  conversion_funnel: Array<{ stage: string; count: number }>;
  order_statuses?: Record<string, number>;
  conversations_per_day?: Array<{ date: string; count: number; new?: number; resolved?: number }>;
  message_types?: Record<string, number>;
}

// ============================================
// EXPORT TYPES
// ============================================

export interface ExportParams {
  format?: 'csv' | 'xlsx' | 'pdf';
  entity?: 'conversations' | 'messages' | 'orders' | 'customers';
  store?: string;
  status?: string;
  mode?: string;
  filters?: Record<string, unknown>;
  date_from?: string;
  date_to?: string;
  fields?: string[];
}

// ============================================
// ORDER TYPES
// ============================================

export interface OrderItem {
  id: string;
  product_id: string;
  product_name: string;
  quantity: number;
  unit_price: number;
  subtotal: number;
  total_price?: number;
  options?: Record<string, unknown>;
}

export interface Order {
  id: string;
  order_number: string;
  store_id: string;
  store_name?: string;
  customer_name: string;
  customer_email: string;
  customer_phone: string;
  status: 'pending' | 'confirmed' | 'processing' | 'paid' | 'preparing' | 'ready' | 'shipped' | 'out_for_delivery' | 'delivered' | 'completed' | 'cancelled' | 'refunded' | 'failed';
  payment_status: 'pending' | 'processing' | 'paid' | 'failed' | 'refunded' | 'partially_refunded';
  delivery_method: 'delivery' | 'pickup' | 'digital';
  subtotal: number;
  discount: number;
  tax: number;
  delivery_fee: number;
  shipping_cost?: number;
  total: number;
  items: OrderItem[];
  items_count?: number;
  source?: string;
  delivery_address?: Record<string, unknown>;
  shipping_address?: Record<string, unknown>;
  tracking_code?: string;
  notes?: string;
  pix_code?: string;
  pix_qr_code?: string;
  pix_ticket_url?: string;
  payment_method?: string;
  payment_preference_id?: string;
  payment_url?: string;
  payment_link?: string;
  access_token?: string;
  init_point?: string;
  paid_at?: string;
  created_at: string;
  updated_at: string;
}

export interface OrderEvent {
  id: string;
  order_id: string;
  event_type: string;
  description: string;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export interface CreateOrder {
  customer_name: string;
  customer_email: string;
  customer_phone: string;
  items: Array<{
    product_id: string;
    quantity: number;
    options?: Record<string, unknown>;
  }>;
  delivery_method?: 'delivery' | 'pickup';
  delivery_address?: Record<string, unknown>;
  notes?: string;
}

// ============================================
// PAYMENT TYPES
// ============================================

export interface PaymentGateway {
  id: string;
  name: string;
  provider: string;
  is_active: boolean;
  config?: Record<string, unknown>;
}

export interface Payment {
  id: string;
  order_id: string;
  gateway_id: string;
  amount: number;
  currency: string;
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'refunded';
  payment_method?: string;
  payment_id?: string;
  pix_code?: string;
  pix_qr_code?: string;
  paid_at?: string;
  created_at: string;
}

// ============================================
// SCHEDULED MESSAGE TYPES
// ============================================

export interface ScheduledMessage {
  id: string;
  account_id: string;
  account_name?: string;
  to_number: string;
  contact_name?: string;
  message_type: 'text' | 'template' | 'image' | 'document' | 'interactive';
  message_text?: string;
  template_name?: string;
  media_url?: string;
  buttons?: Array<{ id: string; title: string }>;
  scheduled_at: string;
  timezone: string;
  status: 'pending' | 'processing' | 'sent' | 'failed' | 'cancelled';
  status_display?: string;
  sent_at?: string;
  error_message?: string;
  notes?: string;
  created_at: string;
}

export interface CreateScheduledMessage {
  account_id?: string;
  to_number: string;
  contact_name?: string;
  message_type: 'text' | 'template' | 'image' | 'document' | 'interactive';
  message_text?: string;
  template_name?: string;
  template_components?: unknown[];
  media_url?: string;
  buttons?: Array<{ id: string; title: string }>;
  scheduled_at: string;
  timezone?: string;
  notes?: string;
}

export interface ScheduledMessageStats {
  total_scheduled: number;
  pending: number;
  sent: number;
  failed: number;
  sent_today?: number;
  by_status: Record<string, number>;
  upcoming_count: number;
}

export interface CreateReportSchedule {
  name: string;
  report_type: string;
  frequency: 'daily' | 'weekly' | 'monthly';
  recipients: string[];
  day_of_week?: number;
  day_of_month?: number;
  hour?: number;
  timezone?: string;
}

// ============================================
// AUTOMATION DASHBOARD TYPES
// ============================================

export interface AutomationStats {
  period: { start: string; end: string };
  summary: {
    total_messages_sent: number;
    total_automations_triggered: number;
    conversion_rate: number;
    revenue_from_automations: number;
  };
  by_event_type: Record<AutoMessageEventType, {
    sent: number;
    delivered: number;
    read: number;
    converted: number;
    conversion_rate: number;
  }>;
  cart_recovery: {
    abandoned_carts: number;
    reminders_sent: number;
    recovered: number;
    recovery_rate: number;
    revenue_recovered: number;
  };
  payment_reminders: {
    pending_payments: number;
    reminders_sent: number;
    paid_after_reminder: number;
    conversion_rate: number;
  };
}

export interface AutomationSettings {
  cart_recovery: {
    enabled: boolean;
    reminder_30min: boolean;
    reminder_2h: boolean;
    reminder_24h: boolean;
    discount_code?: string;
  };
  payment_reminders: {
    enabled: boolean;
    reminder_30min: boolean;
    reminder_2h: boolean;
    auto_cancel_after_24h: boolean;
  };
  order_notifications: {
    enabled: boolean;
    on_confirmed: boolean;
    on_preparing: boolean;
    on_ready: boolean;
    on_out_for_delivery: boolean;
    on_delivered: boolean;
  };
  feedback_request: {
    enabled: boolean;
    delay_minutes: number;
  };
}
