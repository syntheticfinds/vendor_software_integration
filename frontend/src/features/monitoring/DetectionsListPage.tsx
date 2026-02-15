import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getDetections, updateDetection } from '../../api/monitoring';
import { createSoftware } from '../../api/software';
import { setupJiraWebhook, getJiraWebhooks } from '../../api/integrations';
import type { JiraWebhookSetup, JiraWebhookInfo } from '../../api/integrations';
import type { Detection } from '../../api/monitoring';
import { Check, X, AlertCircle, ChevronUp, Copy } from 'lucide-react';

/** Group webhooks by secret to get unique URLs with their linked software. */
function getUniqueWebhookUrls(webhooks: JiraWebhookInfo[]) {
  const bySecret = new Map<string, { url: string; secret: string; software: { name: string; vendor: string }[] }>();
  for (const wh of webhooks) {
    const existing = bySecret.get(wh.webhook_secret);
    if (existing) {
      existing.software.push({ name: wh.software_name || 'Unknown', vendor: wh.vendor_name || '' });
    } else {
      bySecret.set(wh.webhook_secret, {
        url: wh.webhook_url,
        secret: wh.webhook_secret,
        software: [{ name: wh.software_name || 'Unknown', vendor: wh.vendor_name || '' }],
      });
    }
  }
  return Array.from(bySecret.values());
}

function WebhookSelector({
  webhooks,
  selectedSecret,
  onSelect,
}: {
  webhooks: JiraWebhookInfo[];
  selectedSecret: string | null; // null = create new
  onSelect: (secret: string | null) => void;
}) {
  const options = getUniqueWebhookUrls(webhooks);
  if (options.length === 0) return null;

  return (
    <div className="space-y-2">
      <label className="block text-xs font-medium text-gray-600">Webhook URL</label>
      {options.map((opt) => (
        <label
          key={opt.secret}
          className={`flex items-start gap-2 p-2 rounded-md border cursor-pointer ${
            selectedSecret === opt.secret
              ? 'border-blue-400 bg-blue-50'
              : 'border-gray-200 hover:bg-gray-50'
          }`}
        >
          <input
            type="radio"
            name="webhook-choice"
            checked={selectedSecret === opt.secret}
            onChange={() => onSelect(opt.secret)}
            className="mt-0.5 text-blue-600 focus:ring-blue-500"
          />
          <div className="flex-1 min-w-0">
            <div className="text-xs text-gray-700">
              Use existing webhook
              <span className="text-gray-400 ml-1">
                (used by: {opt.software.map((s) => `${s.name} by ${s.vendor}`).join(', ')})
              </span>
            </div>
            <code className="text-[11px] text-gray-500 break-all">{opt.url}</code>
          </div>
        </label>
      ))}
      <label
        className={`flex items-start gap-2 p-2 rounded-md border cursor-pointer ${
          selectedSecret === null
            ? 'border-blue-400 bg-blue-50'
            : 'border-gray-200 hover:bg-gray-50'
        }`}
      >
        <input
          type="radio"
          name="webhook-choice"
          checked={selectedSecret === null}
          onChange={() => onSelect(null)}
          className="mt-0.5 text-blue-600 focus:ring-blue-500"
        />
        <div className="text-xs text-gray-700">Create a new webhook URL</div>
      </label>
    </div>
  );
}

