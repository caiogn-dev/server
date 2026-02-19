/**
 * WebSocket Connection Manager with SSE Fallback
 * 
 * This module provides a robust WebSocket connection with automatic
 * fallback to Server-Sent Events (SSE) and HTTP polling.
 * 
 * Usage:
 *   const conn = new WebSocketConnection('/ws/orders/');
 *   conn.on('message', (data) => console.log(data));
 *   conn.connect();
 */

class WebSocketConnection extends EventTarget {
    /**
     * @param {string} url - WebSocket URL
     * @param {Object} options - Configuration options
     */
    constructor(url, options = {}) {
        super();
        
        this.wsUrl = url;
        this.options = {
            autoReconnect: true,
            reconnectInterval: 5000,
            maxReconnectAttempts: 5,
            heartbeatInterval: 30000,
            fallbackEnabled: true,
            debug: false,
            ...options
        };
        
        this.ws = null;
        this.eventSource = null;
        this.reconnectAttempts = 0;
        this.heartbeatTimer = null;
        this.fallbackMode = false;
        this.transport = null; // 'websocket', 'sse', or 'polling'
        this.messageQueue = [];
        
        this._boundOnOpen = this._onOpen.bind(this);
        this._boundOnMessage = this._onMessage.bind(this);
        this._boundOnClose = this._onClose.bind(this);
        this._boundOnError = this._onError.bind(this);
    }
    
    /**
     * Detect if WebSocket is supported and working
     */
    static async detectSupport() {
        // Check browser support
        if (!window.WebSocket) {
            return { supported: false, reason: 'WebSocket not supported' };
        }
        
        // Try to connect to health endpoint
        try {
            const response = await fetch('/api/sse/health/');
            const data = await response.json();
            return {
                supported: data.websocket_supported,
                recommended: data.recommended_transport,
                sseSupported: data.sse_supported,
                endpoints: data.sse_endpoints
            };
        } catch (e) {
            return { supported: true, reason: 'Health check failed, assuming supported' };
        }
    }
    
    /**
     * Connect to the server
     */
    async connect() {
        if (this.ws || this.eventSource) {
            this._log('Already connected');
            return;
        }
        
        // Detect support if not in fallback mode
        if (!this.fallbackMode) {
            const detection = await WebSocketConnection.detectSupport();
            this._log('Support detection:', detection);
            
            if (!detection.supported && this.options.fallbackEnabled) {
                this._log('WebSocket not supported, trying SSE');
                return this._connectSSE();
            }
        }
        
        // Try WebSocket
        try {
            this._connectWebSocket();
        } catch (e) {
            this._error('WebSocket connection failed:', e);
            if (this.options.fallbackEnabled) {
                this._connectSSE();
            }
        }
    }
    
    /**
     * Connect via WebSocket
     */
    _connectWebSocket() {
        this._log('Connecting WebSocket:', this.wsUrl);
        
        this.ws = new WebSocket(this.wsUrl);
        this.transport = 'websocket';
        
        this.ws.addEventListener('open', this._boundOnOpen);
        this.ws.addEventListener('message', this._boundOnMessage);
        this.ws.addEventListener('close', this._boundOnClose);
        this.ws.addEventListener('error', this._boundOnError);
    }
    
    /**
     * Connect via Server-Sent Events
     */
    _connectSSE() {
        this.fallbackMode = true;
        
        // Map WebSocket URL to SSE endpoint
        let sseUrl = this._mapToSSEUrl(this.wsUrl);
        
        this._log('Connecting SSE:', sseUrl);
        
        try {
            this.eventSource = new EventSource(sseUrl);
            this.transport = 'sse';
            
            this.eventSource.addEventListener('open', () => {
                this._log('SSE connection opened');
                this.reconnectAttempts = 0;
            });
            
            this.eventSource.addEventListener('connected', (e) => {
                const data = JSON.parse(e.data);
                this._log('SSE connected:', data);
                this.dispatchEvent(new CustomEvent('open', { detail: data }));
                this._startHeartbeat();
            });
            
            this.eventSource.addEventListener('message', (e) => {
                const data = JSON.parse(e.data);
                this.dispatchEvent(new CustomEvent('message', { detail: data }));
            });
            
            this.eventSource.addEventListener('error', (e) => {
                this._error('SSE error:', e);
                this._reconnect();
            });
            
            // Handle specific event types
            this.eventSource.addEventListener('order_update', (e) => {
                const data = JSON.parse(e.data);
                this.dispatchEvent(new CustomEvent('order_update', { detail: data }));
            });
            
            this.eventSource.addEventListener('new_order', (e) => {
                const data = JSON.parse(e.data);
                this.dispatchEvent(new CustomEvent('new_order', { detail: data }));
            });
            
            this.eventSource.addEventListener('heartbeat', (e) => {
                this._log('SSE heartbeat');
            });
            
        } catch (e) {
            this._error('SSE connection failed:', e);
            this._startPolling();
        }
    }
    
