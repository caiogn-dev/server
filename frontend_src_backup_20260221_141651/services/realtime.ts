/**
 * Realtime Connection Service
 * Suporte a múltiplos transportes: WebSocket → SSE → HTTP Polling
 * Fallback automático com reconexão e backoff exponencial
 */

export type TransportType = 'websocket' | 'sse' | 'polling';
export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

interface EventCallback {
  (data: unknown): void;
}

interface ConnectionOptions {
  url: string;
  token?: string;
  storeSlug?: string;
  reconnectAttempts?: number;
  reconnectDelay?: number;
  maxReconnectDelay?: number;
  pingInterval?: number;
  fallbackOrder?: TransportType[];
}

export interface TransportCapabilities {
  websocket: boolean;
  sse: boolean;
  polling: boolean;
}

/**
 * Detecta as capacidades do navegador para cada transporte
 */
export function detectTransportCapabilities(): TransportCapabilities {
  return {
    websocket: typeof window !== 'undefined' && 'WebSocket' in window,
    sse: typeof window !== 'undefined' && 'EventSource' in window,
    polling: true, // Sempre disponível
  };
}

/**
 * Verifica se um transporte específico é suportado
 */
export function isTransportSupported(transport: TransportType): boolean {
  const caps = detectTransportCapabilities();
  return caps[transport];
}

/**
 * Classe principal de conexão realtime com fallback automático
 */
export class RealtimeConnection {
  private transport: TransportType | null = null;
  private fallbackOrder: TransportType[] = ['websocket', 'sse', 'polling'];
  private currentFallbackIndex = 0;
  
  // Handlers de conexão
  private ws: WebSocket | null = null;
  private eventSource: EventSource | null = null;
  private pollingInterval: number | null = null;
  private pollingController: AbortController | null = null;
  
  // Estado
  private status: ConnectionStatus = 'disconnected';
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectDelay = 1000;
  private maxReconnectDelay = 30000;
  private reconnectTimer: number | null = null;
  private pingTimer: number | null = null;
  private pingInterval = 25000;
  
  // Configuração
  private options: ConnectionOptions;
  private baseUrl: string;
  private token: string | null = null;
  
  // Event listeners
  private listeners = new Map<string, Set<EventCallback>>();
  private globalListeners = new Set<(event: string, data: unknown) => void>();
  
  // Status callbacks
  private statusCallbacks = new Set<(status: ConnectionStatus, transport: TransportType | null) => void>();
  private errorCallbacks = new Set<(error: Error, transport: TransportType | null) => void>();

  constructor(options: ConnectionOptions) {
    this.options = {
      reconnectAttempts: 10,
      reconnectDelay: 1000,
      maxReconnectDelay: 30000,
      pingInterval: 25000,
      fallbackOrder: ['websocket', 'sse', 'polling'],
      ...options,
    };
    
    this.baseUrl = options.url;
    this.token = options.token || null;
    this.maxReconnectAttempts = this.options.reconnectAttempts!;
    this.reconnectDelay = this.options.reconnectDelay!;
    this.maxReconnectDelay = this.options.maxReconnectDelay!;
    this.pingInterval = this.options.pingInterval!;
    this.fallbackOrder = this.options.fallbackOrder!;
  }

  /**
   * Retorna o transporte atual
   */
  getTransport(): TransportType | null {
    return this.transport;
  }

  /**
   * Retorna o status atual da conexão
   */
  getStatus(): ConnectionStatus {
    return this.status;
  }

  /**
   * Verifica se está conectado
   */
  isConnected(): boolean {
    return this.status === 'connected';
  }

  /**
   * Retorna informações sobre a conexão atual
   */
  getConnectionInfo() {
    return {
      transport: this.transport,
      status: this.status,
      reconnectAttempts: this.reconnectAttempts,
      currentFallbackIndex: this.currentFallbackIndex,
      capabilities: detectTransportCapabilities(),
    };
  }

