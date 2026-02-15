import apiClient from './client';

export interface PublicSoftware {
  id: string;
  vendor_name: string;
  software_name: string;
  avg_health_score: number | null;
  company_count: number;
  category_scores: Record<string, number> | null;
  common_issues: string | null;
  sentiment_summary: string | null;
}

export interface ChatResponse {
  reply: string;
  citations: Array<{ vendor: string; software: string; score: number | null }> | null;
  session_token: string;
}

export async function getPublicIndex(): Promise<PublicSoftware[]> {
  const res = await apiClient.get<PublicSoftware[]>('/portal/software-index');
  return res.data;
}

export async function getPublicSoftware(vendor: string, name: string): Promise<PublicSoftware> {
  const res = await apiClient.get<PublicSoftware>(`/portal/software/${vendor}/${name}`);
  return res.data;
}

export async function sendChatMessage(message: string, sessionToken?: string): Promise<ChatResponse> {
  const res = await apiClient.post<ChatResponse>('/portal/chat', {
    message,
    session_token: sessionToken,
  });
  return res.data;
}
