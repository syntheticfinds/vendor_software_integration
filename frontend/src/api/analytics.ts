import apiClient from './client';

export interface OverviewStats {
  total_software: number;
  active_software: number;
  total_signals: number;
  avg_health_score: number | null;
  pending_reviews: number;
  critical_signals: number;
}

export interface SoftwareHealthSummary {
  software_id: string;
  software_name: string;
  vendor_name: string;
  latest_score: number | null;
  signal_count: number;
  critical_count: number;
  status: string;
}

export interface HealthTrendPoint {
  date: string;
  score: number;
  software_id: string;
  software_name: string;
}

export interface IssueCategoryBreakdown {
  category: string;
  count: number;
  percentage: number;
}

export interface SoftwareBurden {
  software_id: string;
  software_name: string;
  vendor_name: string;
  total_signals: number;
  critical_signals: number;
  high_signals: number;
  open_tickets: number;
  burden_score: number;
}

export interface SourceDistribution {
  source_type: string;
  count: number;
}

export async function getOverview(softwareIds?: string[]): Promise<OverviewStats> {
  const res = await apiClient.get<OverviewStats>('/analytics/overview', {
    params: softwareIds ? { software_ids: softwareIds } : undefined,
  });
  return res.data;
}

export async function getSoftwareSummary(): Promise<SoftwareHealthSummary[]> {
  const res = await apiClient.get<SoftwareHealthSummary[]>('/analytics/software-summary');
  return res.data;
}

export async function getHealthTrends(days = 30): Promise<HealthTrendPoint[]> {
  const res = await apiClient.get<HealthTrendPoint[]>('/analytics/health-trends', { params: { days } });
  return res.data;
}

export async function getIssueCategories(softwareIds?: string[]): Promise<IssueCategoryBreakdown[]> {
  const res = await apiClient.get<IssueCategoryBreakdown[]>('/analytics/issue-categories', {
    params: softwareIds ? { software_ids: softwareIds } : undefined,
  });
  return res.data;
}

export async function getSupportBurden(): Promise<SoftwareBurden[]> {
  const res = await apiClient.get<SoftwareBurden[]>('/analytics/support-burden');
  return res.data;
}

export async function getSourceDistribution(softwareIds?: string[]): Promise<SourceDistribution[]> {
  const res = await apiClient.get<SourceDistribution[]>('/analytics/source-distribution', {
    params: softwareIds ? { software_ids: softwareIds } : undefined,
  });
  return res.data;
}
