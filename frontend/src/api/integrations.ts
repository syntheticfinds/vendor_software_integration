import apiClient from './client';

export interface GmailAuthUrl {
  authorization_url: string;
}

export interface GmailStatus {
  connected: boolean;
  email_address: string | null;
  is_active: boolean;
  scopes: string | null;
  last_sync_at: string | null;
  connected_at: string | null;
}

export interface GmailDisconnectResponse {
  status: string;
  message: string;
}

export async function getGmailAuthUrl(): Promise<GmailAuthUrl> {
  const res = await apiClient.get<GmailAuthUrl>('/integrations/gmail/authorize');
  return res.data;
}

export async function getGmailStatus(): Promise<GmailStatus> {
  const res = await apiClient.get<GmailStatus>('/integrations/gmail/status');
  return res.data;
}

export async function disconnectGmail(): Promise<GmailDisconnectResponse> {
  const res = await apiClient.delete<GmailDisconnectResponse>('/integrations/gmail');
  return res.data;
}

// --- Jira Webhook (per-software, supports shared URLs) ---

export interface JiraWebhookSetup {
  webhook_url: string;
  webhook_secret: string;
  software_id: string;
  is_new_url: boolean;
  instructions: string;
}

export interface JiraWebhookInfo {
  software_id: string;
  software_name: string | null;
  vendor_name: string | null;
  webhook_url: string;
  webhook_secret: string;
  is_active: boolean;
  events_received: number;
  last_event_at: string | null;
  connected_at: string | null;
}

export async function setupJiraWebhook(
  softwareId: string,
  reuseWebhookSecret?: string,
): Promise<JiraWebhookSetup> {
  const res = await apiClient.post<JiraWebhookSetup>('/integrations/jira/setup', {
    software_id: softwareId,
    reuse_webhook_secret: reuseWebhookSecret ?? null,
  });
  return res.data;
}

export async function getJiraWebhooks(): Promise<{ webhooks: JiraWebhookInfo[] }> {
  const res = await apiClient.get<{ webhooks: JiraWebhookInfo[] }>('/integrations/jira/webhooks');
  return res.data;
}

export async function disconnectJira(softwareId: string): Promise<{ status: string; message: string }> {
  const res = await apiClient.delete(`/integrations/jira/${softwareId}`);
  return res.data;
}

// --- Google Drive ---

export interface DriveStatus {
  available: boolean;
  enabled: boolean;
  last_sync_at: string | null;
  needs_reauth: boolean;
}

export async function getDriveStatus(): Promise<DriveStatus> {
  const res = await apiClient.get<DriveStatus>('/integrations/drive/status');
  return res.data;
}

export async function enableDriveSync(): Promise<{ status: string }> {
  const res = await apiClient.post<{ status: string }>('/integrations/drive/enable');
  return res.data;
}

export async function disableDriveSync(): Promise<{ status: string }> {
  const res = await apiClient.post<{ status: string }>('/integrations/drive/disable');
  return res.data;
}

// --- Jira Polling ---

export interface JiraPollingStatus {
  available: boolean;
  enabled: boolean;
  last_sync_at: string | null;
  issues_synced: number;
  jql_filter: string | null;
}

export async function getJiraPollingStatus(): Promise<JiraPollingStatus> {
  const res = await apiClient.get<JiraPollingStatus>('/integrations/jira-polling/status');
  return res.data;
}

export async function enableJiraPolling(jqlFilter?: string): Promise<{ status: string }> {
  const res = await apiClient.post<{ status: string }>('/integrations/jira-polling/enable', {
    jql_filter: jqlFilter ?? null,
  });
  return res.data;
}

export async function disableJiraPolling(): Promise<{ status: string }> {
  const res = await apiClient.post<{ status: string }>('/integrations/jira-polling/disable');
  return res.data;
}
