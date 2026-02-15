import apiClient from './client';

export interface SignalEvent {
  id: string;
  company_id: string;
  software_id: string;
  source_type: string;
  source_id: string | null;
  event_type: string;
  severity: string | null;
  title: string | null;
  body: string | null;
  event_metadata: Record<string, unknown> | null;
  occurred_at: string;
  created_at: string;
}

export interface SignalEventList {
  items: SignalEvent[];
  total: number;
}

export interface HealthScore {
  id: string;
  company_id: string;
  software_id: string;
  score: number;
  category_breakdown: Record<string, number>;
  signal_summary: string | null;
  signal_count: number;
  confidence_tier: string;
  scoring_window_start: string;
  scoring_window_end: string;
  created_at: string;
}

export interface ReviewDraft {
  id: string;
  company_id: string;
  software_id: string;
  health_score_id: string | null;
  draft_subject: string | null;
  draft_body: string;
  confidence_tier: string;
  status: string;
  edited_body: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export async function ingestSignals(software_id: string, source_type?: string) {
  const res = await apiClient.post<{ ingested_count: number; software_id: string }>(
    '/signals/ingest',
    { software_id, source_type },
  );
  return res.data;
}

export async function getSignalEvents(params?: {
  software_id?: string;
  source_type?: string;
  severity?: string;
  page?: number;
  per_page?: number;
}): Promise<SignalEventList> {
  const res = await apiClient.get<SignalEventList>('/signals/events', { params });
  return res.data;
}

export async function analyzeSignals(software_id: string, window_days = 30) {
  const res = await apiClient.post<{ status: string; software_id: string }>(
    '/signals/analyze',
    { software_id, window_days },
  );
  return res.data;
}

export async function getHealthScores(software_id?: string): Promise<HealthScore[]> {
  const res = await apiClient.get<HealthScore[]>('/signals/health-scores', {
    params: software_id ? { software_id } : undefined,
  });
  return res.data;
}

export async function getReviewDrafts(status?: string): Promise<ReviewDraft[]> {
  const res = await apiClient.get<ReviewDraft[]>('/signals/review-drafts', {
    params: status ? { status } : undefined,
  });
  return res.data;
}

export async function getReviewDraft(id: string): Promise<ReviewDraft> {
  const res = await apiClient.get<ReviewDraft>(`/signals/review-drafts/${id}`);
  return res.data;
}

export async function updateReviewDraft(
  id: string,
  data: { status: string; edited_body?: string },
): Promise<ReviewDraft> {
  const res = await apiClient.patch<ReviewDraft>(`/signals/review-drafts/${id}`, data);
  return res.data;
}

export async function sendReviewDraft(id: string) {
  const res = await apiClient.post<{ status: string; draft_id: string }>(
    `/signals/review-drafts/${id}/send`,
  );
  return res.data;
}
