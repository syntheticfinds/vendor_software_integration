import apiClient from './client';

export interface IndexEntry {
  vendor_name: string;
  software_name: string;
  auto_category: string | null;
  avg_health_score: number | null;
  company_count: number;
}

export interface IndexResponse {
  items: IndexEntry[];
  categories: string[];
}

export interface DistributionItem {
  label: string;
  count: number;
}

export interface CUJStage {
  order: number;
  name: string;
  description: string;
  satisfied_count: number;
  dissatisfied_count: number;
  total: number;
  avg_duration_days: number | null;
}

export interface CUJResponse {
  vendor_name: string;
  software_name: string;
  stages: CUJStage[];
}

export interface SolutionDetailResponse {
  vendor_name: string;
  software_name: string;
  auto_category: string | null;
  avg_health_score: number | null;
  company_count: number;
  industry_distribution: DistributionItem[];
  size_distribution: DistributionItem[];
  cuj: CUJResponse | null;
}

export interface DrilldownCompany {
  company_id: string;
  company_name: string;
  industry: string | null;
  company_size: string | null;
  satisfied: boolean;
  contacts: string[];
}

export interface DrilldownResponse {
  stage_order: number;
  stage_name: string;
  companies: DrilldownCompany[];
}

export interface GenerateOutreachResponse {
  company_name: string;
  contact_name: string | null;
  generated_message: string;
  pain_points: string[];
}

export async function getIntelligenceIndex(params?: {
  category?: string;
  search?: string;
}): Promise<IndexResponse> {
  const res = await apiClient.get<IndexResponse>('/intelligence/index', { params });
  return res.data;
}

export async function rebuildIntelligenceIndex(): Promise<{ status: string; entries: number }> {
  const res = await apiClient.post<{ status: string; entries: number }>('/intelligence/rebuild');
  return res.data;
}

export async function getSolutionDetail(
  vendorName: string,
  softwareName: string,
): Promise<SolutionDetailResponse> {
  const res = await apiClient.get<SolutionDetailResponse>(
    `/intelligence/solution/${encodeURIComponent(vendorName)}/${encodeURIComponent(softwareName)}`,
  );
  return res.data;
}

export async function getCUJDrilldown(
  vendorName: string,
  softwareName: string,
  stage: number,
): Promise<DrilldownResponse> {
  const res = await apiClient.get<DrilldownResponse>(
    `/intelligence/cuj/${encodeURIComponent(vendorName)}/${encodeURIComponent(softwareName)}/drilldown/${stage}`,
  );
  return res.data;
}

export async function generateOutreach(
  vendorName: string,
  softwareName: string,
  stageOrder: number,
  companyId: string,
  contactName?: string,
): Promise<GenerateOutreachResponse> {
  const res = await apiClient.post<GenerateOutreachResponse>('/intelligence/outreach', {
    vendor_name: vendorName,
    software_name: softwareName,
    stage_order: stageOrder,
    company_id: companyId,
    contact_name: contactName ?? null,
  });
  return res.data;
}
