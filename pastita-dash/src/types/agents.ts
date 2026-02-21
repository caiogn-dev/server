/**
 * Types for Langchain AI Agents
 * Replaces Langflow types with native Langchain implementation
 */

// Import from services to avoid duplication
import { AgentProvider, AgentStatus, ProcessMessageRequest, ProcessMessageResponse } from '../services/agents';

// Re-export from services
export type { AgentProvider, AgentStatus, ProcessMessageRequest, ProcessMessageResponse };

// Message role types
export type MessageRole = 'user' | 'assistant' | 'system';

/**
 * AI Agent configuration
 */
export interface Agent {
  id: string;
  name: string;
  description: string;
  provider: AgentProvider;
  model_name: string;
  base_url?: string;
  temperature: number;
  max_tokens: number;
  timeout: number;
  system_prompt: string;
  context_prompt: string;
  status: AgentStatus;
  use_memory: boolean;
  memory_ttl: number;
  accounts?: WhatsAppAccountMinimal[];
  created_at: string;
  updated_at: string;
}

/**
 * Minimal WhatsApp account info for agent association
 */
export interface WhatsAppAccountMinimal {
  id: string;
  name: string;
  phone_number: string;
  status: string;
}

/**
 * Agent list item (subset of fields)
 */
export interface AgentListItem {
  id: string;
  name: string;
  description: string;
  provider: AgentProvider;
  model_name: string;
  status: AgentStatus;
  temperature: number;
  max_tokens: number;
  use_memory: boolean;
  created_at: string;
  updated_at: string;
}

/**
 * Agent creation/update payload
 * Note: api_key is handled by backend, not sent from frontend
 */
export interface AgentCreateInput {
  name: string;
  description?: string;
  provider: AgentProvider;
  model_name: string;
  // api_key is NOT included - managed by backend
  base_url?: string;
  temperature?: number;
  max_tokens?: number;
  timeout?: number;
  system_prompt: string;
  context_prompt?: string;
  status?: AgentStatus;
  use_memory?: boolean;
  memory_ttl?: number;
  accounts?: string[];
}

export interface AgentUpdateInput extends Partial<AgentCreateInput> {
  id: string;
}

/**
 * Agent message in a conversation
 */
export interface AgentMessage {
  id: string;
  role: MessageRole;
  content: string;
  tokens_used?: number;
  response_time_ms?: number;
  created_at: string;
}

/**
 * Agent conversation session
 */
export interface AgentConversation {
  id: string;
  session_id: string;
  agent?: AgentListItem;
  phone_number: string;
  message_count: number;
  last_message_at: string;
  messages?: AgentMessage[];
  created_at: string;
}

/**
 * Agent statistics
 */
export interface AgentStats {
  total_conversations: number;
  total_messages: number;
  avg_response_time_ms: number;
  active_sessions: number;
}

/**
 * Conversation history from Redis memory
 */
export interface ConversationHistory {
  session_id: string;
  messages: Array<{
    type: 'human' | 'ai' | 'system';
    content: string;
    timestamp?: string;
  }>;
}

/**
 * Agent filters for listing
 */
export interface AgentFilters {
  status?: AgentStatus;
  provider?: AgentProvider;
  search?: string;
}

/**
 * Paginated response
 */
export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// Note: PROVIDER_CONFIGS and DEFAULT_AGENT_VALUES are now in services/agents.ts
// to avoid duplication. Import them from there:
// import { PROVIDER_CONFIGS, DEFAULT_AGENT_VALUES } from '../services/agents';
