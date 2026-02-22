/**
 * Instagram API Service
 * 
 * Gerencia todas as operações do Instagram:
 * - Contas (connect, sync, insights)
 * - Mídia (posts, stories, reels)
 * - Shopping (catálogos, produtos)
 * - Live (transmissões ao vivo)
 * - Direct (mensagens)
 */
import api from './api';
import { PaginatedResponse } from '@/types';

// ============================================================================
// TYPES
// ============================================================================

export interface InstagramAccount {
  id: string;
  platform: 'instagram' | 'facebook';
  username: string;
  instagram_business_id?: string;
  facebook_page_id?: string;
  followers_count: number;
  follows_count: number;
  media_count: number;
  profile_picture_url?: string;
  biography: string;
  website?: string;
  is_active: boolean;
  is_verified: boolean;
  last_sync_at?: string;
  created_at: string;
}

export interface InstagramMedia {
  id: string;
  account: string;
  instagram_media_id?: string;
  media_type: 'IMAGE' | 'VIDEO' | 'CAROUSEL_ALBUM' | 'REELS' | 'STORY' | 'LIVE';
  caption: string;
  media_url?: string;
  thumbnail_url?: string;
  permalink?: string;
  shortcode?: string;
  likes_count: number;
  comments_count: number;
  shares_count: number;
  saves_count: number;
  reach: number;
  impressions: number;
  status: 'PUBLISHED' | 'SCHEDULED' | 'DRAFT' | 'PROCESSING' | 'FAILED' | 'ARCHIVED';
  scheduled_at?: string;
  published_at?: string;
  has_product_tags: boolean;
  created_at: string;
}

export interface InstagramInsight {
  id: string;
  date: string;
  impressions: number;
  reach: number;
  profile_views: number;
  website_clicks: number;
  follower_count: number;
  followers_gained: number;
  followers_lost: number;
  engagement: number;
}

export interface InstagramCatalog {
  id: string;
  catalog_id: string;
  name: string;
  is_active: boolean;
  product_count?: number;
  created_at: string;
}

export interface InstagramProduct {
  id: string;
  product_id: string;
  name: string;
  description: string;
  price: number;
  currency: string;
  image_url: string;
  availability: string;
  is_active: boolean;
}

export interface InstagramLive {
  id: string;
  title: string;
  description: string;
  status: 'SCHEDULED' | 'LIVE' | 'ENDED' | 'CANCELLED';
  scheduled_at?: string;
  started_at?: string;
  ended_at?: string;
  viewers_count: number;
  max_viewers: number;
  comments_count: number;
  stream_url?: string;
  stream_key?: string;
}

export interface InstagramScheduledPost {
  id: string;
  media_type: 'IMAGE' | 'VIDEO' | 'CAROUSEL' | 'REELS' | 'STORY';
  caption: string;
  media_files: string[];
  schedule_time: string;
  timezone: string;
  status: 'PENDING' | 'PROCESSING' | 'PUBLISHED' | 'FAILED' | 'CANCELLED';
  product_tags: Array<{
    product_id: string;
    position_x: number;
    position_y: number;
  }>;
}

// ============================================================================
// ACCOUNTS
// ============================================================================

export const instagramAccountApi = {
  list: () => api.get<InstagramAccount[]>('/instagram/accounts/'),
  
  create: (data: Partial<InstagramAccount>) => 
    api.post<InstagramAccount>('/instagram/accounts/', data),
  
  get: (id: string) => 
    api.get<InstagramAccount>(`/instagram/accounts/${id}/`),
  
  update: (id: string, data: Partial<InstagramAccount>) => 
    api.patch<InstagramAccount>(`/instagram/accounts/${id}/`, data),
  
  delete: (id: string) => 
    api.delete(`/instagram/accounts/${id}/`),
  
  sync: (id: string) => 
    api.post<{ status: string; message: string }>(`/instagram/accounts/${id}/sync/`),
  
  getInsights: (id: string, days: number = 30) => 
    api.get<InstagramInsight[]>(`/instagram/accounts/${id}/insights/?days=${days}`),
};

// ============================================================================
// MEDIA (Posts, Stories, Reels)
// ============================================================================

