import apiClient from './client';

export interface Campaign {
  id: string;
  vendor_name: string;
  software_name: string;
  target_criteria: Record<string, unknown> | null;
  message_template: string;
  status: string;
  created_at: string;
}

export interface OutreachMessage {
  id: string;
  campaign_id: string;
  target_company_id: string;
  message_body: string;
  status: string;
  sent_at: string | null;
  created_at: string;
}

export async function createCampaign(data: {
  vendor_name: string;
  software_name: string;
  message_template: string;
  target_criteria?: Record<string, unknown>;
}): Promise<Campaign> {
  const res = await apiClient.post<Campaign>('/outreach/campaigns', data);
  return res.data;
}

export async function getCampaigns(): Promise<Campaign[]> {
  const res = await apiClient.get<Campaign[]>('/outreach/campaigns');
  return res.data;
}

export async function sendCampaign(id: string) {
  const res = await apiClient.post<{ campaign_id: string; messages_sent: number; status: string }>(
    `/outreach/campaigns/${id}/send`,
  );
  return res.data;
}

export async function getCampaignMessages(id: string): Promise<OutreachMessage[]> {
  const res = await apiClient.get<OutreachMessage[]>(`/outreach/campaigns/${id}/messages`);
  return res.data;
}