    /**
     * Start HTTP polling as last resort
     */
    _startPolling() {
        this.transport = 'polling';
        this._log('Starting HTTP polling');
        
        // Map URL to polling endpoint
        const pollUrl = this._mapToPollUrl(this.wsUrl);
        
        const poll = async () => {
            try {
                const response = await fetch(pollUrl);
                const data = await response.json();
                
                if (data.results) {
                    data.results.forEach(item => {
                        this.dispatchEvent(new CustomEvent('message', { detail: item }));
                    });
                }
            } catch (e) {
                this._error('Polling error:', e);
            }
            
            if (this.transport === 'polling') {
                setTimeout(poll, 5000); // Poll every 5 seconds
            }
        };
        
        poll();
    }
    
    /**
     * Map WebSocket URL to SSE URL
     */
    _mapToSSEUrl(wsUrl) {
        // Convert ws:// to http:// and wss:// to https://
        let url = wsUrl.replace(/^ws:/, 'http:').replace(/^wss:/, 'https:');
        
        // Map specific endpoints
        if (url.includes('/ws/orders/')) {
            const match = url.match(/\/ws\/orders\/([^\/]+)/);
            if (match) {
                return `/api/sse/orders/?order_id=${match[1]}`;
            }
            return '/api/sse/orders/';
        }
        
        if (url.includes('/ws/whatsapp/')) {
            const match = url.match(/\/ws\/whatsapp\/([^\/]+)/);
            if (match) {
                return `/api/sse/whatsapp/?account_id=${match[1]}`;
            }
            return '/api/sse/whatsapp/';
        }
        
        if (url.includes('/ws/chat/')) {
            const match = url.match(/\/ws\/chat\/([^\/]+)/);
            if (match) {
                return `/api/sse/whatsapp/?conversation_id=${match[1]}`;
            }
        }
        
        // Add token if present in query string
        if (url.includes('?')) {
            const params = new URLSearchParams(url.split('?')[1]);
            const token = params.get('token');
            if (token) {
                return `/api/sse/orders/?token=${token}`;
            }
        }
        
        return '/api/sse/orders/';
    }
    
    /**
     * Map WebSocket URL to polling URL
     */
    _mapToPollUrl(wsUrl) {
        if (wsUrl.includes('/ws/orders/')) {
            const match = wsUrl.match(/\/ws\/orders\/([^\/]+)/);
            if (match) {
                return `/api/v1/stores/orders/${match[1]}/`;
            }
            return '/api/v1/stores/orders/';
        }
        
        if (wsUrl.includes('/ws/whatsapp/') || wsUrl.includes('/ws/chat/')) {
            return '/api/v1/whatsapp/messages/';
        }
        
        return '/api/v1/notifications/';
    }
    
    /**
     * WebSocket event handlers
     */
    _onOpen(event) {
        this._log('WebSocket connected');
        this.reconnectAttempts = 0;
        this.fallbackMode = false;
        this._startHeartbeat();
        this.dispatchEvent(new CustomEvent('open', { detail: event }));
    }
    
    _onMessage(event) {
        try {
            const data = JSON.parse(event.data);
            this._log('Received:', data);
            
            // Handle specific message types
            if (data.type === 'fallback_info') {
                this.fallbackEndpoints = data;
            }
            
            this.dispatchEvent(new CustomEvent('message', { detail: data }));
        } catch (e) {
            this.dispatchEvent(new CustomEvent('message', { detail: event.data }));
        }
    }
    
