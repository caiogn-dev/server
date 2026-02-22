/**
 * Logger Service - Centralized logging with environment awareness
 * 
 * In development: logs to console with full details
 * In production: logs errors to external service (Sentry-ready)
 */

const isDevelopment = import.meta.env.DEV;
const isTest = import.meta.env.MODE === 'test';

// Log levels
const LOG_LEVELS = {
  DEBUG: 0,
  INFO: 1,
  WARN: 2,
  ERROR: 3,
} as const;

// Current log level based on environment
const currentLevel = isDevelopment ? LOG_LEVELS.DEBUG : LOG_LEVELS.WARN;

interface LogContext {
  [key: string]: unknown;
}

interface StoredError {
  timestamp: string;
  message: string;
  stack?: string;
  context: LogContext;
}

/**
 * Format log message with timestamp and context
 */
function formatMessage(level: string, message: string, context: LogContext = {}): string {
  const timestamp = new Date().toISOString();
  const contextStr = Object.keys(context).length > 0 
    ? ` | ${JSON.stringify(context)}` 
    : '';
  return `[${timestamp}] [${level}] ${message}${contextStr}`;
}

/**
 * Send error to external monitoring service (Sentry-ready)
 */
function sendToMonitoring(error: Error | string, context: LogContext = {}): void {
  // Sentry integration placeholder
  // if (typeof window !== 'undefined' && (window as any).Sentry) {
  //   (window as any).Sentry.captureException(error, { extra: context });
  // }
  
  // For now, store in sessionStorage for debugging
  if (typeof window !== 'undefined' && !isTest) {
    try {
      const errors: StoredError[] = JSON.parse(sessionStorage.getItem('app_errors') || '[]');
      const errorObj = error instanceof Error ? error : new Error(String(error));
      errors.push({
        timestamp: new Date().toISOString(),
        message: errorObj.message || String(error),
        stack: errorObj.stack,
        context,
      });
      // Keep only last 50 errors
      if (errors.length > 50) errors.shift();
      sessionStorage.setItem('app_errors', JSON.stringify(errors));
    } catch (e) {
      // Storage might be full or unavailable
    }
  }
}

/**
 * Debug level logging - only in development
 */
export function debug(message: string, context: LogContext = {}): void {
  if (currentLevel <= LOG_LEVELS.DEBUG && isDevelopment) {
    console.debug(formatMessage('DEBUG', message, context));
  }
}

/**
 * Info level logging - development only
 */
export function info(message: string, context: LogContext = {}): void {
  if (currentLevel <= LOG_LEVELS.INFO && isDevelopment) {
    console.info(formatMessage('INFO', message, context));
  }
}

/**
 * Warning level logging - always logged in development
 */
export function warn(message: string, context: LogContext = {}): void {
  if (currentLevel <= LOG_LEVELS.WARN) {
    if (isDevelopment) {
      console.warn(formatMessage('WARN', message, context));
    }
    // In production, warnings are silently tracked
    sendToMonitoring(message, { level: 'warn', ...context });
  }
}

/**
 * Error level logging - always logged, sent to monitoring in production
 * Accepts unknown type to handle catch block errors safely
 */
export function error(message: string, errorObj: Error | unknown = null, context: LogContext = {}): void {
  const err = errorObj instanceof Error ? errorObj : new Error(message);
  
  if (isDevelopment) {
    console.error(formatMessage('ERROR', message, context));
    if (errorObj && errorObj !== (message as unknown)) {
      console.error(errorObj);
    }
  }
  
  // Always send errors to monitoring
  sendToMonitoring(err, { message, ...context });
}

/**
 * Log API errors with request context
 */
export function apiError(endpoint: string, err: Error | unknown, requestData: unknown = {}): void {
  const errorObj = err instanceof Error ? err : new Error(String(err));
  const context = {
    endpoint,
    status: (err as any)?.status || (err as any)?.response?.status,
    requestData: isDevelopment ? requestData : '[redacted]',
  };
  
  error(`API Error: ${endpoint}`, errorObj, context);
}

/**
 * Log WebSocket events
 */
export function wsEvent(event: string, data: LogContext = {}): void {
  if (isDevelopment) {
    debug(`WebSocket: ${event}`, data);
  }
}

/**
 * Log map-related events
 */
export function mapEvent(event: string, data: LogContext = {}): void {
  if (isDevelopment) {
    debug(`Map: ${event}`, data);
  }
}

/**
 * Get stored errors for debugging
 */
export function getStoredErrors(): StoredError[] {
  if (typeof window !== 'undefined') {
    try {
      return JSON.parse(sessionStorage.getItem('app_errors') || '[]');
    } catch (e) {
      return [];
    }
  }
  return [];
}

/**
 * Clear stored errors
 */
export function clearStoredErrors(): void {
  if (typeof window !== 'undefined') {
    sessionStorage.removeItem('app_errors');
  }
}

// Default export with all methods
const logger = {
  debug,
  info,
  warn,
  error,
  apiError,
  wsEvent,
  mapEvent,
  getStoredErrors,
  clearStoredErrors,
};

export default logger;
