import api from './api';

// Provider configurations - synced with backend
// IMPORTANT: defaultBaseUrl is DEPRECATED - use fetchProviderConfig() to get base URLs from backend
// This ensures the frontend always uses the correct URLs configured on the server
export const PROVIDER_CONFIGS = {
  kimi: {
    name: 'Kimi (Moonshot)',
    models: ['kimi-for-coding', 'kimi-k2', 'kimi-k2.5'],
    // DEPRECATED: Do not use this - call fetchProviderConfig() instead
    defaultBaseUrl: 'https://api.kimi.com/coding/',
    requiresApiKey: true,
    apiStyle: 'anthropic', // Backend uses ChatAnthropic for Kimi
  },
  openai: {
    name: 'OpenAI',
    models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'],
    // DEPRECATED: Do not use this - call fetchProviderConfig() instead
    defaultBaseUrl: 'https://api.openai.com/v1',
    requiresApiKey: true,
    apiStyle: 'openai',
  },
  anthropic: {
    name: 'Anthropic',
    models: ['claude-opus-4', 'claude-sonnet-4', 'claude-haiku-4'],
    // DEPRECATED: Do not use this - call fetchProviderConfig() instead
    defaultBaseUrl: 'https://api.anthropic.com/v1',
    requiresApiKey: true,
    apiStyle: 'anthropic',
  },
  ollama: {
    name: 'Ollama (Local)',
    models: ['llama3', 'mistral', 'codellama', 'mixtral'],
    // DEPRECATED: Do not use this - call fetchProviderConfig() instead
    defaultBaseUrl: 'http://localhost:11434/v1',
    requiresApiKey: false,
    apiStyle: 'openai',
  },
} as const;

export type AgentProvider = keyof typeof PROVIDER_CONFIGS;
export type AgentStatus = 'active' | 'inactive' | 'draft';

export interface Agent {
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

export interface AgentDetail extends Agent {
  base_url: string;
  timeout: number;
  system_prompt: string;
  context_prompt: string;
  memory_ttl: number;
  accounts: Array<{
    id: string;
    name: string;
    phone_number: string;
  }>;
}

export interface CreateAgentData {
  name: string;
  description?: string;
  provider: AgentProvider;
  model_name: string;
  // api_key is handled by backend, not sent from frontend
  base_url?: string;
  temperature?: number;
  max_tokens?: number;
  timeout?: number;
  system_prompt?: string;
  context_prompt?: string;
  status?: AgentStatus;
  use_memory?: boolean;
  memory_ttl?: number;
  accounts?: string[];
}

export interface ProcessMessageRequest {
  message: string;
  session_id?: string;
  phone_number?: string;
  context?: Record<string, unknown>;
}

export interface ProcessMessageResponse {
  response: string;
  session_id: string;
  tokens_used?: number;
  response_time_ms?: number;
}

export interface AgentStats {
  total_conversations: number;
  total_messages: number;
  avg_response_time_ms: number;
  active_sessions: number;
}

export interface AgentConversation {
  id: string;
  session_id: string;
  phone_number: string;
  message_count: number;
  last_message_at: string;
  created_at: string;
  messages?: AgentMessage[];
}

export interface AgentMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  tokens_used?: number;
  created_at: string;
}

// Default values for new agent - synced with backend
// Using Kimi Coding API with Anthropic style
// NOTE: base_url is loaded from backend via getProviderConfig() to avoid hardcoding
export const DEFAULT_AGENT_VALUES: Partial<CreateAgentData> = {
  provider: 'kimi',
  model_name: 'kimi-for-coding',
  // base_url is loaded from backend - do not hardcode
  temperature: 0.7,
  max_tokens: 32768, // Max for kimi-for-coding
  timeout: 30,
  system_prompt: 'Você é o assistente virtual da Pastita, uma loja de massas artesanais.\n\nSuas responsabilidades:\n- Responder dúvidas sobre o cardápio e produtos\n- Ajudar clientes a fazer pedidos\n- Informar sobre horário de funcionamento e entregas\n- Ser sempre educado, prestativo e gentil\n\nSe não souber responder algo específico, direcione o cliente para falar com um atendente humano.',
  context_prompt: '',
  status: 'draft',
  use_memory: true,
  memory_ttl: 3600,
  accounts: [],
};