export const instagramMediaApi = {
  list: (params?: { account?: string; media_type?: string }) => 
    api.get<PaginatedResponse<InstagramMedia>>('/instagram/media/', { params }),
  
  get: (id: string) => 
    api.get<InstagramMedia>(`/instagram/media/${id}/`),
  
  create: (data: Partial<InstagramMedia>) => 
    api.post<InstagramMedia>('/instagram/media/', data),
  
  update: (id: string, data: Partial<InstagramMedia>) => 
    api.patch<InstagramMedia>(`/instagram/media/${id}/`, data),
  
  delete: (id: string) => 
    api.delete(`/instagram/media/${id}/`),
  
  // Feed de posts
  getFeed: () => 
    api.get<InstagramMedia[]>('/instagram/media/feed/'),
  
  // Stories
  getStories: () => 
    api.get<InstagramMedia[]>('/instagram/media/stories/'),
  
  // Reels
  getReels: () => 
    api.get<InstagramMedia[]>('/instagram/media/reels/'),
  
  // Publicar
  publish: (id: string) => 
    api.post<{ status: string; id: string }>(`/instagram/media/${id}/publish/`),
  
  // Agendar
  schedule: (id: string, scheduleTime: string) => 
    api.post(`/instagram/media/${id}/schedule/`, { schedule_time: scheduleTime }),
  
  // Insights da mídia
  getInsights: (id: string) => 
    api.get(`/instagram/media/${id}/insights/`),
  
  // Comentários
  getComments: (id: string) => 
    api.get(`/instagram/media/${id}/comments/`),
};

// ============================================================================
// SHOPPING
// ============================================================================

export const instagramShoppingApi = {
  // Catálogos
  getCatalogs: (accountId: string) => 
    api.get<InstagramCatalog[]>(`/instagram/shopping/catalogs/?account_id=${accountId}`),
  
  // Produtos
  getProducts: (accountId: string, catalogId?: string) => 
    api.get<InstagramProduct[]>(`/instagram/shopping/products/?account_id=${accountId}${catalogId ? `&catalog_id=${catalogId}` : ''}`),
  
  // Tag de produto em mídia
  tagProduct: (accountId: string, data: {
    media_id: string;
    product_id: string;
    x: number;
    y: number;
  }) => api.post('/instagram/shopping/tag_product/', { account_id: accountId, ...data }),
};

// ============================================================================
// LIVE
// ============================================================================

export const instagramLiveApi = {
  list: (accountId: string) => 
    api.get<InstagramLive[]>(`/instagram/live/?account_id=${accountId}`),
  
  create: (accountId: string, data: Partial<InstagramLive>) => 
    api.post<InstagramLive>('/instagram/live/', { account: accountId, ...data }),
  
  get: (id: string) => 
    api.get<InstagramLive>(`/instagram/live/${id}/`),
  
  update: (id: string, data: Partial<InstagramLive>) => 
    api.patch<InstagramLive>(`/instagram/live/${id}/`, data),
  
  delete: (id: string) => 
    api.delete(`/instagram/live/${id}/`),
  
  // Iniciar live
  start: (id: string) => 
    api.post<{ stream_url: string; stream_key: string }>(`/instagram/live/${id}/start/`),
  
  // Finalizar live
  end: (id: string) => 
    api.post(`/instagram/live/${id}/end/`),
  
  // Comentários da live
  getComments: (id: string) => 
    api.get(`/instagram/live/${id}/comments/`),
};

// ============================================================================
// SCHEDULED POSTS
// ============================================================================

export const instagramScheduledPostApi = {
  list: (accountId: string) => 
    api.get<InstagramScheduledPost[]>(`/instagram/scheduled-posts/?account_id=${accountId}`),
  
  create: (data: Partial<InstagramScheduledPost>) => 
    api.post<InstagramScheduledPost>('/instagram/scheduled-posts/', data),
  
  get: (id: string) => 
    api.get<InstagramScheduledPost>(`/instagram/scheduled-posts/${id}/`),
  
  update: (id: string, data: Partial<InstagramScheduledPost>) => 
    api.patch<InstagramScheduledPost>(`/instagram/scheduled-posts/${id}/`, data),
  
  delete: (id: string) => 
    api.delete(`/instagram/scheduled-posts/${id}/`),
  
  // Cancelar post agendado
  cancel: (id: string) => 
    api.post(`/instagram/scheduled-posts/${id}/cancel/`),
};