    _onClose(event) {
        this._log('WebSocket closed:', event.code, event.reason);
        this._cleanup();
        
        if (this.options.autoReconnect && !event.wasClean) {
            this._reconnect();
        }
        
        this.dispatchEvent(new CustomEvent('close', { detail: event }));
    }
    
    _onError(event) {
        this._error('WebSocket error:', event);
        this.dispatchEvent(new CustomEvent('error', { detail: event }));
    }
    
    /**
     * Reconnect logic
     */
    _reconnect() {
        if (this.reconnectAttempts >= this.options.maxReconnectAttempts) {
            this._error('Max reconnection attempts reached');
            
            if (this.options.fallbackEnabled && this.transport === 'websocket') {
                this._log('Trying fallback transport');
                this._connectSSE();
            }
            return;
        }
        
        this.reconnectAttempts++;
        const delay = this.options.reconnectInterval * Math.pow(1.5, this.reconnectAttempts - 1);
        
        this._log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
        
        setTimeout(() => {
            if (this.fallbackMode) {
                this._connectSSE();
            } else {
                this.connect();
            }
        }, delay);
    }
    
    /**
     * Heartbeat/ping-pong
     */
    _startHeartbeat() {
        if (this.heartbeatTimer) {
            clearInterval(this.heartbeatTimer);
        }
        
        this.heartbeatTimer = setInterval(() => {
            if (this.transport === 'websocket' && this.ws?.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: 'ping', timestamp: Date.now() }));
            }
        }, this.options.heartbeatInterval);
    }
    
    /**
     * Send message (WebSocket only)
     */
    send(data) {
        if (this.transport === 'websocket' && this.ws?.readyState === WebSocket.OPEN) {
            const message = typeof data === 'string' ? data : JSON.stringify(data);
            this.ws.send(message);
        } else {
            // Queue for later or send via HTTP
            this._log('Cannot send in current transport mode:', this.transport);
            this.messageQueue.push(data);
        }
    }
    
    /**
     * Subscribe to a channel
     */
    subscribe(channel) {
        this.send({ type: 'subscribe', channel });
    }
    
    /**
     * Unsubscribe from a channel
     */
    unsubscribe(channel) {
        this.send({ type: 'unsubscribe', channel });
    }
    
    /**
     * Close connection
     */
    close() {
        this.options.autoReconnect = false;
        
        if (this.ws) {
            this.ws.close(1000, 'Client closing');
        }
        
        if (this.eventSource) {
            this.eventSource.close();
        }
        
        this._cleanup();
    }
    
    /**
     * Clean up resources
     */
    _cleanup() {
        if (this.heartbeatTimer) {
            clearInterval(this.heartbeatTimer);
            this.heartbeatTimer = null;
        }
        
        if (this.ws) {
            this.ws.removeEventListener('open', this._boundOnOpen);
            this.ws.removeEventListener('message', this._boundOnMessage);
            this.ws.removeEventListener('close', this._boundOnClose);
            this.ws.removeEventListener('error', this._boundOnError);
            this.ws = null;
        }
        
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
    }
    
    /**
     * Utility methods
     */
    _log(...args) {
        if (this.options.debug) {
            console.log('[WebSocketConnection]', ...args);
        }
    }
    
    _error(...args) {
        console.error('[WebSocketConnection]', ...args);
    }
    
    /**
     * Check if currently connected
     */
    get isConnected() {
        if (this.transport === 'websocket') {
            return this.ws?.readyState === WebSocket.OPEN;
        }
        if (this.transport === 'sse') {
            return this.eventSource?.readyState === EventSource.OPEN;
        }
        return this.transport === 'polling';
    }
    
    /**
     * Get current transport mode
     */
    get currentTransport() {
        return this.transport;
    }
}


/**
 * Convenience function to create a connection
 */
function createWebSocketConnection(url, options) {
    return new WebSocketConnection(url, options);
}


// Export for different module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { WebSocketConnection, createWebSocketConnection };
}

if (typeof window !== 'undefined') {
    window.WebSocketConnection = WebSocketConnection;
    window.createWebSocketConnection = createWebSocketConnection;
}