// Backend provider config cache
let backendProviderConfig: Record<string, { base_url: string; model_name: string; api_style: string }> | null = null;

// Fetch provider config from backend (includes correct base URLs)
export const fetchProviderConfig = async (): Promise<Record<string, { base_url: string; model_name: string; api_style: string }>> => {
  try {
    const response = await api.get('/agents/agents/provider_config/');
    backendProviderConfig = response.data;
    return response.data;
  } catch (error) {
    console.error('[AgentService] Failed to fetch provider config:', error);
    // Return empty object - caller should handle fallback
    return {};
  }
};

// Get provider config (from cache or fetch)
export const getBackendProviderConfig = async (provider: AgentProvider): Promise<{ base_url: string; model_name: string; api_style: string } | null> => {
  if (!backendProviderConfig) {
    await fetchProviderConfig();
  }
  return backendProviderConfig?.[provider] || null;
};

// Clear provider config cache (call when needed)
export const clearProviderConfigCache = (): void => {
  backendProviderConfig = null;
};

// Error handling helper
class AgentServiceError extends Error {
  constructor(
    message: string,
    public statusCode?: number,
    public responseData?: unknown
  ) {
    super(message);
    this.name = 'AgentServiceError';
  }
}

const handleApiError = (error: unknown): never => {
  console.error('[AgentService] API Error:', error);
  
  if (error && typeof error === 'object' && 'response' in error) {
    const axiosError = error as { 
      response?: { 
        status?: number; 
        data?: { detail?: string; error?: string; message?: string } 
      };
      message?: string;
    };
    
    const status = axiosError.response?.status;
    const data = axiosError.response?.data;
    
    let message = 'Erro desconhecido ao processar requisição';
    
    if (data?.detail) {
      message = data.detail;
    } else if (data?.error) {
      message = data.error;
    } else if (data?.message) {
      message = data.message;
    } else if (status === 401) {
      message = 'API Key inválida ou não configurada no backend';
    } else if (status === 404) {
      message = 'Agente não encontrado ou endpoint indisponível';
    } else if (status === 500) {
      message = 'Erro interno no servidor. Verifique os logs do backend.';
    } else if (axiosError.message) {
      message = axiosError.message;
    }
    
    console.error(`[AgentService] Error ${status}: ${message}`, { data });
    throw new AgentServiceError(message, status, data);
  }
  
  throw new AgentServiceError('Erro de conexão com o servidor');
};

