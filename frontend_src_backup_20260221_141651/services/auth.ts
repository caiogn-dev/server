import api from './api';
import { LoginResponse, User } from '../types';

export const authService = {
  login: async (email: string, password: string): Promise<LoginResponse> => {
    const response = await api.post<LoginResponse>('/auth/login/', { email, password });
    return response.data;
  },

  logout: async (): Promise<void> => {
    await api.post('/auth/logout/');
  },

  getCurrentUser: async (): Promise<User> => {
    const response = await api.get<User>('/auth/me/');
    return response.data;
  },

  changePassword: async (oldPassword: string, newPassword: string): Promise<{ message: string; token: string }> => {
    const response = await api.post('/auth/change-password/', {
      old_password: oldPassword,
      new_password: newPassword,
    });
    return response.data;
  },
};