  /**
   * Inicia a conexão
   */
  connect(): void {
    if (this.status === 'connecting' || this.status === 'connected') {
      console.log('[Realtime] Already connecting or connected');
      return;
    }

    this.setStatus('connecting');
    this.tryConnect();
  }

  /**
   * Desconecta e limpa recursos
   */
  disconnect(): void {
    this.cleanup();
    this.setStatus('disconnected');
    this.reconnectAttempts = 0;
    this.currentFallbackIndex = 0;
    console.log('[Realtime] Disconnected');
  }

  /**
   * Reconecta manualmente
   */
  reconnect(): void {
    this.disconnect();
    this.reconnectAttempts = 0;
    this.currentFallbackIndex = 0;
    this.connect();
  }

  /**
   * Registra listener para um evento específico
   */
  on(event: string, callback: EventCallback): () => void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(callback);
    
    console.log(`[Realtime] Subscribed to '${event}' (total: ${this.listeners.get(event)!.size})`);
    
    return () => {
      this.listeners.get(event)?.delete(callback);
      console.log(`[Realtime] Unsubscribed from '${event}'`);
    };
  }

  /**
   * Registra listener para todos os eventos
   */
  onAny(callback: (event: string, data: unknown) => void): () => void {
    this.globalListeners.add(callback);
    return () => {
      this.globalListeners.delete(callback);
    };
  }

  /**
   * Registra callback para mudanças de status
   */
  onStatusChange(callback: (status: ConnectionStatus, transport: TransportType | null) => void): () => void {
    this.statusCallbacks.add(callback);
    return () => {
      this.statusCallbacks.delete(callback);
    };
  }

  /**
   * Registra callback para erros
   */
  onError(callback: (error: Error, transport: TransportType | null) => void): () => void {
    this.errorCallbacks.add(callback);
    return () => {
      this.errorCallbacks.delete(callback);
    };
  }

  /**
   * Envia dados (apenas para WebSocket)
   */
  emit(event: string, data?: unknown): boolean {
    if (this.transport !== 'websocket' || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('[Realtime] Cannot emit: not connected via WebSocket');
      return false;
    }
    
    try {
      const message = JSON.stringify({ type: event, ...((typeof data === 'object' && data !== null) ? data : { data }) });
      this.ws.send(message);
      return true;
    } catch (err) {
      console.error('[Realtime] Emit error:', err);
      return false;
    }
  }

  /**
   * Envia ping (keepalive)
   */
  ping(): boolean {
    return this.emit('ping');
  }

  /**
   * Força o uso de um transporte específico
   */
  forceTransport(transport: TransportType): void {
    this.disconnect();
    const index = this.fallbackOrder.indexOf(transport);
    if (index >= 0) {
      this.currentFallbackIndex = index;
    }
    this.connect();
  }

  /**
   * Tenta conectar com o transporte atual
   */
  private tryConnect(): void {
    const transport = this.fallbackOrder[this.currentFallbackIndex];
    
    if (!transport) {
      console.error('[Realtime] Exhausted all transport options');
      this.setStatus('error');
      this.notifyError(new Error('All transport options exhausted'), null);
      return;
    }

    if (!isTransportSupported(transport)) {
      console.log(`[Realtime] Transport '${transport}' not supported, trying next...`);
      this.currentFallbackIndex++;
      this.tryConnect();
      return;
    }

    console.log(`[Realtime] Trying transport: ${transport}`);
    this.transport = transport;

    switch (transport) {
      case 'websocket':
        this.connectWebSocket();
        break;
      case 'sse':
        this.connectSSE();
        break;
      case 'polling':
        this.connectPolling();
        break;
    }
  }

  /**
   * Conecta via WebSocket
   */
  private connectWebSocket(): void {
    try {
      const url = this.buildUrl('websocket');
      console.log('[Realtime] Connecting WebSocket:', url.replace(/token=.*/, 'token=***'));
      
      this.ws = new WebSocket(url);
      
      this.ws.onopen = () => {
        console.log('[Realtime] WebSocket connected ✓');
        this.onConnectSuccess();
        this.startPingInterval();
      };
      
      this.ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          this.handleMessage(data);
        } catch (err) {
          console.error('[Realtime] WebSocket parse error:', err);
        }
      };
      
      this.ws.onclose = (e) => {
        console.log('[Realtime] WebSocket closed:', e.code, e.reason);
        this.onConnectError(new Error(`WebSocket closed: ${e.code} ${e.reason}`));
      };
      
      this.ws.onerror = (e) => {
        console.error('[Realtime] WebSocket error:', e);
        this.onConnectError(new Error('WebSocket error'));
      };
    } catch (err) {
      console.error('[Realtime] WebSocket connection error:', err);
      this.onConnectError(err as Error);
    }
  }

  /**
   * Conecta via Server-Sent Events
   */
  private connectSSE(): void {
    try {
      const url = this.buildUrl('sse');
      console.log('[Realtime] Connecting SSE:', url.replace(/token=.*/, 'token=***'));
      
      this.eventSource = new EventSource(url);
      
      this.eventSource.onopen = () => {
        console.log('[Realtime] SSE connected ✓');
        this.onConnectSuccess();
      };
      
      this.eventSource.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          this.handleMessage(data);
        } catch (err) {
          console.error('[Realtime] SSE parse error:', err);
        }
      };
      
      // Eventos específicos do SSE
      this.eventSource.addEventListener('order_created', (e) => {
        try {
          const data = JSON.parse(e.data);
          this.emitEvent('order_created', data);
        } catch (err) {
          console.error('[Realtime] SSE event error:', err);
        }
      });
      
      this.eventSource.addEventListener('order_updated', (e) => {
        try {
          const data = JSON.parse(e.data);
          this.emitEvent('order_updated', data);
        } catch (err) {
          console.error('[Realtime] SSE event error:', err);
        }
      });
      
      this.eventSource.addEventListener('payment_received', (e) => {
        try {
          const data = JSON.parse(e.data);
          this.emitEvent('payment_received', data);
        } catch (err) {
          console.error('[Realtime] SSE event error:', err);
        }
      });
      
      this.eventSource.onerror = (e) => {
        console.error('[Realtime] SSE error:', e);
        this.onConnectError(new Error('SSE error'));
      };
    } catch (err) {
      console.error('[Realtime] SSE connection error:', err);
      this.onConnectError(err as Error);
    }
  }

  /**
   * Conecta via HTTP Polling
   */
  private connectPolling(): void {
    console.log('[Realtime] Starting HTTP polling');
    this.pollingController = new AbortController();
    this.doPoll();
  }

  /**
   * Executa uma requisição de polling
   */
  private async doPoll(): Promise<void> {
    if (this.transport !== 'polling' || this.status === 'disconnected') {
      return;
    }

    try {
      const url = this.buildUrl('polling');
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
          ...(this.token ? { 'Authorization': `Bearer ${this.token}` } : {}),
        },
        signal: this.pollingController?.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const events = await response.json();
      
      // Primeira resposta bem-sucedida = conectado
      if (this.status !== 'connected') {
        this.onConnectSuccess();
      }

      // Processar eventos recebidos
      if (Array.isArray(events)) {
        events.forEach((event) => this.handleMessage(event));
      } else if (events) {
        this.handleMessage(events);
      }
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        return; // Polling cancelado intencionalmente
      }
      console.error('[Realtime] Polling error:', err);
      this.onConnectError(err as Error);
      return;
    }

    // Agendar próximo poll
    if (this.transport === 'polling' && this.status === 'connected') {
      this.pollingInterval = window.setTimeout(() => {
        this.doPoll();
      }, 5000); // Poll a cada 5 segundos
    }
  }

  /**
   * Constrói a URL para o transporte especificado
   */
  private buildUrl(transport: TransportType): string {
    const wsHost = this.getWSHost();
    const storeSlug = this.options.storeSlug || 'default';
    const token = this.token;
    
    switch (transport) {
      case 'websocket': {
        const proto = this.isSecure() ? 'wss' : 'ws';
        return `${proto}://${wsHost}/ws/stores/${storeSlug}/orders/?token=${token}`;
      }
      case 'sse': {
        const httpProto = this.isSecure() ? 'https' : 'http';
        return `${httpProto}://${wsHost}/api/sse/stores/${storeSlug}/events/?token=${token}`;
      }
      case 'polling': {
        const httpProto = this.isSecure() ? 'https' : 'http';
        return `${httpProto}://${wsHost}/api/polling/stores/${storeSlug}/events/?token=${token}`;
      }
    }
  }

  /**
   * Retorna o host WebSocket
   */
  private getWSHost(): string {
    // @ts-ignore - Vite env
    let wsHost: string | undefined = typeof import.meta !== 'undefined' ? import.meta.env?.VITE_WS_HOST : undefined;
    if (!wsHost) {
      // @ts-ignore - Vite env
      const apiUrl: string = typeof import.meta !== 'undefined' ? (import.meta.env?.VITE_API_URL || '') : '';
      if (apiUrl) {
        try {
          wsHost = new URL(apiUrl).host;
        } catch {
          wsHost = window.location.host;
        }
      } else {
        wsHost = window.location.host;
      }
    }
    return wsHost;
  }

  /**
   * Verifica se deve usar conexão segura
   */
  private isSecure(): boolean {
    const wsHost = this.getWSHost();
    return wsHost.includes('railway') || 
           wsHost.includes('vercel') || 
           window.location.protocol === 'https:';
  }

  /**
   * Chamado quando a conexão é bem-sucedida
   */
  private onConnectSuccess(): void {
    this.setStatus('connected');
    this.reconnectAttempts = 0;
  }

  /**
   * Chamado quando há erro de conexão
   */
  private onConnectError(error: Error): void {
    this.cleanupTransport();
    this.notifyError(error, this.transport);

    // Tentar próximo transporte
    this.currentFallbackIndex++;
    
    if (this.currentFallbackIndex < this.fallbackOrder.length) {
      console.log(`[Realtime] Falling back to next transport...`);
      this.tryConnect();
    } else {
      // Todos os transportes falharam, tentar reconexão
      this.scheduleReconnect();
    }
  }

  /**
   * Agenda reconexão com backoff exponencial
   */
  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('[Realtime] Max reconnect attempts reached');
      this.setStatus('error');
      return;
    }

    const delay = Math.min(
      this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts),
      this.maxReconnectDelay
    );

    console.log(`[Realtime] Reconnecting in ${Math.round(delay)}ms (attempt ${this.reconnectAttempts + 1}/${this.maxReconnectAttempts})`);
    this.setStatus('connecting');

    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectAttempts++;
      this.currentFallbackIndex = 0; // Resetar para tentar WebSocket novamente
      this.tryConnect();
    }, delay);
  }

  /**
   * Processa mensagem recebida
   */
  private handleMessage(data: Record<string, unknown>): void {
    // Ignorar pings/pongs
    if (data.type === 'ping' || data.type === 'pong') {
      return;
    }

    // Normalizar nomes de eventos
    const eventMap: Record<string, string> = {
      'order.created': 'order_created',
      'order.updated': 'order_updated',
      'order.paid': 'payment_received',
      'order.cancelled': 'order_cancelled',
      'order.status_changed': 'order_updated',
    };

    const eventType = (data.type as string) || 'message';
    const normalizedEvent = eventMap[eventType] || eventType;

    this.emitEvent(normalizedEvent, data);
  }

  /**
   * Emite evento para listeners
   */
  private emitEvent(event: string, data: unknown): void {
    console.log(`[Realtime] Event: ${event}`, data);

    // Listeners específicos do evento
    const eventListeners = this.listeners.get(event);
    if (eventListeners) {
      eventListeners.forEach(cb => {
        try {
          cb(data);
        } catch (e) {
          console.error('[Realtime] Callback error:', e);
        }
      });
    }

    // Listeners globais
    this.globalListeners.forEach(cb => {
      try {
        cb(event, data);
      } catch (e) {
        console.error('[Realtime] Global callback error:', e);
      }
    });

    // Wildcard listeners
    const wildcardListeners = this.listeners.get('*');
    if (wildcardListeners) {
      wildcardListeners.forEach(cb => {
        try {
          cb(data);
        } catch (e) {
          console.error('[Realtime] Wildcard callback error:', e);
        }
      });
    }
  }

  /**
   * Atualiza o status e notifica listeners
   */
  private setStatus(status: ConnectionStatus): void {
    this.status = status;
    this.statusCallbacks.forEach(cb => {
      try {
        cb(status, this.transport);
      } catch (e) {
        console.error('[Realtime] Status callback error:', e);
      }
    });
  }

  /**
   * Notifica listeners de erro
   */
  private notifyError(error: Error, transport: TransportType | null): void {
    this.errorCallbacks.forEach(cb => {
      try {
        cb(error, transport);
      } catch (e) {
        console.error('[Realtime] Error callback error:', e);
      }
    });
  }

  /**
   * Inicia intervalo de ping
   */
  private startPingInterval(): void {
    if (this.pingTimer) {
      window.clearInterval(this.pingTimer);
    }
    
    this.pingTimer = window.setInterval(() => {
      if (this.transport === 'websocket' && this.ws?.readyState === WebSocket.OPEN) {
        this.ping();
      }
    }, this.pingInterval);
  }

  /**
   * Limpa recursos do transporte atual
   */
  private cleanupTransport(): void {
    // Limpar WebSocket
    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onclose = null;
      this.ws.onerror = null;
      
      if (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING) {
        this.ws.close();
      }
      this.ws = null;
    }

    // Limpar SSE
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }

    // Limpar Polling
    if (this.pollingInterval) {
      window.clearTimeout(this.pollingInterval);
      this.pollingInterval = null;
    }
    
    if (this.pollingController) {
      this.pollingController.abort();
      this.pollingController = null;
    }

    // Limpar ping
    if (this.pingTimer) {
      window.clearInterval(this.pingTimer);
      this.pingTimer = null;
    }

    this.transport = null;
  }

  /**
   * Limpa todos os recursos
   */
  private cleanup(): void {
    this.cleanupTransport();
    
    if (this.reconnectTimer) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
}

/**
 * Cria uma instância singleton de RealtimeConnection
 */
let globalConnection: RealtimeConnection | null = null;

export function createRealtimeConnection(options: ConnectionOptions): RealtimeConnection {
  return new RealtimeConnection(options);
}

export function getGlobalConnection(): RealtimeConnection | null {
  return globalConnection;
}

export function setGlobalConnection(connection: RealtimeConnection | null): void {
  globalConnection = connection;
}

/**
 * Hook helper para obter URL WebSocket (backwards compatibility)
 */
export function getWebSocketUrl(path: string): string {
  // @ts-ignore - Vite env
  let wsHost: string | undefined = typeof import.meta !== 'undefined' ? import.meta.env?.VITE_WS_HOST : undefined;
  if (!wsHost) {
    // @ts-ignore - Vite env
    const apiUrl: string = typeof import.meta !== 'undefined' ? (import.meta.env?.VITE_API_URL || '') : '';
    wsHost = apiUrl ? new URL(apiUrl).host : window.location.host;
  }
  const proto = wsHost.includes('railway') || wsHost.includes('vercel') || window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${wsHost}${path}`;
}

export default RealtimeConnection;
