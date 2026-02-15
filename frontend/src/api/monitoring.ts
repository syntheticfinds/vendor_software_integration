import apiClient from './client';

export interface Detection {
  id: string;
  company_id: string;
  source_email_id: string | null;
  detected_vendor_name: string;
  detected_software: string;
  confidence_score: number;
  status: string;
  agent_reasoning: string | null;
  detected_at: string;
  created_at: string;
}

export interface DetectionList {
  items: Detection[];
  total: number;
}

export interface ScanResponse {
  scan_id: string;
  status: string;
  queued_emails: number;
}

export async function triggerScan(source = 'mock'): Promise<ScanResponse> {
  const res = await apiClient.post<ScanResponse>('/monitoring/scan', { source });
  return res.data;
}

export async function getDetections(params?: {
  status?: string;
  page?: number;
  per_page?: number;
}): Promise<DetectionList> {
  const res = await apiClient.get<DetectionList>('/monitoring/detections', { params });
  return res.data;
}

export async function updateDetection(id: string, status: 'confirmed' | 'dismissed'): Promise<Detection> {
  const res = await apiClient.patch<Detection>(`/monitoring/detections/${id}`, { status });
  return res.data;
}
