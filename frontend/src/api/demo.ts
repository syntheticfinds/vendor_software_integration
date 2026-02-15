import apiClient from './client';

export interface DemoCompany {
  id: string;
  company_name: string;
  industry: string | null;
  company_size: string | null;
}

export async function getDemoCompanies(): Promise<DemoCompany[]> {
  const res = await apiClient.get<DemoCompany[]>('/demo/companies');
  return res.data;
}

export interface ComposeEmailPayload {
  company_id: string;
  sender: string;
  sender_name?: string;
  recipient?: string;
  subject: string;
  body: string;
  category: 'integration' | 'feature_request' | 'issue_debug';
  direction: 'inbound' | 'outbound';
  auto_detect: boolean;
  severity?: 'low' | 'medium' | 'high' | 'critical';
  occurred_at?: string;
}

export interface ComposeEmailResponse {
  email_id: string;
  sender: string;
  subject: string;
  category: string;
  direction: string;
  detection_queued: boolean;
  signal_created: boolean;
  analysis_queued: boolean;
}

export async function composeEmail(data: ComposeEmailPayload): Promise<ComposeEmailResponse> {
  const res = await apiClient.post<ComposeEmailResponse>('/demo/compose-email', data);
  return res.data;
}

export interface ComposeSignalPayload {
  company_id: string;
  source_type: 'jira';
  event_type: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  title: string;
  body: string;
  source_id?: string;
  reporter?: string;
  occurred_at?: string;
}

export interface ComposeSignalResponse {
  signal_id: string;
  software_id: string;
  source_type: string;
  event_type: string;
  severity: string;
  title: string;
}

export async function composeSignal(data: ComposeSignalPayload): Promise<ComposeSignalResponse> {
  const res = await apiClient.post<ComposeSignalResponse>('/demo/compose-signal', data);
  return res.data;
}
