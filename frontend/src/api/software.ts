import apiClient from './client';

export interface Software {
  id: string;
  company_id: string;
  vendor_name: string;
  software_name: string;
  intended_use: string | null;
  jira_workspace: string | null;
  support_email: string | null;
  status: string;
  detection_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface SoftwareList {
  items: Software[];
  total: number;
}

export interface CreateSoftwarePayload {
  vendor_name: string;
  software_name: string;
  intended_use?: string;
  jira_workspace?: string;
  support_email?: string;
  detection_id?: string;
}

export async function getSoftwareList(params?: {
  status?: string;
  search?: string;
  page?: number;
}): Promise<SoftwareList> {
  const res = await apiClient.get<SoftwareList>('/software', { params });
  return res.data;
}

export async function createSoftware(data: CreateSoftwarePayload): Promise<Software> {
  const res = await apiClient.post<Software>('/software', data);
  return res.data;
}

export interface UpdateSoftwarePayload {
  vendor_name?: string;
  software_name?: string;
  intended_use?: string | null;
  jira_workspace?: string | null;
  support_email?: string | null;
}

export async function updateSoftware(id: string, data: UpdateSoftwarePayload): Promise<Software> {
  const res = await apiClient.patch<Software>(`/software/${id}`, data);
  return res.data;
}

export async function deleteSoftware(id: string): Promise<void> {
  await apiClient.delete(`/software/${id}`);
}
