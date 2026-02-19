import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getSoftwareList, updateSoftware, deleteSoftware } from '../../api/software';
import { setupJiraWebhook, getJiraWebhooks, disconnectJira } from '../../api/integrations';
import type { Software, UpdateSoftwarePayload } from '../../api/software';
import type { JiraWebhookSetup, JiraWebhookInfo } from '../../api/integrations';
import { Trash2, Package, Pencil, Copy, Check, Webhook, Unplug, RefreshCw } from 'lucide-react';

/** Group webhooks by secret to get unique URLs with their linked software. */
function getUniqueWebhookUrls(webhooks: JiraWebhookInfo[], excludeSoftwareId?: string) {
  const bySecret = new Map<string, { url: string; secret: string; software: { name: string; vendor: string }[] }>();
  for (const wh of webhooks) {
    if (excludeSoftwareId && wh.software_id === excludeSoftwareId) continue;
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
  excludeSoftwareId,
  selectedSecret,
  onSelect,
}: {
  webhooks: JiraWebhookInfo[];
  excludeSoftwareId?: string;
  selectedSecret: string | null; // null = create new
  onSelect: (secret: string | null) => void;
}) {
  const options = getUniqueWebhookUrls(webhooks, excludeSoftwareId);
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

function EditForm({
  sw,
  webhookInfo: _webhookInfo,
  allWebhooks,
  onCancel,
  onSaved,
}: {
  sw: Software;
  webhookInfo?: JiraWebhookInfo;
  allWebhooks: JiraWebhookInfo[];
  onCancel: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    vendor_name: sw.vendor_name,
    software_name: sw.software_name,
    intended_use: sw.intended_use || '',
    support_email: sw.support_email || '',
  });
  const [enableJira, setEnableJira] = useState(!!sw.jira_workspace);
  const [reuseSecret, setReuseSecret] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [jiraSetup, setJiraSetup] = useState<JiraWebhookSetup | null>(null);
  const [copied, setCopied] = useState(false);

  const hadJira = !!sw.jira_workspace;

  const mutation = useMutation({
    mutationFn: (data: UpdateSoftwarePayload) => updateSoftware(sw.id, data),
    onSuccess: async () => {
      if (enableJira && !hadJira) {
        try {
          const setup = await setupJiraWebhook(sw.id, reuseSecret ?? undefined);
          setJiraSetup(setup);
          return;
        } catch {
          // Webhook setup failed but update succeeded
        }
      }
      onSaved();
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to update software');
    },
  });

  const update = (field: string, value: string) => setForm((f) => ({ ...f, [field]: value }));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    mutation.mutate({
      vendor_name: form.vendor_name,
      software_name: form.software_name,
      intended_use: form.intended_use || null,
      jira_workspace: enableJira ? (sw.jira_workspace || 'enabled') : null,
      support_email: form.support_email || null,
    });
  };

  const copyUrl = () => {
    if (jiraSetup) {
      navigator.clipboard.writeText(jiraSetup.webhook_url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // Show Jira webhook result after successful update
  if (jiraSetup) {
    return (
      <div className="space-y-4">
        <div>
          <h3 className="text-sm font-semibold text-gray-900 mb-1">
            {jiraSetup.is_new_url ? 'Jira Webhook Setup' : 'Jira Webhook Linked'}
          </h3>
          <p className="text-xs text-gray-500">
            <span className="font-medium text-gray-700">{form.software_name}</span> updated.
            {jiraSetup.is_new_url
              ? ' Add this webhook URL to your Jira project to start receiving signals.'
              : ' This software now shares an existing Jira webhook URL.'}
          </p>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">Webhook URL</label>
          <div className="flex items-center gap-2">
            <input
              readOnly
              value={jiraSetup.webhook_url}
              className="flex-1 bg-gray-50 border border-gray-300 rounded-md px-3 py-1.5 text-sm text-gray-800 font-mono select-all"
              onClick={(e) => (e.target as HTMLInputElement).select()}
            />
            <button
              onClick={copyUrl}
              className="flex items-center gap-1 px-3 py-1.5 text-sm font-medium rounded-md border border-gray-300 hover:bg-gray-50 cursor-pointer"
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
          <div className="bg-blue-50 border border-blue-200 rounded-md p-3">
            <h4 className="text-xs font-semibold text-blue-900 mb-1.5">How to add this webhook in Jira</h4>
            <ol className="text-xs text-blue-800 space-y-1.5 list-decimal list-inside">
              <li>
                Go to <span className="font-medium">Settings &rarr; System &rarr; WebHooks</span>
              </li>
              <li>Click <span className="font-medium">Create a WebHook</span></li>
              <li>Paste the webhook URL above into the <span className="font-medium">URL</span> field</li>
              <li>
                Under <span className="font-medium">Events</span>, select:
                <ul className="mt-0.5 ml-4 space-y-0.5 list-disc">
                  <li>Issue: <span className="font-medium">created, updated, deleted</span></li>
                  <li>Comment: <span className="font-medium">created, updated</span></li>
                </ul>
              </li>
              <li>Click <span className="font-medium">Create</span> to save</li>
            </ol>
          </div>
        )}

        <div className="flex gap-2">
          <button
            onClick={onSaved}
            className="bg-blue-600 text-white px-3 py-1.5 rounded-md text-sm font-medium hover:bg-blue-700 cursor-pointer"
          >
            Done
          </button>
        </div>
      </div>
    );
  }

  const existingOptions = getUniqueWebhookUrls(allWebhooks, sw.id);

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      {error && (
        <div className="p-2 bg-red-50 text-red-700 text-sm rounded-md">{error}</div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">Vendor name *</label>
          <input
            value={form.vendor_name}
            onChange={(e) => update('vendor_name', e.target.value)}
            required
            className="w-full border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">Software name *</label>
          <input
            value={form.software_name}
            onChange={(e) => update('software_name', e.target.value)}
            required
            className="w-full border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1">Intended use</label>
        <textarea
          value={form.intended_use}
          onChange={(e) => update('intended_use', e.target.value)}
          rows={2}
          className="w-full border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      <div className="grid grid-cols-3 gap-3">
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
          <label className="block text-xs font-medium text-gray-500 mb-1">Support email</label>
          <input
            type="email"
            value={form.support_email}
            onChange={(e) => update('support_email', e.target.value)}
            placeholder="e.g. support@vendor.com"
            className="w-full border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      {enableJira && !hadJira && existingOptions.length > 0 && (
        <WebhookSelector
          webhooks={allWebhooks}
          excludeSoftwareId={sw.id}
          selectedSecret={reuseSecret}
          onSelect={setReuseSecret}
        />
      )}

      {enableJira && !hadJira && existingOptions.length === 0 && (
        <p className="text-xs text-blue-600">
          After saving, you'll get a webhook URL to add to your Jira project.
        </p>
      )}

      <div className="flex gap-2 pt-1">
        <button
          type="submit"
          disabled={mutation.isPending}
          className="bg-blue-600 text-white px-3 py-1.5 rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-50 cursor-pointer"
        >
          {mutation.isPending ? 'Saving...' : 'Save'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={mutation.isPending}
          className="text-gray-600 px-3 py-1.5 rounded-md text-sm hover:bg-gray-100 cursor-pointer"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

function JiraWebhookCard({
  info,
  sharedWith,
  allWebhooks,
  onDisconnected,
  onReconfigured,
}: {
  info: JiraWebhookInfo;
  sharedWith: string[];
  allWebhooks: JiraWebhookInfo[];
  onDisconnected: () => void;
  onReconfigured: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [reconfiguring, setReconfiguring] = useState(false);
  const [reuseSecret, setReuseSecret] = useState<string | null>(null);
  const [reconfigResult, setReconfigResult] = useState<JiraWebhookSetup | null>(null);
  const [resultCopied, setResultCopied] = useState(false);

  const disconnectMutation = useMutation({
    mutationFn: () => disconnectJira(info.software_id),
    onSuccess: onDisconnected,
  });

  const reconfigMutation = useMutation({
    mutationFn: () => setupJiraWebhook(info.software_id, reuseSecret ?? undefined),
    onSuccess: (setup) => {
      setReconfiguring(false);
      setReconfigResult(setup);
    },
  });

  const copyUrl = () => {
    navigator.clipboard.writeText(info.webhook_url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const copyResultUrl = () => {
    if (reconfigResult) {
      navigator.clipboard.writeText(reconfigResult.webhook_url);
      setResultCopied(true);
      setTimeout(() => setResultCopied(false), 2000);
    }
  };

  // Show result after reconfigure
  if (reconfigResult) {
    return (
      <div className="mt-3 bg-blue-50 rounded-md p-3 space-y-2 border border-blue-200">
        <div className="flex items-center gap-2">
          <Webhook className="w-3.5 h-3.5 text-blue-600" />
          <span className="text-xs font-medium text-blue-700">
            {reconfigResult.is_new_url ? 'New Webhook URL' : 'Webhook URL Updated'}
          </span>
        </div>
        <p className="text-xs text-gray-600">
          {reconfigResult.is_new_url
            ? 'Add this new webhook URL to your Jira project.'
            : 'This software now shares an existing Jira webhook URL.'}
        </p>
        <div className="flex items-center gap-2">
          <code className="flex-1 text-xs text-gray-700 bg-white border border-gray-200 rounded px-2 py-1 overflow-x-auto">
            {reconfigResult.webhook_url}
          </code>
          <button
            onClick={copyResultUrl}
            className="flex-shrink-0 p-1 text-gray-400 hover:text-gray-600 cursor-pointer"
            title="Copy URL"
          >
            {resultCopied ? (
              <Check className="w-3.5 h-3.5 text-green-600" />
            ) : (
              <Copy className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
        {reconfigResult.is_new_url && (
          <div className="bg-white border border-blue-200 rounded-md p-2">
            <h4 className="text-xs font-semibold text-blue-900 mb-1">How to add this webhook in Jira</h4>
            <ol className="text-xs text-blue-800 space-y-0.5 list-decimal list-inside">
              <li>Go to <span className="font-medium">Settings &rarr; System &rarr; WebHooks</span></li>
              <li>Click <span className="font-medium">Create a WebHook</span></li>
              <li>Paste the webhook URL above</li>
              <li>Select events: Issue created, updated, deleted; Comment created, updated</li>
              <li>Click <span className="font-medium">Create</span></li>
            </ol>
          </div>
        )}
        <button
          onClick={() => {
            setReconfigResult(null);
            onReconfigured();
          }}
          className="text-xs bg-blue-600 text-white px-2.5 py-1 rounded-md hover:bg-blue-700 cursor-pointer"
        >
          Done
        </button>
      </div>
    );
  }

  return (
    <div className="mt-3 bg-gray-50 rounded-md p-3 space-y-2 border border-gray-200">
      <div className="flex items-center gap-2">
        <Webhook className="w-3.5 h-3.5 text-blue-600" />
        <span className="text-xs font-medium text-blue-700">Jira Webhook</span>
      </div>
      <div>
        <div className="text-xs text-gray-500 mb-1">Webhook URL</div>
        <div className="flex items-center gap-2">
          <code className="flex-1 text-xs text-gray-700 bg-white border border-gray-200 rounded px-2 py-1 overflow-x-auto">
            {info.webhook_url}
          </code>
          <button
            onClick={copyUrl}
            className="flex-shrink-0 p-1 text-gray-400 hover:text-gray-600 cursor-pointer"
            title="Copy URL"
          >
            {copied ? (
              <Check className="w-3.5 h-3.5 text-green-600" />
            ) : (
              <Copy className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </div>
      <div className="flex items-center gap-4 text-xs text-gray-500">
        <span>Events: <span className="text-gray-700 font-medium">{info.events_received}</span></span>
        {info.last_event_at && (
          <span>Last: <span className="text-gray-700">{new Date(info.last_event_at).toLocaleString()}</span></span>
        )}
        {info.connected_at && (
          <span>Created: <span className="text-gray-700">{new Date(info.connected_at).toLocaleDateString()}</span></span>
        )}
      </div>
      {sharedWith.length > 0 && (
        <div className="text-xs text-gray-400">
          Shared with: {sharedWith.join(', ')}
        </div>
      )}

      {reconfiguring ? (
        <div className="space-y-2 pt-1 border-t border-gray-200">
          <WebhookSelector
            webhooks={allWebhooks}
            excludeSoftwareId={info.software_id}
            selectedSecret={reuseSecret}
            onSelect={setReuseSecret}
          />
          {reconfigMutation.isError && (
            <p className="text-xs text-red-600">Failed to reconfigure webhook.</p>
          )}
          <div className="flex gap-2">
            <button
              onClick={() => reconfigMutation.mutate()}
              disabled={reconfigMutation.isPending}
              className="text-xs bg-blue-600 text-white px-2.5 py-1 rounded-md hover:bg-blue-700 disabled:opacity-50 cursor-pointer"
            >
              {reconfigMutation.isPending ? 'Saving...' : 'Confirm'}
            </button>
            <button
              onClick={() => { setReconfiguring(false); setReuseSecret(null); }}
              className="text-xs text-gray-600 px-2.5 py-1 rounded-md hover:bg-gray-100 cursor-pointer"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-3">
          <button
            onClick={() => setReconfiguring(true)}
            className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 cursor-pointer"
          >
            <RefreshCw className="w-3 h-3" />
            Change URL
          </button>
          <button
            onClick={() => disconnectMutation.mutate()}
            disabled={disconnectMutation.isPending}
            className="flex items-center gap-1 text-xs text-red-600 hover:text-red-700 cursor-pointer"
          >
            <Unplug className="w-3 h-3" />
            {disconnectMutation.isPending ? 'Removing...' : 'Remove Webhook'}
          </button>
        </div>
      )}
    </div>
  );
}

export function SoftwareListPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['software', search],
    queryFn: () => getSoftwareList({ search: search || undefined }),
  });

  const { data: jiraData } = useQuery({
    queryKey: ['jira-webhooks'],
    queryFn: getJiraWebhooks,
  });

  const allWebhooks = jiraData?.webhooks || [];

  // Build a lookup: software_id -> JiraWebhookInfo
  const webhookMap = new Map<string, JiraWebhookInfo>();
  for (const wh of allWebhooks) {
    webhookMap.set(wh.software_id, wh);
  }

  // For shared-URL display: for each webhook, find other software sharing the same secret
  const getSharedWith = (wh: JiraWebhookInfo): string[] => {
    return allWebhooks
      .filter((other) => other.webhook_secret === wh.webhook_secret && other.software_id !== wh.software_id)
      .map((other) => `${other.software_name || 'Unknown'} by ${other.vendor_name || '?'}`);
  };

  const deleteMutation = useMutation({
    mutationFn: deleteSoftware,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['software'] }),
  });

  const handleSaved = () => {
    setEditingId(null);
    queryClient.invalidateQueries({ queryKey: ['software'] });
    queryClient.invalidateQueries({ queryKey: ['jira-webhooks'] });
  };

  const handleWebhookDisconnected = () => {
    queryClient.invalidateQueries({ queryKey: ['jira-webhooks'] });
    queryClient.invalidateQueries({ queryKey: ['software'] });
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Software Integrations</h1>
          <p className="text-gray-600 text-sm mt-1">Manage your registered vendor software</p>
        </div>
      </div>

      <div className="mb-4">
        <input
          type="text"
          placeholder="Search by vendor or software name..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full max-w-md border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {isLoading ? (
        <div className="text-center py-12 text-gray-500">Loading...</div>
      ) : !data?.items.length ? (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
          <Package className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500">No software registered yet.</p>
        </div>
      ) : (
        <div className="grid gap-4">
          {data.items.map((sw: Software) => (
            <div key={sw.id} className="bg-white rounded-lg border border-gray-200 p-4">
              {editingId === sw.id ? (
                <EditForm
                  sw={sw}
                  webhookInfo={webhookMap.get(sw.id)}
                  allWebhooks={allWebhooks}
                  onCancel={() => setEditingId(null)}
                  onSaved={handleSaved}
                />
              ) : (
                <div>
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-medium text-gray-900">{sw.software_name}</h3>
                        <span className={`text-xs px-2 py-0.5 rounded ${
                          sw.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'
                        }`}>
                          {sw.status}
                        </span>
                      </div>
                      <p className="text-sm text-gray-500 mt-0.5">by {sw.vendor_name}</p>
                      {sw.intended_use && (
                        <p className="text-sm text-gray-600 mt-1">{sw.intended_use}</p>
                      )}
                      <div className="flex gap-4 mt-2 text-xs text-gray-400">
                        {sw.support_email && <span>Support: {sw.support_email}</span>}
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => setEditingId(sw.id)}
                        className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded cursor-pointer"
                        title="Edit"
                      >
                        <Pencil className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => {
                          if (confirm('Archive this software?')) deleteMutation.mutate(sw.id);
                        }}
                        className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded cursor-pointer"
                        title="Archive"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                  {webhookMap.has(sw.id) && (
                    <JiraWebhookCard
                      info={webhookMap.get(sw.id)!}
                      sharedWith={getSharedWith(webhookMap.get(sw.id)!)}
                      allWebhooks={allWebhooks}
                      onDisconnected={handleWebhookDisconnected}
                      onReconfigured={handleWebhookDisconnected}
                    />
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