export function DetectionsListPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [registeringId, setRegisteringId] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['detections', statusFilter],
    queryFn: () => getDetections({ status: statusFilter }),
  });

  const { data: jiraData } = useQuery({
    queryKey: ['jira-webhooks'],
    queryFn: getJiraWebhooks,
  });

  const allWebhooks = jiraData?.webhooks || [];

  const updateMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: 'confirmed' | 'dismissed' }) =>
      updateDetection(id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['detections'] }),
  });

  const confidenceColor = (score: number) => {
    if (score >= 0.8) return 'text-green-700 bg-green-50';
    if (score >= 0.6) return 'text-yellow-700 bg-yellow-50';
    return 'text-red-700 bg-red-50';
  };

  const statusBadge = (status: string) => {
    const styles: Record<string, string> = {
      pending: 'bg-yellow-100 text-yellow-800',
      confirmed: 'bg-green-100 text-green-800',
      dismissed: 'bg-gray-100 text-gray-600',
    };
    return styles[status] || 'bg-gray-100 text-gray-600';
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Software Detections</h1>
          <p className="text-gray-600 text-sm mt-1">
            New vendor software detected from your email stream
          </p>
        </div>
      </div>

      <div className="flex gap-2 mb-4">
        {['all', 'pending', 'confirmed', 'dismissed'].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s === 'all' ? undefined : s)}
            className={`px-3 py-1 rounded-full text-sm cursor-pointer ${
              (s === 'all' && !statusFilter) || statusFilter === s
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="text-center py-12 text-gray-500">Loading...</div>
      ) : !data?.items.length ? (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
          <AlertCircle className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500">No detections yet. New vendor software will appear here as emails are synced.</p>
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 text-sm font-medium text-gray-600">Vendor</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-gray-600">Software</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-gray-600">Confidence</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-gray-600">Status</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-gray-600">Detected</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-gray-600">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.items.map((d: Detection) => (
                <DetectionRow
                  key={d.id}
                  detection={d}
                  isRegistering={registeringId === d.id}
                  onStartRegister={() => setRegisteringId(d.id)}
                  onCancelRegister={() => setRegisteringId(null)}
                  onDismiss={() => updateMutation.mutate({ id: d.id, status: 'dismissed' })}
                  allWebhooks={allWebhooks}
                  onRegistered={() => {
                    setRegisteringId(null);
                    updateMutation.mutate({ id: d.id, status: 'confirmed' });
                    queryClient.invalidateQueries({ queryKey: ['software'] });
                    queryClient.invalidateQueries({ queryKey: ['jira-webhooks'] });
                  }}
                  confidenceColor={confidenceColor}
                  statusBadge={statusBadge}
                />
              ))}
            </tbody>
          </table>
          <div className="px-4 py-3 border-t border-gray-200 text-sm text-gray-500">
            {data.total} detection{data.total !== 1 ? 's' : ''} total
          </div>
        </div>
      )}
    </div>
  );
}

function DetectionRow({
  detection: d,
  isRegistering,
  allWebhooks,
  onStartRegister,
  onCancelRegister,
  onDismiss,
  onRegistered,
  confidenceColor,
  statusBadge,
}: {
  detection: Detection;
  isRegistering: boolean;
  allWebhooks: JiraWebhookInfo[];
  onStartRegister: () => void;
  onCancelRegister: () => void;
  onDismiss: () => void;
  onRegistered: () => void;
  confidenceColor: (score: number) => string;
  statusBadge: (status: string) => string;
}) {
  return (
    <>
      <tr className="hover:bg-gray-50">
        <td className="px-4 py-3 text-sm font-medium text-gray-900">{d.detected_vendor_name}</td>
        <td className="px-4 py-3 text-sm text-gray-700">{d.detected_software}</td>
        <td className="px-4 py-3">
          <span className={`text-xs font-medium px-2 py-1 rounded ${confidenceColor(d.confidence_score)}`}>
            {(d.confidence_score * 100).toFixed(0)}%
          </span>
        </td>
        <td className="px-4 py-3">
          <span className={`text-xs font-medium px-2 py-1 rounded ${statusBadge(d.status)}`}>
            {d.status}
          </span>
        </td>
        <td className="px-4 py-3 text-sm text-gray-500">
          {new Date(d.detected_at).toLocaleDateString()}
        </td>
        <td className="px-4 py-3">
          {d.status === 'pending' && !isRegistering && (
            <div className="flex gap-1">
              <button
                onClick={onStartRegister}
                className="p-1 text-green-600 hover:bg-green-50 rounded cursor-pointer"
                title="Confirm & Register"
              >
                <Check className="w-4 h-4" />
              </button>
              <button
                onClick={onDismiss}
                className="p-1 text-red-600 hover:bg-red-50 rounded cursor-pointer"
                title="Dismiss"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          )}
          {d.status === 'pending' && isRegistering && (
            <button
              onClick={onCancelRegister}
              className="p-1 text-gray-500 hover:bg-gray-100 rounded cursor-pointer"
              title="Collapse"
            >
              <ChevronUp className="w-4 h-4" />
            </button>
          )}
        </td>
      </tr>
      {isRegistering && (
        <tr>
          <td colSpan={6} className="px-4 py-0">
            <InlineRegistrationForm
              vendorName={d.detected_vendor_name}
              softwareName={d.detected_software}
              detectionId={d.id}
              allWebhooks={allWebhooks}
              onCancel={onCancelRegister}
              onSuccess={onRegistered}
            />
          </td>
        </tr>
      )}
    </>
  );
}

function InlineRegistrationForm({
  vendorName,
  softwareName,
  detectionId,
  allWebhooks,
  onCancel,
  onSuccess,
}: {
  vendorName: string;
  softwareName: string;
  detectionId: string;
  allWebhooks: JiraWebhookInfo[];
  onCancel: () => void;
  onSuccess: () => void;
}) {
  const [intendedUse, setIntendedUse] = useState('');
  const [enableJira, setEnableJira] = useState(false);
  const [reuseSecret, setReuseSecret] = useState<string | null>(null);
  const [supportEmail, setSupportEmail] = useState('');
  const [jiraSetup, setJiraSetup] = useState<JiraWebhookSetup | null>(null);
  const [copied, setCopied] = useState(false);

  const existingOptions = getUniqueWebhookUrls(allWebhooks);

  const mutation = useMutation({
    mutationFn: () =>
      createSoftware({
        vendor_name: vendorName,
        software_name: softwareName,
        intended_use: intendedUse || undefined,
        support_email: supportEmail || undefined,
        detection_id: detectionId,
      }),
    onSuccess: async (software) => {
      if (enableJira) {
        try {
          const setup = await setupJiraWebhook(software.id, reuseSecret ?? undefined);
          setJiraSetup(setup);
          return;
        } catch {
          // Webhook setup failed but registration succeeded
        }
      }
      onSuccess();
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    mutation.mutate();
  };

  const copyUrl = () => {
    if (jiraSetup) {
      navigator.clipboard.writeText(jiraSetup.webhook_url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // Show Jira webhook result after successful registration
  if (jiraSetup) {
    return (
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 my-3 space-y-3">
        <p className="text-sm font-medium text-blue-900">
          <strong>{softwareName}</strong> registered.
          {jiraSetup.is_new_url
            ? ' Add this webhook URL to your Jira project.'
            : ' This software now shares an existing Jira webhook URL.'}
        </p>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Webhook URL</label>
          <div className="flex items-center gap-2">
            <input
              readOnly
              value={jiraSetup.webhook_url}
              className="flex-1 bg-white border border-gray-300 rounded-md px-3 py-1.5 text-sm text-gray-800 font-mono select-all"
              onClick={(e) => (e.target as HTMLInputElement).select()}
            />
            <button
              onClick={copyUrl}
              className="flex items-center gap-1 px-3 py-1.5 text-sm font-medium rounded-md border border-gray-300 bg-white hover:bg-gray-50 cursor-pointer"
            >
              {copied ? (
                <><Check className="w-4 h-4 text-green-600" /> Copied</>
              ) : (
                <><Copy className="w-4 h-4" /> Copy</>
              )}
            </button>
          </div>
        </div>
        {jiraSetup.is_new_url && (
          <div className="bg-white border border-blue-200 rounded-md p-3">
            <h4 className="text-xs font-semibold text-blue-900 mb-1.5">How to add this webhook in Jira</h4>
            <ol className="text-xs text-blue-800 space-y-1 list-decimal list-inside">
              <li>Go to <span className="font-medium">Settings &rarr; System &rarr; WebHooks</span></li>
              <li>Click <span className="font-medium">Create a WebHook</span></li>
              <li>Paste the webhook URL above</li>
              <li>Select events: Issue created, updated, deleted; Comment created, updated</li>
              <li>Click <span className="font-medium">Create</span></li>
            </ol>
          </div>
        )}
        <button
          onClick={onSuccess}
          className="bg-blue-600 text-white px-3 py-1.5 rounded-md text-sm font-medium hover:bg-blue-700 cursor-pointer"
        >
          Done
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="bg-blue-50 border border-blue-200 rounded-lg p-4 my-3 space-y-3">
      <p className="text-sm font-medium text-blue-900">
        Register <strong>{softwareName}</strong> by {vendorName}
      </p>

      <div>
        <label htmlFor={`use-${detectionId}`} className="block text-xs font-medium text-gray-600 mb-1">
          Intended Use <span className="text-gray-400">(optional)</span>
        </label>
        <textarea
          id={`use-${detectionId}`}
          value={intendedUse}
          onChange={(e) => setIntendedUse(e.target.value)}
          rows={2}
          placeholder="e.g. Team communication and project channels"
          className="w-full px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <label className="flex items-center gap-2 cursor-pointer self-end pb-1.5">
          <input
            type="checkbox"
            checked={enableJira}
            onChange={(e) => setEnableJira(e.target.checked)}
            className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
          />
          <span className="text-xs text-gray-700">Jira integration</span>
        </label>
        <div>
          <label htmlFor={`email-${detectionId}`} className="block text-xs font-medium text-gray-600 mb-1">
            Support Email
          </label>
          <input
            id={`email-${detectionId}`}
            type="email"
            value={supportEmail}
            onChange={(e) => setSupportEmail(e.target.value)}
            placeholder="support@vendor.com"
            className="w-full px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
      </div>

      {enableJira && existingOptions.length > 0 && (
        <WebhookSelector
          webhooks={allWebhooks}
          selectedSecret={reuseSecret}
          onSelect={setReuseSecret}
        />
      )}

      {enableJira && existingOptions.length === 0 && (
        <p className="text-xs text-blue-600">
          After registration, you'll get a webhook URL to add to your Jira project.
        </p>
      )}

      {mutation.isError && (
        <p className="text-sm text-red-600">
          {(mutation.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Registration failed'}
        </p>
      )}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={mutation.isPending}
          className="flex items-center gap-1.5 bg-blue-600 text-white px-3 py-1.5 rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-50 cursor-pointer"
        >
          <Check className="w-3.5 h-3.5" />
          {mutation.isPending ? 'Registering...' : 'Confirm & Register'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-1.5 bg-white border border-gray-300 text-gray-700 rounded-md text-sm hover:bg-gray-50 cursor-pointer"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
