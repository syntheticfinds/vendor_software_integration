import apiClient from './client';

export interface Company {
  id: string;
  company_name: string;
  industry: string | null;
  company_size: string | null;
  primary_email: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AuthResponse {
  company: Company;
  access_token: string;
  refresh_token: string;
}

export interface RegisterPayload {
  company_name: string;
  industry?: string;
  company_size?: string;
  primary_email: string;
  password: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export async function register(data: RegisterPayload): Promise<AuthResponse> {
  const res = await apiClient.post<AuthResponse>('/auth/register', data);
  return res.data;
}

export async function login(data: LoginPayload): Promise<AuthResponse> {
  const res = await apiClient.post<AuthResponse>('/auth/login', data);
  return res.data;
}

export async function getMe(): Promise<Company> {
  const res = await apiClient.get<Company>('/auth/me');
  return res.data;
}
