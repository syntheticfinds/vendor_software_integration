import { create } from 'zustand';
import type { Company } from '../api/auth';

interface AuthState {
  company: Company | null;
  isAuthenticated: boolean;
  setAuth: (company: Company, accessToken: string, refreshToken: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  company: null,
  isAuthenticated: !!localStorage.getItem('access_token'),

  setAuth: (company, accessToken, refreshToken) => {
    localStorage.setItem('access_token', accessToken);
    localStorage.setItem('refresh_token', refreshToken);
    set({ company, isAuthenticated: true });
  },

  logout: () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    set({ company: null, isAuthenticated: false });
  },
}));
