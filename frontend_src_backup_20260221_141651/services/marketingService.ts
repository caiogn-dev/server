/**
 * Marketing Service
 * 
 * Handles email marketing, WhatsApp campaigns, and promotional activities.
 * Integrates with Resend for email delivery.
 */
import api from './api';
import logger from './logger';

const BASE_URL = '/marketing';

// =============================================================================
// TYPES
// =============================================================================

export interface EmailTemplate {
  id: string;
  store: string;
  name: string;
  slug: string;
  subject: string;
  preview_text?: string;
  html_content: string;
  text_content?: string;
  template_type: 'promotional' | 'transactional' | 'newsletter' | 'coupon' | 'welcome' | 'abandoned_cart' | 'order_confirmation' | 'custom';
  variables: string[]; // e.g., ['customer_name', 'coupon_code', 'discount_value']
  thumbnail_url?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface EmailTemplateInput {
  store: string;
  name: string;
  slug?: string;
  subject: string;
  preview_text?: string;
  html_content: string;
  text_content?: string;
  template_type: EmailTemplate['template_type'];
  variables?: string[];
  is_active?: boolean;
}

export interface EmailCampaign {
  id: string;
  store: string;
  name: string;
  template: string;
  template_name?: string;
  subject: string;
  from_name: string;
  from_email: string;
  reply_to?: string;
  status: 'draft' | 'scheduled' | 'sending' | 'sent' | 'paused' | 'cancelled';
  scheduled_at?: string;
  sent_at?: string;
  recipients_count: number;
  delivered_count: number;
  opened_count: number;
  clicked_count: number;
  bounced_count: number;
  unsubscribed_count: number;
  target_audience: 'all' | 'new_customers' | 'returning_customers' | 'inactive' | 'custom';
  custom_segment?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface EmailCampaignInput {
  store: string;
  name: string;
  template?: string | null;  // UUID of template, or null for custom content
  subject: string;
  html_content: string;      // Required: the actual HTML content
  text_content?: string;     // Optional plain text version
  from_name?: string;
  from_email?: string;
  reply_to?: string;
  scheduled_at?: string;
  audience_type?: 'all' | 'segment' | 'custom';
  audience_filters?: Record<string, unknown>;
  recipient_list?: Array<{ email: string; name?: string; variables?: Record<string, string> }>;
}

export interface WhatsAppCampaign {
  id: string;
  store: string;
  name: string;
  message_template: string;
  media_url?: string;
  status: 'draft' | 'scheduled' | 'sending' | 'sent' | 'paused' | 'cancelled';
  scheduled_at?: string;
  sent_at?: string;
  recipients_count: number;
  delivered_count: number;
  read_count: number;
  replied_count: number;
  target_audience: 'all' | 'new_customers' | 'returning_customers' | 'inactive' | 'custom';
  custom_segment?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface WhatsAppCampaignInput {
  store: string;
  name: string;
  message_template: string;
  media_url?: string;
  scheduled_at?: string;
  target_audience: WhatsAppCampaign['target_audience'];
  custom_segment?: Record<string, unknown>;
}

export interface MarketingStats {
  email: {
    total_campaigns: number;
    total_sent: number;
    total_delivered: number;
    total_opened: number;
    total_clicked: number;
    open_rate: number;
    click_rate: number;
  };
  whatsapp: {
    total_campaigns: number;
    total_sent: number;
    total_delivered: number;
    total_read: number;
    total_replied: number;
    delivery_rate: number;
    read_rate: number;
  };
  subscribers: {
    total: number;
    active: number;
    unsubscribed: number;
    new_this_month: number;
  };
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// =============================================================================
// PREDEFINED EMAIL TEMPLATES
// =============================================================================

export const EMAIL_TEMPLATE_PRESETS: Record<string, Partial<EmailTemplateInput>> = {
  coupon: {
    name: 'Cupom de Desconto',
    subject: '🎁 Presente especial para você: {{discount_value}}% OFF!',
    template_type: 'coupon',
    variables: ['customer_name', 'coupon_code', 'discount_value', 'expiry_date', 'store_name'],
    html_content: `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Cupom de Desconto</title>
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f4;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f4f4f4; padding: 40px 20px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
          <!-- Header -->
          <tr>
            <td style="background: linear-gradient(135deg, #722F37 0%, #8B3A42 100%); padding: 40px; text-align: center;">
              <h1 style="color: #ffffff; margin: 0; font-size: 28px;">🎁 Presente Especial!</h1>
            </td>
          </tr>
          <!-- Content -->
          <tr>
            <td style="padding: 40px;">
              <p style="font-size: 18px; color: #333; margin: 0 0 20px;">Olá, <strong>{{customer_name}}</strong>!</p>
              <p style="font-size: 16px; color: #666; line-height: 1.6; margin: 0 0 30px;">
                Preparamos um desconto exclusivo para você aproveitar em sua próxima compra na <strong>{{store_name}}</strong>!
              </p>
              <!-- Coupon Box -->
              <div style="background: linear-gradient(135deg, #722F37 0%, #8B3A42 100%); border-radius: 12px; padding: 30px; text-align: center; margin: 30px 0;">
                <p style="color: #ffffff; font-size: 14px; margin: 0 0 10px; text-transform: uppercase; letter-spacing: 2px;">Seu cupom</p>
                <p style="color: #ffffff; font-size: 36px; font-weight: bold; margin: 0; letter-spacing: 4px;">{{coupon_code}}</p>
                <p style="color: #ffffff; font-size: 48px; font-weight: bold; margin: 20px 0 0;">{{discount_value}}% OFF</p>
              </div>
              <p style="font-size: 14px; color: #999; text-align: center; margin: 20px 0;">
                Válido até: <strong>{{expiry_date}}</strong>
              </p>
              <!-- CTA Button -->
              <div style="text-align: center; margin: 30px 0;">
                <a href="{{store_url}}" style="display: inline-block; background: #722F37; color: #ffffff; text-decoration: none; padding: 16px 40px; border-radius: 8px; font-size: 16px; font-weight: bold;">
                  Usar Meu Cupom
                </a>
              </div>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="background-color: #f8f8f8; padding: 30px; text-align: center;">
              <p style="font-size: 12px; color: #999; margin: 0;">
                © {{year}} {{store_name}}. Todos os direitos reservados.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
    `.trim(),
  },
  
  welcome: {
    name: 'Boas-vindas',
    subject: '👋 Bem-vindo(a) à {{store_name}}!',
    template_type: 'welcome',
    variables: ['customer_name', 'store_name', 'store_url'],
    html_content: `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f4;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f4f4f4; padding: 40px 20px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 16px; overflow: hidden;">
          <tr>
            <td style="background: linear-gradient(135deg, #722F37 0%, #8B3A42 100%); padding: 40px; text-align: center;">
              <h1 style="color: #ffffff; margin: 0;">👋 Bem-vindo(a)!</h1>
            </td>
          </tr>
          <tr>
            <td style="padding: 40px;">
              <p style="font-size: 18px; color: #333;">Olá, <strong>{{customer_name}}</strong>!</p>
              <p style="font-size: 16px; color: #666; line-height: 1.6;">
                É um prazer ter você conosco! Agora você faz parte da família <strong>{{store_name}}</strong>.
              </p>
              <p style="font-size: 16px; color: #666; line-height: 1.6;">
                Prepare-se para receber ofertas exclusivas, novidades e muito mais!
              </p>
              <div style="text-align: center; margin: 30px 0;">
                <a href="{{store_url}}" style="display: inline-block; background: #722F37; color: #ffffff; text-decoration: none; padding: 16px 40px; border-radius: 8px; font-size: 16px; font-weight: bold;">
                  Conhecer a Loja
                </a>
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
    `.trim(),
  },

  promotion: {
    name: 'Promoção',
    subject: '🔥 {{promotion_title}} - Só por tempo limitado!',
    template_type: 'promotional',
    variables: ['customer_name', 'promotion_title', 'promotion_description', 'store_name', 'store_url'],
    html_content: `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f4;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f4f4f4; padding: 40px 20px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 16px; overflow: hidden;">
          <tr>
            <td style="background: linear-gradient(135deg, #FF6B6B 0%, #FF8E53 100%); padding: 40px; text-align: center;">
              <h1 style="color: #ffffff; margin: 0; font-size: 32px;">🔥 PROMOÇÃO!</h1>
              <p style="color: #ffffff; font-size: 24px; margin: 10px 0 0;">{{promotion_title}}</p>
            </td>
          </tr>
          <tr>
            <td style="padding: 40px;">
              <p style="font-size: 18px; color: #333;">Olá, <strong>{{customer_name}}</strong>!</p>
              <p style="font-size: 16px; color: #666; line-height: 1.6;">
                {{promotion_description}}
              </p>
              <div style="text-align: center; margin: 30px 0;">
                <a href="{{store_url}}" style="display: inline-block; background: linear-gradient(135deg, #FF6B6B 0%, #FF8E53 100%); color: #ffffff; text-decoration: none; padding: 16px 40px; border-radius: 8px; font-size: 16px; font-weight: bold;">
                  Aproveitar Agora
                </a>
              </div>
              <p style="font-size: 12px; color: #999; text-align: center;">
                *Promoção por tempo limitado. Sujeito a disponibilidade.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
    `.trim(),
  },

  order_confirmation: {
    name: 'Confirmação de Pedido',
    subject: '✅ Pedido #{{order_number}} confirmado!',
    template_type: 'order_confirmation',
    variables: ['customer_name', 'order_number', 'order_total', 'order_items', 'delivery_address', 'store_name'],
    html_content: `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f4;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f4f4f4; padding: 40px 20px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 16px; overflow: hidden;">
          <tr>
            <td style="background: linear-gradient(135deg, #10B981 0%, #059669 100%); padding: 40px; text-align: center;">
              <h1 style="color: #ffffff; margin: 0;">✅ Pedido Confirmado!</h1>
              <p style="color: #ffffff; font-size: 20px; margin: 10px 0 0;">#{{order_number}}</p>
            </td>
          </tr>
          <tr>
            <td style="padding: 40px;">
              <p style="font-size: 18px; color: #333;">Olá, <strong>{{customer_name}}</strong>!</p>
              <p style="font-size: 16px; color: #666; line-height: 1.6;">
                Seu pedido foi confirmado e está sendo preparado com carinho!
              </p>
              
              <div style="background: #f8f8f8; border-radius: 8px; padding: 20px; margin: 20px 0;">
                <h3 style="margin: 0 0 15px; color: #333;">Resumo do Pedido</h3>
                {{order_items}}
                <hr style="border: none; border-top: 1px solid #ddd; margin: 15px 0;">
                <p style="font-size: 18px; font-weight: bold; color: #333; margin: 0;">
                  Total: R$ {{order_total}}
                </p>
              </div>

              <div style="background: #f8f8f8; border-radius: 8px; padding: 20px; margin: 20px 0;">
                <h3 style="margin: 0 0 10px; color: #333;">📍 Endereço de Entrega</h3>
                <p style="color: #666; margin: 0;">{{delivery_address}}</p>
              </div>
            </td>
          </tr>
          <tr>
            <td style="background-color: #f8f8f8; padding: 30px; text-align: center;">
              <p style="font-size: 12px; color: #999; margin: 0;">
                Obrigado por comprar na {{store_name}}!
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
    `.trim(),
  },

  abandoned_cart: {
    name: 'Carrinho Abandonado',
    subject: '🛒 Você esqueceu algo no carrinho!',
    template_type: 'abandoned_cart',
    variables: ['customer_name', 'cart_items', 'cart_total', 'store_name', 'store_url'],
    html_content: `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f4;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f4f4f4; padding: 40px 20px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 16px; overflow: hidden;">
          <tr>
            <td style="background: linear-gradient(135deg, #722F37 0%, #8B3A42 100%); padding: 40px; text-align: center;">
              <h1 style="color: #ffffff; margin: 0;">🛒 Esqueceu de algo?</h1>
            </td>
          </tr>
          <tr>
            <td style="padding: 40px;">
              <p style="font-size: 18px; color: #333;">Olá, <strong>{{customer_name}}</strong>!</p>
              <p style="font-size: 16px; color: #666; line-height: 1.6;">
                Notamos que você deixou alguns itens no carrinho. Eles ainda estão esperando por você!
              </p>
              
              <div style="background: #f8f8f8; border-radius: 8px; padding: 20px; margin: 20px 0;">
                {{cart_items}}
                <hr style="border: none; border-top: 1px solid #ddd; margin: 15px 0;">
                <p style="font-size: 18px; font-weight: bold; color: #333; margin: 0;">
                  Total: R$ {{cart_total}}
                </p>
              </div>

              <div style="text-align: center; margin: 30px 0;">
                <a href="{{store_url}}" style="display: inline-block; background: #722F37; color: #ffffff; text-decoration: none; padding: 16px 40px; border-radius: 8px; font-size: 16px; font-weight: bold;">
                  Ver Cardápio
                </a>
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
    `.trim(),
  },
};

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

const generateSlug = (name: string): string => {
  return name
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
};

// =============================================================================
// EMAIL TEMPLATES API
// =============================================================================

export const emailTemplatesApi = {
  async list(storeId: string): Promise<EmailTemplate[]> {
    try {
      // Try to fetch from API first
      const response = await api.get<{ results?: EmailTemplate[] } | EmailTemplate[]>(`${BASE_URL}/templates/`, {
        params: { store: storeId }
      });
      
      const templates = Array.isArray(response.data) 
        ? response.data 
        : response.data.results || [];
      
      // If API returns templates, use them
      if (templates.length > 0) {
        return templates;
      }
      
      // Fallback to preset templates if no custom templates exist
      return emailTemplatesApi.getPresetTemplates(storeId);
    } catch (error) {
      logger.warn('API not available, using preset templates', { error: String(error) });
      // Fallback to preset templates
      return emailTemplatesApi.getPresetTemplates(storeId);
    }
  },

  getPresetTemplates(storeId: string): EmailTemplate[] {
    return Object.entries(EMAIL_TEMPLATE_PRESETS).map(([key, preset]) => ({
      id: `preset-${key}`,
      store: storeId,
      name: preset.name || key,
      slug: key,
      subject: preset.subject || '',
      html_content: preset.html_content || '',
      template_type: preset.template_type || 'custom',
      variables: preset.variables || [],
      is_active: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }));
  },

  async get(id: string): Promise<EmailTemplate> {
    const response = await api.get<EmailTemplate>(`${BASE_URL}/templates/${id}/`);
    return response.data;
  },

  async create(data: EmailTemplateInput): Promise<EmailTemplate> {
    const payload = { ...data, slug: data.slug || generateSlug(data.name) };
    const response = await api.post<EmailTemplate>(`${BASE_URL}/templates/`, payload);
    return response.data;
  },

  async update(id: string, data: Partial<EmailTemplateInput>): Promise<EmailTemplate> {
    const response = await api.patch<EmailTemplate>(`${BASE_URL}/templates/${id}/`, data);
    return response.data;
  },

  async delete(id: string): Promise<void> {
    await api.delete(`${BASE_URL}/templates/${id}/`);
  },

  async preview(id: string, variables: Record<string, string>): Promise<string> {
    const response = await api.post<{ html: string }>(`${BASE_URL}/templates/${id}/preview/`, { variables });
    return response.data.html;
  },

  async sendTest(id: string, email: string, variables: Record<string, string>): Promise<void> {
    await api.post(`${BASE_URL}/templates/${id}/send-test/`, { email, variables });
  },
};

// =============================================================================
// EMAIL CAMPAIGNS API
// =============================================================================

export const emailCampaignsApi = {
  async list(storeId: string): Promise<EmailCampaign[]> {
    try {
      const response = await api.get<{ results?: EmailCampaign[] } | EmailCampaign[]>(`${BASE_URL}/campaigns/`, {
        params: { store: storeId }
      });
      return Array.isArray(response.data) 
        ? response.data 
        : response.data.results || [];
    } catch (error) {
      logger.warn('Failed to fetch campaigns', { error: String(error) });
      return [];
    }
  },

  async get(id: string): Promise<EmailCampaign> {
    const response = await api.get<EmailCampaign>(`${BASE_URL}/campaigns/${id}/`);
    return response.data;
  },

  async create(data: EmailCampaignInput): Promise<EmailCampaign> {
    // Clean up the data - remove null/undefined/empty template
    const cleanData: Record<string, unknown> = { ...data };
    
    // Remove template if it's not a valid UUID
    if (!cleanData.template || 
        cleanData.template === null || 
        (typeof cleanData.template === 'string' && 
         (cleanData.template.startsWith('preset-') || cleanData.template === ''))) {
      delete cleanData.template;
    }
    
    // Remove empty strings and undefined values
    Object.keys(cleanData).forEach(key => {
      if (cleanData[key] === '' || cleanData[key] === undefined || cleanData[key] === null) {
        delete cleanData[key];
      }
    });
    
    logger.info('Creating email campaign', { data: cleanData });
    
    const response = await api.post<EmailCampaign>(`${BASE_URL}/campaigns/`, cleanData);
    return response.data;
  },

  async update(id: string, data: Partial<EmailCampaignInput>): Promise<EmailCampaign> {
    const response = await api.patch<EmailCampaign>(`${BASE_URL}/campaigns/${id}/`, data);
    return response.data;
  },

  async delete(id: string): Promise<void> {
    await api.delete(`${BASE_URL}/campaigns/${id}/`);
  },

  async send(id: string): Promise<{ success: boolean; sent?: number; failed?: number; error?: string }> {
    const response = await api.post<{ success: boolean; sent?: number; failed?: number; error?: string }>(
      `${BASE_URL}/campaigns/${id}/send/`
    );
    return response.data;
  },

  async schedule(id: string, scheduledAt: string): Promise<EmailCampaign> {
    const response = await api.post<EmailCampaign>(`${BASE_URL}/campaigns/${id}/schedule/`, {
      scheduled_at: scheduledAt
    });
    return response.data;
  },

  async pause(id: string): Promise<EmailCampaign> {
    const response = await api.post<EmailCampaign>(`${BASE_URL}/campaigns/${id}/pause/`);
    return response.data;
  },

  async cancel(id: string): Promise<EmailCampaign> {
    const response = await api.post<EmailCampaign>(`${BASE_URL}/campaigns/${id}/cancel/`);
    return response.data;
  },

  async getRecipients(id: string): Promise<{ email: string; name: string; status: string }[]> {
    const response = await api.get<{ email: string; name: string; status: string }[]>(
      `${BASE_URL}/campaigns/${id}/recipients/`
    );
    return response.data;
  },
};

// =============================================================================
// WHATSAPP CAMPAIGNS API (usa /campaigns/ endpoint)
// =============================================================================

export const whatsappCampaignsApi = {
  async list(storeId: string): Promise<PaginatedResponse<WhatsAppCampaign>> {
    const response = await api.get<PaginatedResponse<WhatsAppCampaign>>('/campaigns/campaigns/', {
      params: { store: storeId }
    });
    return response.data;
  },

  async get(id: string): Promise<WhatsAppCampaign> {
    const response = await api.get<WhatsAppCampaign>(`/campaigns/campaigns/${id}/`);
    return response.data;
  },

  async create(data: WhatsAppCampaignInput): Promise<WhatsAppCampaign> {
    const response = await api.post<WhatsAppCampaign>('/campaigns/campaigns/', data);
    return response.data;
  },

  async update(id: string, data: Partial<WhatsAppCampaignInput>): Promise<WhatsAppCampaign> {
    const response = await api.patch<WhatsAppCampaign>(`/campaigns/campaigns/${id}/`, data);
    return response.data;
  },

  async delete(id: string): Promise<void> {
    await api.delete(`/campaigns/campaigns/${id}/`);
  },

  async send(id: string): Promise<void> {
    await api.post(`/campaigns/campaigns/${id}/start/`);
  },
};

// =============================================================================
// MARKETING STATS API
// =============================================================================

export const marketingStatsApi = {
  async get(storeId: string): Promise<MarketingStats> {
    try {
      const response = await api.get(`${BASE_URL}/stats/`, {
        params: { store: storeId }
      });
      
      // Map API response to our format
      const data = response.data;
      return {
        email: {
          total_campaigns: data.campaigns?.total || 0,
          total_sent: data.emails?.sent || 0,
          total_delivered: data.emails?.delivered || 0,
          total_opened: data.emails?.opened || 0,
          total_clicked: data.emails?.clicked || 0,
          open_rate: data.rates?.open_rate || 0,
          click_rate: data.rates?.click_rate || 0,
        },
        whatsapp: {
          total_campaigns: 0,
          total_sent: 0,
          total_delivered: 0,
          total_read: 0,
          total_replied: 0,
          delivery_rate: 0,
          read_rate: 0,
        },
        subscribers: {
          total: data.subscribers?.total || 0,
          active: data.subscribers?.active || 0,
          unsubscribed: (data.subscribers?.total || 0) - (data.subscribers?.active || 0),
          new_this_month: data.subscribers?.new_last_30_days || 0,
        },
      };
    } catch (error) {
      logger.warn('Error fetching marketing stats:', { error: String(error) });
      // Return empty stats if endpoint doesn't exist
      return {
        email: {
          total_campaigns: 0,
          total_sent: 0,
          total_delivered: 0,
          total_opened: 0,
          total_clicked: 0,
          open_rate: 0,
          click_rate: 0,
        },
        whatsapp: {
          total_campaigns: 0,
          total_sent: 0,
          total_delivered: 0,
          total_read: 0,
          total_replied: 0,
          delivery_rate: 0,
          read_rate: 0,
        },
        subscribers: {
          total: 0,
          active: 0,
          unsubscribed: 0,
          new_this_month: 0,
        },
      };
    }
  },
};

// =============================================================================
// QUICK ACTIONS API
// =============================================================================

export interface SendCouponEmailParams {
  store: string;
  to_email: string;
  customer_name: string;
  coupon_code: string;
  discount_value: string;
  expiry_date?: string;
}

export interface SendWelcomeEmailParams {
  store: string;
  to_email: string;
  customer_name: string;
}

export const quickActionsApi = {
  async sendCouponEmail(params: SendCouponEmailParams): Promise<{ success: boolean; id?: string; error?: string }> {
    try {
      const response = await api.post<{ success: boolean; id?: string; error?: string }>(
        `${BASE_URL}/actions/send_coupon/`,
        params
      );
      return response.data;
    } catch (error: unknown) {
      const err = error as { response?: { data?: { error?: string } } };
      logger.error('Failed to send coupon email', { error: String(error) });
      return { success: false, error: err.response?.data?.error || 'Erro ao enviar email' };
    }
  },

  async sendWelcomeEmail(params: SendWelcomeEmailParams): Promise<{ success: boolean; id?: string; error?: string }> {
    try {
      const response = await api.post<{ success: boolean; id?: string; error?: string }>(
        `${BASE_URL}/actions/send_welcome/`,
        params
      );
      return response.data;
    } catch (error: unknown) {
      const err = error as { response?: { data?: { error?: string } } };
      logger.error('Failed to send welcome email', { error: String(error) });
      return { success: false, error: err.response?.data?.error || 'Erro ao enviar email' };
    }
  },
};

// =============================================================================
// SUBSCRIBERS API
// =============================================================================

export interface Subscriber {
  id: string;
  store: string;
  email: string;
  name: string;
  phone?: string;
  status: 'active' | 'unsubscribed' | 'bounced' | 'complained';
  tags: string[];
  source?: string;
  total_orders: number;
  total_spent: number;
  accepts_marketing: boolean;
  subscribed_at: string;
  created_at: string;
}

export const subscribersApi = {
  /**
   * List all customers (aggregated from orders + subscribers)
   * This is the main endpoint for getting contacts for campaigns
   */
  async list(storeId: string, filters?: { status?: string; tags?: string[]; search?: string }): Promise<Subscriber[]> {
    try {
      const params: Record<string, string | string[]> = { store: storeId };
      if (filters?.status) params.status = filters.status;
      if (filters?.search) params.search = filters.search;
      
      // Use the unified customers endpoint that aggregates from orders + subscribers
      const response = await api.get<{ results?: Subscriber[]; count?: number } | Subscriber[]>(
        `${BASE_URL}/customers/`, 
        { params }
      );
      
      const results = Array.isArray(response.data) 
        ? response.data 
        : response.data.results || [];
      
      logger.info('Fetched customers', { count: results.length });
      return results;
    } catch (error) {
      logger.warn('Failed to fetch customers, trying subscribers fallback', { error: String(error) });
      
      // Fallback to subscribers endpoint
      try {
        const params: Record<string, string | string[]> = { store: storeId };
        if (filters?.status) params.status = filters.status;
        
        const response = await api.get<{ results?: Subscriber[] } | Subscriber[]>(
          `${BASE_URL}/subscribers/`, 
          { params }
        );
        return Array.isArray(response.data) 
          ? response.data 
          : response.data.results || [];
      } catch {
        return [];
      }
    }
  },
  
  async count(storeId: string, status?: string): Promise<number> {
    try {
      const params: Record<string, string> = { store: storeId };
      if (status) params.status = status;
      
      const response = await api.get<{ count: number }>(`${BASE_URL}/customers/count/`, { params });
      return response.data.count;
    } catch {
      // Fallback: get list and count
      const list = await this.list(storeId, { status });
      return list.length;
    }
  },

  async create(data: Partial<Subscriber>): Promise<Subscriber> {
    // Create in subscribers table
    const response = await api.post<Subscriber>(`${BASE_URL}/subscribers/`, data);
    return response.data;
  },

  async importCsv(storeId: string, contacts: { email: string; name?: string; phone?: string }[]): Promise<{ created: number; updated: number; total: number }> {
    const response = await api.post<{ created: number; updated: number; total: number }>(
      `${BASE_URL}/subscribers/import_csv/`,
      { store: storeId, contacts }
    );
    return response.data;
  },

  async unsubscribe(id: string): Promise<Subscriber> {
    const response = await api.post<Subscriber>(`${BASE_URL}/subscribers/${id}/unsubscribe/`);
    return response.data;
  },
};

// =============================================================================
// COMBINED SERVICE
// =============================================================================

export const marketingService = {
  emailTemplates: emailTemplatesApi,
  emailCampaigns: emailCampaignsApi,
  whatsappCampaigns: whatsappCampaignsApi,
  stats: marketingStatsApi,
  quickActions: quickActionsApi,
  subscribers: subscribersApi,
  presets: EMAIL_TEMPLATE_PRESETS,
};

export default marketingService;


// =============================================================================
// EMAIL AUTOMATION API
// =============================================================================

export interface EmailAutomation {
  id: string;
  store: string;
  name: string;
  description: string;
  trigger_type: string;
  trigger_type_display: string;
  subject: string;
  html_content: string;
  template?: string;
  template_name?: string;
  delay_minutes: number;
  is_active: boolean;
  conditions: Record<string, unknown>;
  total_sent: number;
  total_opened: number;
  total_clicked: number;
  created_at: string;
  updated_at: string;
}

export interface EmailAutomationLog {
  id: string;
  automation: string;
  automation_name: string;
  trigger_type: string;
  recipient_email: string;
  recipient_name: string;
  status: 'pending' | 'sent' | 'failed' | 'opened' | 'clicked';
  trigger_data: Record<string, unknown>;
  scheduled_at?: string;
  sent_at?: string;
  opened_at?: string;
  error_message?: string;
  created_at: string;
}

export interface TriggerType {
  value: string;
  label: string;
}

export const automationsApi = {
  async list(storeId: string): Promise<EmailAutomation[]> {
    try {
      const response = await api.get<{ results?: EmailAutomation[] } | EmailAutomation[]>(
        `${BASE_URL}/automations/`,
        { params: { store: storeId } }
      );
      return Array.isArray(response.data) 
        ? response.data 
        : response.data.results || [];
    } catch (error) {
      logger.warn('Failed to fetch automations', { error: String(error) });
      return [];
    }
  },

  async get(id: string): Promise<EmailAutomation | null> {
    try {
      const response = await api.get<EmailAutomation>(`${BASE_URL}/automations/${id}/`);
      return response.data;
    } catch {
      return null;
    }
  },

  async create(data: Partial<EmailAutomation>): Promise<EmailAutomation> {
    const response = await api.post<EmailAutomation>(`${BASE_URL}/automations/`, data);
    return response.data;
  },

  async update(id: string, data: Partial<EmailAutomation>): Promise<EmailAutomation> {
    const response = await api.patch<EmailAutomation>(`${BASE_URL}/automations/${id}/`, data);
    return response.data;
  },

  async delete(id: string): Promise<void> {
    await api.delete(`${BASE_URL}/automations/${id}/`);
  },

  async toggle(id: string): Promise<EmailAutomation> {
    const response = await api.post<EmailAutomation>(`${BASE_URL}/automations/${id}/toggle/`);
    return response.data;
  },

  async getTriggerTypes(): Promise<TriggerType[]> {
    try {
      const response = await api.get<TriggerType[]>(`${BASE_URL}/automations/trigger_types/`);
      return response.data;
    } catch {
      // Return default trigger types if API fails
      return [
        { value: 'new_user', label: 'Novo Usuário' },
        { value: 'welcome', label: 'Boas-vindas' },
        { value: 'order_confirmed', label: 'Pedido Confirmado' },
        { value: 'order_preparing', label: 'Pedido em Preparo' },
        { value: 'order_shipped', label: 'Pedido Enviado' },
        { value: 'order_delivered', label: 'Pedido Entregue' },
        { value: 'order_cancelled', label: 'Pedido Cancelado' },
        { value: 'payment_confirmed', label: 'Pagamento Confirmado' },
        { value: 'payment_failed', label: 'Pagamento Falhou' },
        { value: 'cart_abandoned', label: 'Carrinho Abandonado' },
        { value: 'coupon_sent', label: 'Cupom Enviado' },
        { value: 'birthday', label: 'Aniversário' },
        { value: 'review_request', label: 'Solicitar Avaliação' },
      ];
    }
  },

  async getLogs(automationId: string): Promise<EmailAutomationLog[]> {
    try {
      const response = await api.get<EmailAutomationLog[]>(
        `${BASE_URL}/automations/${automationId}/logs/`
      );
      return response.data;
    } catch {
      return [];
    }
  },

  async test(automationId: string, email: string): Promise<{ success: boolean; error?: string }> {
    const response = await api.post<{ success: boolean; error?: string }>(
      `${BASE_URL}/automations/test/`,
      { automation_id: automationId, email }
    );
    return response.data;
  },

  async trigger(
    storeId: string,
    triggerType: string,
    recipientEmail: string,
    recipientName?: string,
    context?: Record<string, unknown>
  ): Promise<{ success: boolean; error?: string }> {
    const response = await api.post<{ success: boolean; error?: string }>(
      `${BASE_URL}/automations/trigger/`,
      {
        store: storeId,
        trigger_type: triggerType,
        recipient_email: recipientEmail,
        recipient_name: recipientName || '',
        context: context || {},
      }
    );
    return response.data;
  },
};

// =============================================================================
// TEMPLATE VARIABLES API
// =============================================================================

export interface TemplateVariable {
  name: string;
  description: string;
  example: string;
}

export interface TemplateVariableCategory {
  description: string;
  variables: TemplateVariable[];
}

export interface TemplateVariables {
  customer: TemplateVariableCategory;
  store: TemplateVariableCategory;
  order: TemplateVariableCategory;
  coupon: TemplateVariableCategory;
  promotion: TemplateVariableCategory;
}

export interface SampleCustomer {
  email: string;
  name: string;
  first_name: string;
  phone: string;
}

export interface PreviewResult {
  preview_html: string;
  variables_used: Record<string, string>;
}

export const templateVariablesApi = {
  /**
   * Get all available template variables with descriptions
   */
  async getAvailable(): Promise<TemplateVariables> {
    try {
      const response = await api.get<TemplateVariables>(`${BASE_URL}/variables/available/`);
      return response.data;
    } catch {
      // Return default variables if API fails
      return {
        customer: {
          description: 'Variáveis do cliente (preenchidas automaticamente)',
          variables: [
            { name: 'customer_name', description: 'Nome completo do cliente', example: 'João Silva' },
            { name: 'first_name', description: 'Primeiro nome do cliente', example: 'João' },
            { name: 'email', description: 'Email do cliente', example: 'joao@email.com' },
            { name: 'phone', description: 'Telefone do cliente', example: '(11) 99999-9999' },
          ]
        },
        store: {
          description: 'Variáveis da loja',
          variables: [
            { name: 'store_name', description: 'Nome da loja', example: 'Pastita' },
            { name: 'store_url', description: 'URL da loja', example: 'https://pastita.com.br' },
            { name: 'year', description: 'Ano atual', example: '2026' },
          ]
        },
        order: {
          description: 'Variáveis de pedido (para automações de pedido)',
          variables: [
            { name: 'order_number', description: 'Número do pedido', example: 'PAS-2026-001' },
            { name: 'order_total', description: 'Total do pedido', example: '89.90' },
            { name: 'order_status', description: 'Status do pedido', example: 'confirmed' },
            { name: 'tracking_code', description: 'Código de rastreio', example: 'BR123456789' },
          ]
        },
        coupon: {
          description: 'Variáveis de cupom',
          variables: [
            { name: 'coupon_code', description: 'Código do cupom', example: 'DESCONTO10' },
            { name: 'discount_value', description: 'Valor do desconto', example: '10%' },
            { name: 'expiry_date', description: 'Data de expiração', example: '31/12/2026' },
          ]
        },
        promotion: {
          description: 'Variáveis de promoção',
          variables: [
            { name: 'promotion_title', description: 'Título da promoção', example: 'Black Friday' },
            { name: 'promotion_description', description: 'Descrição da promoção', example: 'Até 50% OFF' },
          ]
        }
      };
    }
  },

  /**
   * Generate a preview of a template with sample data
   */
  async preview(htmlContent: string, storeId?: string, customerEmail?: string): Promise<PreviewResult> {
    try {
      const response = await api.post<PreviewResult>(`${BASE_URL}/variables/preview/`, {
        html_content: htmlContent,
        store: storeId,
        customer_email: customerEmail,
      });
      return response.data;
    } catch {
      // Fallback: do client-side replacement with sample data
      const variables: Record<string, string> = {
        customer_name: 'Cliente Exemplo',
        name: 'Cliente Exemplo',
        first_name: 'Cliente',
        email: 'cliente@exemplo.com',
        phone: '(11) 99999-9999',
        store_name: 'Pastita',
        store_url: 'https://pastita.com.br',
        year: new Date().getFullYear().toString(),
        order_number: 'PAS-2026-001',
        order_total: '89.90',
        order_status: 'confirmed',
        tracking_code: 'BR123456789',
        coupon_code: 'DESCONTO10',
        discount_value: '10%',
        expiry_date: '31/12/2026',
        promotion_title: 'Promoção Especial',
        promotion_description: 'Aproveite descontos incríveis!',
      };

      let previewHtml = htmlContent;
      Object.entries(variables).forEach(([key, value]) => {
        previewHtml = previewHtml.replace(new RegExp(`\\{\\{\\s*${key}\\s*\\}\\}`, 'g'), value);
      });

      return { preview_html: previewHtml, variables_used: variables };
    }
  },

  /**
   * Get a sample customer for preview
   */
  async getSampleCustomer(storeId?: string): Promise<SampleCustomer> {
    try {
      const params = storeId ? { store: storeId } : {};
      const response = await api.get<SampleCustomer>(`${BASE_URL}/variables/sample_customer/`, { params });
      return response.data;
    } catch {
      return {
        email: 'cliente@exemplo.com',
        name: 'Cliente Exemplo',
        first_name: 'Cliente',
        phone: '(11) 99999-9999',
      };
    }
  },
};
