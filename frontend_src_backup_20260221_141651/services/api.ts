import axios, { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios';
import { useAuthStore } from '../stores/authStore';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://backend.pastita.com.br/api/v1';

const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Ensure cookies and CSRF token are sent for cross-site requests
api.defaults.withCredentials = true;
api.defaults.xsrfCookieName = 'csrftoken';
api.defaults.xsrfHeaderName = 'X-CSRFTOKEN';

// Helper to get token from localStorage directly (bypasses zustand hydration timing)
const getTokenFromStorage = (): string | null => {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem('auth-storage');
    if (raw) {
      const parsed = JSON.parse(raw);
      return parsed?.state?.token || null;
    }
  } catch {
    /* ignore parse errors */
  }
  return null;
};

// Request interceptor to add auth token
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // Try zustand store first, then localStorage directly, then axios defaults
    let token = useAuthStore.getState().token;
    
    if (!token) {
      // Fallback: read directly from localStorage (handles hydration timing)
      token = getTokenFromStorage();
    }

    if (token) {
      if (token.includes('.')) {
        config.headers.Authorization = `Bearer ${token}`;
      } else {
        config.headers.Authorization = `Token ${token}`;
      }
    } else {
      // Last fallback: use axios default header if set
      const defaultAuth = api.defaults.headers.common?.Authorization;
      if (defaultAuth && typeof defaultAuth === 'string') {
        config.headers.Authorization = defaultAuth;
      }
    }

    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor to handle errors
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const httpStatus = error.response?.status;
    const errorData = error.response?.data as { code?: string } | undefined;
    const errorCode = errorData?.code;
    const requestUrl = error.config?.url || '';

    // Only logout on 401/403 if:
    // 1. The request actually had an Authorization header (token was sent)
    // 2. It's not a login/register endpoint (those return 401 for invalid credentials)
    const hadAuthHeader = Boolean(error.config?.headers?.Authorization);
    const isAuthEndpoint = requestUrl.includes('/auth/login') || requestUrl.includes('/auth/register');

    if (
      (httpStatus === 401 || httpStatus === 403 || errorCode === 'token_not_valid') &&
      hadAuthHeader &&
      !isAuthEndpoint
    ) {
      useAuthStore.getState().logout();
      // clear default header immediately
      try {
        delete api.defaults.headers.common.Authorization;
      } catch {
        /* ignore */
      }
    }
    return Promise.reject(error);
  }
);

export default api;

// Allow immediate setting/clearing of the Authorization header
export const setAuthToken = (token: string | null): void => {
  if (token) {
    if (token.includes('.')) {
      api.defaults.headers.common.Authorization = `Bearer ${token}`;
    } else {
      api.defaults.headers.common.Authorization = `Token ${token}`;
    }
  } else {
    delete api.defaults.headers.common.Authorization;
  }
};

// Helper function to handle API errors
export const getErrorMessage = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data;
    if (data?.error?.message) {
      return data.error.message;
    }
    if (data?.detail) {
      return data.detail;
    }
    if (typeof data === 'string') {
      return data;
    }
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'An unexpected error occurred';
};
