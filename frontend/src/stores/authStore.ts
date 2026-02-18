import { create } from 'zustand';
import type { Company } from '../api/auth';

function loadCompany(): Company | null {
  try {
    const raw = sessionStorage.getItem('company');
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

interface AuthState {
  company: Company | null;
  isAuthenticated: boolean;
  setAuth: (company: Company, accessToken: string, refreshToken: string) => void;
  setCompany: (company: Company) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  company: loadCompany(),
  isAuthenticated: !!sessionStorage.getItem('access_token'),

  setAuth: (company, accessToken, refreshToken) => {
    sessionStorage.setItem('access_token', accessToken);
    sessionStorage.setItem('refresh_token', refreshToken);
    sessionStorage.setItem('company', JSON.stringify(company));
    set({ company, isAuthenticated: true });
  },

  setCompany: (company) => {
    sessionStorage.setItem('company', JSON.stringify(company));
    set({ company });
  },

  logout: () => {
    sessionStorage.removeItem('access_token');
    sessionStorage.removeItem('refresh_token');
    sessionStorage.removeItem('company');
    set({ company: null, isAuthenticated: false });
  },
}));