const agentsService = {
  // Agents
  getAgents: async (): Promise<Agent[]> => {
    try {
      const response = await api.get('/agents/agents/');
      return response.data.results || response.data;
    } catch (error) {
      return handleApiError(error);
    }
  },

  getAgent: async (id: string): Promise<AgentDetail> => {
    try {
      const response = await api.get(`/agents/agents/${id}/`);
      return response.data;
    } catch (error) {
      return handleApiError(error);
    }
  },

  createAgent: async (data: CreateAgentData): Promise<Agent> => {
    try {
      const response = await api.post('/agents/agents/', data);
      return response.data;
    } catch (error) {
      return handleApiError(error);
    }
  },

  updateAgent: async (id: string, data: Partial<CreateAgentData>): Promise<Agent> => {
    try {
      const response = await api.patch(`/agents/agents/${id}/`, data);
      return response.data;
    } catch (error) {
      return handleApiError(error);
    }
  },

  deleteAgent: async (id: string): Promise<void> => {
    try {
      await api.delete(`/agents/agents/${id}/`);
    } catch (error) {
      return handleApiError(error);
    }
  },

  // Process messages with enhanced error handling
  processMessage: async (
    agentId: string,
    data: ProcessMessageRequest
  ): Promise<ProcessMessageResponse> => {
    console.log(`[AgentService] Processing message for agent ${agentId}:`, {
      messageLength: data.message?.length,
      sessionId: data.session_id,
      hasPhoneNumber: !!data.phone_number,
    });
    
    try {
      const response = await api.post(`/agents/agents/${agentId}/process/`, data);
      console.log('[AgentService] Process message success:', {
        hasResponse: !!response.data?.response,
        sessionId: response.data?.session_id,
        tokensUsed: response.data?.tokens_used,
        responseTimeMs: response.data?.response_time_ms,
      });
      return response.data;
    } catch (error) {
      console.error('[AgentService] Process message failed:', error);
      return handleApiError(error);
    }
  },

  // Stats
  getAgentStats: async (agentId: string): Promise<AgentStats> => {
    try {
      const response = await api.get(`/agents/agents/${agentId}/stats/`);
      return response.data;
    } catch (error) {
      return handleApiError(error);
    }
  },

  // Conversations
  getAgentConversations: async (agentId: string): Promise<AgentConversation[]> => {
    try {
      const response = await api.get(`/agents/agents/${agentId}/conversations/`);
      return response.data.results || response.data;
    } catch (error) {
      return handleApiError(error);
    }
  },

  getConversation: async (sessionId: string): Promise<AgentConversation> => {
    try {
      const response = await api.get(`/agents/conversations/${sessionId}/`);
      return response.data;
    } catch (error) {
      return handleApiError(error);
    }
  },

  getConversationHistory: async (sessionId: string): Promise<AgentMessage[]> => {
    try {
      const response = await api.get(`/agents/conversations/${sessionId}/history/`);
      return response.data;
    } catch (error) {
      return handleApiError(error);
    }
  },

  clearConversationMemory: async (sessionId: string): Promise<boolean> => {
    try {
      const response = await api.post(`/agents/conversations/${sessionId}/clear_memory/`);
      return response.data.success;
    } catch (error) {
      return handleApiError(error);
    }
  },

  // Utility to get provider config
  getProviderConfig: (provider: AgentProvider) => PROVIDER_CONFIGS[provider],
  
  // Utility to get default model for provider
  getDefaultModel: (provider: AgentProvider) => PROVIDER_CONFIGS[provider].models[0],
  
  // Utility to get default base URL for provider
  getDefaultBaseUrl: (provider: AgentProvider) => PROVIDER_CONFIGS[provider].defaultBaseUrl,

  // NOVO: Processar mensagem com sistema unificado (templates → handlers → agent)
  processUnified: async (
    accountId: string,
    data: {
      message: string;
      phone_number: string;
      use_llm?: boolean;
      enable_templates?: boolean;
      enable_handlers?: boolean;
    }
  ): Promise<{
    content: string;
    source: 'template' | 'handler' | 'agent' | 'fallback';
    buttons?: Array<{ id: string; title: string }>;
    metadata?: Record<string, unknown>;
  }> => {
    try {
      const response = await api.post('/automation/unified/process/', {
        account_id: accountId,
        ...data,
      });
      return response.data;
    } catch (error) {
      return handleApiError(error);
    }
  },

  // NOVO: Obter estatísticas do sistema unificado
  getUnifiedStats: async (accountId: string): Promise<{
    templates_used: number;
    handlers_used: number;
    agent_used: number;
    fallbacks: number;
    session_context: Record<string, unknown>;
  }> => {
    try {
      const response = await api.get(`/automation/unified/stats/?account_id=${accountId}`);
      return response.data;
    } catch (error) {
      return handleApiError(error);
    }
  },
};

export default agentsService;
export { AgentServiceError };
