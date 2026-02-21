

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
  first_name: string;
  last_name: string;
  is_active: boolean;
  date_joined: string;
}

// ============================================
// MESSAGE TYPES
// ============================================

export interface Message {
  id: string;
  message_id: string;
  conversation_id: string;
  phone_number: string;
  text?: string;
  message_type: 'text' | 'image' | 'document' | 'audio' | 'video' | 'template' | 'interactive';
  media_url?: string;
  caption?: string;
  timestamp: string;
  direction: 'inbound' | 'outbound';
  status: 'sent' | 'delivered' | 'read' | 'failed' | 'pending';
}

export interface Conversation {
  id: string;
  phone_number: string;
  contact_name?: string;
  last_message?: string;
  last_message_at?: string;
  unread_count: number;
  status: 'open' | 'closed' | 'pending';
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
