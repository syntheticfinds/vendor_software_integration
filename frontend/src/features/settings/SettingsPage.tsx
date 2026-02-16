import { useEffect, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { Mail, CheckCircle, XCircle, ExternalLink, Unplug, HardDrive, TicketCheck } from 'lucide-react';
import { getGmailAuthUrl, getGmailStatus, disconnectGmail, getDriveStatus, enableDriveSync, disableDriveSync, getJiraPollingStatus, enableJiraPolling, disableJiraPolling } from '../../api/integrations';

export function SettingsPage() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [flashMessage, setFlashMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Show flash message based on URL params (from OAuth callback redirect)
  useEffect(() => {
    const gmailParam = searchParams.get('gmail');
    if (gmailParam === 'success') {
      setFlashMessage({ type: 'success', text: 'Gmail connected successfully!' });
      searchParams.delete('gmail');
      setSearchParams(searchParams, { replace: true });
      queryClient.invalidateQueries({ queryKey: ['gmail-status'] });
    } else if (gmailParam === 'error') {
      const reason = searchParams.get('reason');
      const msg = reason === 'no_refresh_token'
        ? 'Failed to connect Gmail — no refresh token received. Try revoking access at myaccount.google.com and reconnecting.'
        : 'Failed to connect Gmail. Please try again.';
      setFlashMessage({ type: 'error', text: msg });
      searchParams.delete('gmail');
      searchParams.delete('reason');
      setSearchParams(searchParams, { replace: true });
    }
  }, [searchParams, setSearchParams, queryClient]);

  // Auto-dismiss flash message after 5 seconds
  useEffect(() => {
    if (flashMessage) {
      const timer = setTimeout(() => setFlashMessage(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [flashMessage]);

  const { data: gmailStatus, isLoading: gmailLoading } = useQuery({
    queryKey: ['gmail-status'],
    queryFn: getGmailStatus,
  });

  const connectGmailMutation = useMutation({
    mutationFn: getGmailAuthUrl,
    onSuccess: (data) => {
      window.location.href = data.authorization_url;
    },
  });

  const disconnectGmailMutation = useMutation({
    mutationFn: disconnectGmail,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['gmail-status'] });
      queryClient.invalidateQueries({ queryKey: ['drive-status'] });
      setFlashMessage({ type: 'success', text: 'Gmail disconnected.' });
    },
  });

  const { data: driveStatus, isLoading: driveLoading } = useQuery({
    queryKey: ['drive-status'],
    queryFn: getDriveStatus,
  });

  const enableDriveMutation = useMutation({
    mutationFn: enableDriveSync,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['drive-status'] });
      setFlashMessage({ type: 'success', text: 'Google Drive monitoring enabled.' });
    },
  });

  const disableDriveMutation = useMutation({
    mutationFn: disableDriveSync,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['drive-status'] });
      setFlashMessage({ type: 'success', text: 'Google Drive monitoring disabled.' });
    },
  });

  const { data: jiraPollingStatus, isLoading: jiraPollingLoading } = useQuery({
    queryKey: ['jira-polling-status'],
    queryFn: getJiraPollingStatus,
  });

  const enableJiraPollingMutation = useMutation({
    mutationFn: () => enableJiraPolling(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jira-polling-status'] });
      setFlashMessage({ type: 'success', text: 'Jira polling enabled.' });
    },
  });

  const disableJiraPollingMutation = useMutation({
    mutationFn: disableJiraPolling,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jira-polling-status'] });
      setFlashMessage({ type: 'success', text: 'Jira polling disabled.' });
    },
  });

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
        <p className="text-gray-600 text-sm mt-1">Manage your integrations and account settings.</p>
      </div>

      {/* Flash message */}
      {flashMessage && (
        <div
          className={`mb-4 px-4 py-3 rounded-md text-sm ${
            flashMessage.type === 'success'
              ? 'bg-green-50 text-green-800 border border-green-200'
              : 'bg-red-50 text-red-800 border border-red-200'
          }`}
        >
          {flashMessage.text}
        </div>
      )}

      <h2 className="text-lg font-semibold text-gray-900 mb-3">Integrations</h2>

      <div className="space-y-4">
        {/* Gmail Integration Card */}
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-red-50 rounded-lg flex items-center justify-center">
              <Mail className="w-5 h-5 text-red-600" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-gray-900">Gmail</h3>
              <p className="text-sm text-gray-500">Connect your Gmail account to monitor vendor emails.</p>
            </div>
          </div>

          {gmailLoading ? (
            <div className="text-sm text-gray-500">Checking connection status...</div>
          ) : gmailStatus?.connected ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-green-600" />
                <span className="text-sm font-medium text-green-700">Connected</span>
              </div>
              <div className="bg-gray-50 rounded-md p-3 space-y-1">
                <div className="text-sm">
                  <span className="text-gray-500">Account:</span>{' '}
                  <span className="text-gray-900 font-medium">{gmailStatus.email_address}</span>
                </div>
                {gmailStatus.connected_at && (
                  <div className="text-sm">
                    <span className="text-gray-500">Connected:</span>{' '}
                    <span className="text-gray-700">
                      {new Date(gmailStatus.connected_at).toLocaleDateString()}
                    </span>
                  </div>
                )}
                {gmailStatus.last_sync_at && (
                  <div className="text-sm">
                    <span className="text-gray-500">Last sync:</span>{' '}
                    <span className="text-gray-700">
                      {new Date(gmailStatus.last_sync_at).toLocaleString()}
                    </span>
                  </div>
                )}
              </div>
              <button
                onClick={() => disconnectGmailMutation.mutate()}
                disabled={disconnectGmailMutation.isPending}
                className="flex items-center gap-1.5 text-red-600 hover:text-red-700 text-sm font-medium cursor-pointer"
              >
                <Unplug className="w-4 h-4" />
                {disconnectGmailMutation.isPending ? 'Disconnecting...' : 'Disconnect Gmail'}
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <XCircle className="w-4 h-4 text-gray-400" />
                <span className="text-sm text-gray-500">Not connected</span>
              </div>
              <button
                onClick={() => connectGmailMutation.mutate()}
                disabled={connectGmailMutation.isPending}
                className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-50 cursor-pointer"
              >
                <ExternalLink className="w-4 h-4" />
                {connectGmailMutation.isPending ? 'Redirecting...' : 'Connect Gmail'}
              </button>
            </div>
          )}
        </div>

        {/* Google Drive Integration Card */}
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-blue-50 rounded-lg flex items-center justify-center">
              <HardDrive className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-gray-900">Google Drive</h3>
              <p className="text-sm text-gray-500">Monitor Drive files for vendor software documents.</p>
            </div>
          </div>

          {driveLoading ? (
            <div className="text-sm text-gray-500">Checking Drive status...</div>
          ) : driveStatus?.enabled ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-green-600" />
                <span className="text-sm font-medium text-green-700">Monitoring active</span>
              </div>
              <div className="bg-gray-50 rounded-md p-3 space-y-1">
                {driveStatus.last_sync_at && (
                  <div className="text-sm">
                    <span className="text-gray-500">Last sync:</span>{' '}
                    <span className="text-gray-700">
                      {new Date(driveStatus.last_sync_at).toLocaleString()}
                    </span>
                  </div>
                )}
                <div className="text-sm">
                  <span className="text-gray-500">Sync interval:</span>{' '}
                  <span className="text-gray-700">Every 5 minutes</span>
                </div>
              </div>
              <button
                onClick={() => disableDriveMutation.mutate()}
                disabled={disableDriveMutation.isPending}
                className="flex items-center gap-1.5 text-red-600 hover:text-red-700 text-sm font-medium cursor-pointer"
              >
                <Unplug className="w-4 h-4" />
                {disableDriveMutation.isPending ? 'Disabling...' : 'Disable Drive Monitoring'}
              </button>
            </div>
          ) : driveStatus?.available ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <XCircle className="w-4 h-4 text-gray-400" />
                <span className="text-sm text-gray-500">Available but not enabled</span>
              </div>
              <button
                onClick={() => enableDriveMutation.mutate()}
                disabled={enableDriveMutation.isPending}
                className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-50 cursor-pointer"
              >
                <HardDrive className="w-4 h-4" />
                {enableDriveMutation.isPending ? 'Enabling...' : 'Enable Drive Monitoring'}
              </button>
            </div>
          ) : driveStatus?.needs_reauth ? (
            <div className="space-y-3">
              <div className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
                Gmail is connected but Drive access was not granted. Re-connect Gmail to enable Drive monitoring.
              </div>
              <button
                onClick={() => connectGmailMutation.mutate()}
                disabled={connectGmailMutation.isPending}
                className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-50 cursor-pointer"
              >
                <ExternalLink className="w-4 h-4" />
                {connectGmailMutation.isPending ? 'Redirecting...' : 'Re-connect Gmail with Drive access'}
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <XCircle className="w-4 h-4 text-gray-400" />
                <span className="text-sm text-gray-500">Connect Gmail first to enable Drive monitoring</span>
              </div>
            </div>
          )}
        </div>

        {/* Jira Polling Integration Card */}
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-indigo-50 rounded-lg flex items-center justify-center">
              <TicketCheck className="w-5 h-5 text-indigo-600" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-gray-900">Jira Polling</h3>
              <p className="text-sm text-gray-500">Poll Jira Cloud for issues to detect vendor software.</p>
            </div>
          </div>

          {jiraPollingLoading ? (
            <div className="text-sm text-gray-500">Checking Jira polling status...</div>
          ) : jiraPollingStatus?.enabled ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-green-600" />
                <span className="text-sm font-medium text-green-700">Polling active</span>
              </div>
              <div className="bg-gray-50 rounded-md p-3 space-y-1">
                {jiraPollingStatus.last_sync_at && (
                  <div className="text-sm">
                    <span className="text-gray-500">Last sync:</span>{' '}
                    <span className="text-gray-700">
                      {new Date(jiraPollingStatus.last_sync_at).toLocaleString()}
                    </span>
                  </div>
                )}
                <div className="text-sm">
                  <span className="text-gray-500">Issues synced:</span>{' '}
                  <span className="text-gray-700">{jiraPollingStatus.issues_synced}</span>
                </div>
                <div className="text-sm">
                  <span className="text-gray-500">Sync interval:</span>{' '}
                  <span className="text-gray-700">Every 5 minutes</span>
                </div>
                {jiraPollingStatus.jql_filter && (
                  <div className="text-sm">
                    <span className="text-gray-500">JQL filter:</span>{' '}
                    <span className="text-gray-700 font-mono text-xs">{jiraPollingStatus.jql_filter}</span>
                  </div>
                )}
              </div>
              <button
                onClick={() => disableJiraPollingMutation.mutate()}
                disabled={disableJiraPollingMutation.isPending}
                className="flex items-center gap-1.5 text-red-600 hover:text-red-700 text-sm font-medium cursor-pointer"
              >
                <Unplug className="w-4 h-4" />
                {disableJiraPollingMutation.isPending ? 'Disabling...' : 'Disable Jira Polling'}
              </button>
            </div>
          ) : jiraPollingStatus?.available ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <XCircle className="w-4 h-4 text-gray-400" />
                <span className="text-sm text-gray-500">Available but not enabled</span>
              </div>
              <button
                onClick={() => enableJiraPollingMutation.mutate()}
                disabled={enableJiraPollingMutation.isPending}
                className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 cursor-pointer"
              >
                <TicketCheck className="w-4 h-4" />
                {enableJiraPollingMutation.isPending ? 'Enabling...' : 'Enable Jira Polling'}
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
                Jira API credentials are not configured. Set JIRA_SITE_URL, JIRA_USER_EMAIL, and JIRA_API_TOKEN in the server environment.
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