// ============================================================================
// DIRECT MESSAGES (Já existe, mas atualizando)
// ============================================================================

export const instagramDirectApi = {
  // Conversas
  getConversations: (accountId: string) => 
    api.get(`/instagram/conversations/?account_id=${accountId}`),
  
  // Mensagens
  getMessages: (conversationId: string) => 
    api.get(`/instagram/conversations/${conversationId}/messages/`),
  
  // Enviar mensagem
  sendMessage: (conversationId: string, content: string) => 
    api.post(`/instagram/conversations/${conversationId}/send_message/`, { content }),
  
  // Marcar como lida
  markAsRead: (conversationId: string) => 
    api.post(`/instagram/conversations/${conversationId}/mark_as_read/`),
};

// ============================================================================
// LEGACY SERVICE (for backward compatibility with hooks)
// ============================================================================

export const instagramService = {
  // Accounts
  getAccounts: () => instagramAccountApi.list(),
  getAccount: (id: string) => instagramAccountApi.get(id),
  createAccount: (data: Partial<InstagramAccount>) => instagramAccountApi.create(data),
  updateAccount: (id: string, data: Partial<InstagramAccount>) => instagramAccountApi.update(id, data),
  deleteAccount: (id: string) => instagramAccountApi.delete(id),
  syncAccount: (id: string) => instagramAccountApi.sync(id),
  
  // Media
  getMedia: (accountId: string) => instagramMediaApi.list({ account: accountId }),
  createPost: (data: { account: string; caption?: string; media_urls: string[]; tags?: string[] }) => 
    instagramMediaApi.create(data as Partial<InstagramMedia>),
  createCarousel: (data: { account: string; caption?: string; media_urls: string[]; tags?: string[] }) =>
    instagramMediaApi.create({ ...data, media_type: 'CAROUSEL_ALBUM' } as Partial<InstagramMedia>),
  
  // Stories
  getStories: (accountId: string) => instagramMediaApi.getStories(),
  createStory: (data: { account: string; media_url: string; caption?: string }) =>
    instagramMediaApi.create({ ...data, media_type: 'STORY' } as Partial<InstagramMedia>),
  
  // Reels
  getReels: (accountId: string) => instagramMediaApi.getReels(),
  createReel: (data: { account: string; video_url: string; caption?: string; cover_url?: string }) =>
    instagramMediaApi.create({ ...data, media_type: 'REELS' } as Partial<InstagramMedia>),
  
  // Catalogs
  getCatalogs: (accountId: string) => instagramShoppingApi.getCatalogs(accountId),
  
  // Products
  getProducts: (catalogId: string) => instagramShoppingApi.getProducts(catalogId),
  createProduct: (data: { catalog: string; name: string; price: number; currency: string; image_url: string; description?: string }) =>
    api.post<InstagramProduct>('/instagram/shopping/products/', data),
  
  // Lives
  getLives: (accountId: string) => instagramLiveApi.list(accountId),
  createLive: (data: { account: string; title?: string; description?: string; scheduled_start?: string }) =>
    instagramLiveApi.create(data.account, data),
};

// Type aliases for backward compatibility
export type InstagramStory = InstagramMedia;
export type InstagramReel = InstagramMedia;
export type CreateInstagramAccount = Partial<InstagramAccount>;
export type InstagramAccountStats = { 
  total_accounts: number;
  active_accounts: number;
  total_followers: number;
  total_posts: number;
};
export type InstagramConversation = {
  id: string;
  account: string;
  participant_id: string;
  participant_username: string;
  last_message_at?: string;
  unread_count: number;
};
export type InstagramMessage = {
  id: string;
  conversation: string;
  content: string;
  direction: 'inbound' | 'outbound';
  sent_at: string;
};

// Export all
export default {
  accounts: instagramAccountApi,
  media: instagramMediaApi,
  shopping: instagramShoppingApi,
  live: instagramLiveApi,
  scheduledPosts: instagramScheduledPostApi,
  direct: instagramDirectApi,
};
