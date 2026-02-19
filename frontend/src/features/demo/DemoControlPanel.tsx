import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  composeEmail,
  composeSignal,
  getDemoCompanies,
  type ComposeEmailPayload,
} from '../../api/demo';
import {
  FlaskConical,
  Send,
  ArrowDownLeft,
  ArrowUpRight,
  CheckCircle2,
  AlertCircle,
  Mail,
  TicketCheck,
  Building2,
} from 'lucide-react';

type Tab = 'email' | 'jira';

const emailCategories = [
  { value: 'integration', label: 'Integration' },
  { value: 'feature_request', label: 'Feature Request' },
  { value: 'issue_debug', label: 'Issue / Debug' },
] as const;

const jiraEventTypes = [
  { value: 'ticket_created', label: 'Ticket Created' },
  { value: 'ticket_resolved', label: 'Ticket Resolved' },
  { value: 'ticket_updated', label: 'Ticket Updated' },
  { value: 'comment_added', label: 'Comment Added' },
] as const;

const severities = [
  { value: 'low', label: 'Low', color: 'bg-gray-100 text-gray-700 border-gray-300' },
  { value: 'medium', label: 'Medium', color: 'bg-yellow-50 text-yellow-700 border-yellow-300' },
  { value: 'high', label: 'High', color: 'bg-orange-50 text-orange-700 border-orange-300' },
  { value: 'critical', label: 'Critical', color: 'bg-red-50 text-red-700 border-red-300' },
] as const;

function ResultBanner({
  isSuccess,
  isError,
  successContent,
  error,
}: {
  isSuccess: boolean;
  isError: boolean;
  successContent: React.ReactNode;
  error: unknown;
}) {
  return (
    <>
      {isSuccess && (
        <div className="flex items-start gap-2 p-3 bg-green-50 border border-green-200 rounded-md">
          <CheckCircle2 className="w-5 h-5 text-green-600 mt-0.5 shrink-0" />
          <div className="text-sm text-green-800">{successContent}</div>
        </div>
      )}
      {isError && (
        <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-md">
          <AlertCircle className="w-5 h-5 text-red-600 mt-0.5 shrink-0" />
          <div className="text-sm text-red-800">
            <p className="font-medium">Failed</p>
            <p className="text-red-700">{String(error)}</p>
          </div>
        </div>
      )}
    </>
  );
}

function EmailForm({ companyId }: { companyId: string }) {
  const [direction, setDirection] = useState<'inbound' | 'outbound'>('inbound');
  const [senderName, setSenderName] = useState('');
  const [sender, setSender] = useState('');
  const [recipient, setRecipient] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [category, setCategory] = useState<ComposeEmailPayload['category']>('integration');
  const [autoDetect, setAutoDetect] = useState(true);
  const [severity, setSeverity] = useState<'low' | 'medium' | 'high' | 'critical'>('medium');
  const [occurredAt, setOccurredAt] = useState('');

  const isSignalCategory = category === 'feature_request' || category === 'issue_debug';

  const mutation = useMutation({
    mutationFn: composeEmail,
    onSuccess: () => {
      setSenderName('');
      setSender('');
      setRecipient('');
      setSubject('');
      setBody('');
      setOccurredAt('');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    mutation.mutate({
      company_id: companyId,
      sender,
      sender_name: senderName || undefined,
      recipient: recipient || undefined,
      subject,
      body,
      category,
      direction,
      auto_detect: autoDetect,
      severity: isSignalCategory ? severity : undefined,
      occurred_at: occurredAt ? new Date(occurredAt).toISOString() : undefined,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {/* Direction toggle */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">Direction</label>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setDirection('inbound')}
            className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium border cursor-pointer ${
              direction === 'inbound'
                ? 'bg-blue-50 border-blue-300 text-blue-700'
                : 'bg-white border-gray-300 text-gray-600 hover:bg-gray-50'
            }`}
          >
            <ArrowDownLeft className="w-4 h-4" />
            From Vendor (inbound)
          </button>
          <button
            type="button"
            onClick={() => setDirection('outbound')}
            className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium border cursor-pointer ${
              direction === 'outbound'
                ? 'bg-green-50 border-green-300 text-green-700'
                : 'bg-white border-gray-300 text-gray-600 hover:bg-gray-50'
            }`}
          >
            <ArrowUpRight className="w-4 h-4" />
            From Company (outbound)
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label htmlFor="email-sender-name" className="block text-sm font-medium text-gray-700 mb-1">
            Sender Name <span className="text-gray-400 font-normal">(optional)</span>
          </label>
          <input
            id="email-sender-name"
            type="text"
            value={senderName}
            onChange={(e) => setSenderName(e.target.value)}
            placeholder={direction === 'inbound' ? 'Slack Support' : 'Jane Smith'}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
        <div>
          <label htmlFor="email-sender" className="block text-sm font-medium text-gray-700 mb-1">
            Sender Email
          </label>
          <input
            id="email-sender"
            type="text"
            value={sender}
            onChange={(e) => setSender(e.target.value)}
            placeholder={direction === 'inbound' ? 'noreply@slack.com' : 'devops@acme-corp.com'}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            required
          />
        </div>
      </div>

      <div>
        <label htmlFor="email-recipient" className="block text-sm font-medium text-gray-700 mb-1">
          Recipient Email <span className="text-gray-400 font-normal">(optional — helps match vendor software)</span>
        </label>
        <input
          id="email-recipient"
          type="text"
          value={recipient}
          onChange={(e) => setRecipient(e.target.value)}
          placeholder={direction === 'inbound' ? 'devops@acme-corp.com' : 'support@hubspot.com'}
          className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
      </div>

      <div>
        <label htmlFor="email-date" className="block text-sm font-medium text-gray-700 mb-1">
          Date <span className="text-gray-400 font-normal">(optional — defaults to now)</span>
        </label>
        <input
          id="email-date"
          type="datetime-local"
          value={occurredAt}
          onChange={(e) => setOccurredAt(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
      </div>

      <div>
        <label htmlFor="email-subject" className="block text-sm font-medium text-gray-700 mb-1">
          Subject
        </label>
        <input
          id="email-subject"
          type="text"
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          placeholder="Welcome to Slack! Your workspace is ready"
          className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          required
        />
      </div>

      <div>
        <label htmlFor="email-body" className="block text-sm font-medium text-gray-700 mb-1">
          Email Body
        </label>
        <textarea
          id="email-body"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={6}
          placeholder="Write the full email body here..."
          className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-y"
          required
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">Category</label>
        <div className="flex gap-2">
          {emailCategories.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              onClick={() => setCategory(value)}
              className={`px-3 py-1.5 rounded-md text-sm font-medium border cursor-pointer ${
                category === value
                  ? 'bg-gray-900 border-gray-900 text-white'
                  : 'bg-white border-gray-300 text-gray-600 hover:bg-gray-50'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="text-xs text-gray-400 mt-1">
          {isSignalCategory
            ? 'Creates a signal event (software inferred from message content) and runs health analysis.'
            : 'Runs the Software Integration Detector to identify new software adoption.'}
        </p>
      </div>

      {/* Severity — shown for feature_request / issue_debug */}
      {isSignalCategory && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">Severity</label>
          <div className="flex gap-2">
            {severities.map(({ value, label, color }) => (
              <button
                key={value}
                type="button"
                onClick={() => setSeverity(value)}
                className={`px-3 py-1.5 rounded-md text-sm font-medium border cursor-pointer ${
                  severity === value ? color : 'bg-white border-gray-300 text-gray-600 hover:bg-gray-50'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Auto-detect checkbox — only relevant for integration emails */}
      {category === 'integration' && (
        <div className="flex items-center gap-2">
          <input
            id="autoDetect"
            type="checkbox"
            checked={autoDetect}
            onChange={(e) => setAutoDetect(e.target.checked)}
            className="h-4 w-4 text-blue-600 border-gray-300 rounded"
          />
          <label htmlFor="autoDetect" className="text-sm text-gray-700">
            Run detection after sending
          </label>
        </div>
      )}

      <button
        type="submit"
        disabled={mutation.isPending}
        className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-50 cursor-pointer"
      >
        <Send className="w-4 h-4" />
        {mutation.isPending ? 'Sending...' : 'Send Email'}
      </button>

      <ResultBanner
        isSuccess={mutation.isSuccess}
        isError={mutation.isError}
        error={mutation.error}
        successContent={
          <>
            <p className="font-medium">Email created</p>
            <p className="text-green-700">
              ID: {mutation.data?.email_id}
              {mutation.data?.detection_queued && ' — detection queued'}
              {mutation.data?.signal_created && ' — signal created'}
              {mutation.data?.analysis_queued && ' — analysis running'}
            </p>
          </>
        }
      />
    </form>
  );
}

function SignalForm({ companyId, sourceType }: { companyId: string; sourceType: 'jira' }) {
  const eventTypes = jiraEventTypes;
  const [eventType, setEventType] = useState<string>(eventTypes[0].value);
  const [severity, setSeverity] = useState<'low' | 'medium' | 'high' | 'critical'>('medium');
  const [reporter, setReporter] = useState('');
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [sourceId, setSourceId] = useState('');
  const [occurredAt, setOccurredAt] = useState('');

  const mutation = useMutation({
    mutationFn: composeSignal,
    onSuccess: () => {
      setReporter('');
      setTitle('');
      setBody('');
      setSourceId('');
      setOccurredAt('');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    mutation.mutate({
      company_id: companyId,
      source_type: sourceType,
      event_type: eventType,
      severity,
      title,
      body,
      source_id: sourceId || undefined,
      reporter: reporter || undefined,
      occurred_at: occurredAt ? new Date(occurredAt).toISOString() : undefined,
    });
  };

  const placeholders = {
    title: 'Slack API returns 500 on /channels endpoint',
    body: 'Intermittent 500 errors when calling the Slack API. Started after their latest update.',
    sourceId: 'JIRA-1234',
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">Event Type</label>
        <div className="flex flex-wrap gap-2">
          {eventTypes.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              onClick={() => setEventType(value)}
              className={`px-3 py-1.5 rounded-md text-sm font-medium border cursor-pointer ${
                eventType === value
                  ? 'bg-gray-900 border-gray-900 text-white'
                  : 'bg-white border-gray-300 text-gray-600 hover:bg-gray-50'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">Severity</label>
        <div className="flex gap-2">
          {severities.map(({ value, label, color }) => (
            <button
              key={value}
              type="button"
              onClick={() => setSeverity(value)}
              className={`px-3 py-1.5 rounded-md text-sm font-medium border cursor-pointer ${
                severity === value ? color : 'bg-white border-gray-300 text-gray-600 hover:bg-gray-50'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label htmlFor={`${sourceType}-reporter`} className="block text-sm font-medium text-gray-700 mb-1">
            Reporter <span className="text-gray-400 font-normal">(optional)</span>
          </label>
          <input
            id={`${sourceType}-reporter`}
            type="text"
            value={reporter}
            onChange={(e) => setReporter(e.target.value)}
            placeholder={sourceType === 'jira' ? 'Jane Smith' : 'On-Call Engineer'}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
        <div>
          <label htmlFor={`${sourceType}-date`} className="block text-sm font-medium text-gray-700 mb-1">
            Date <span className="text-gray-400 font-normal">(optional — defaults to now)</span>
          </label>
          <input
            id={`${sourceType}-date`}
            type="datetime-local"
            value={occurredAt}
            onChange={(e) => setOccurredAt(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
      </div>

      <div>
        <label htmlFor={`${sourceType}-title`} className="block text-sm font-medium text-gray-700 mb-1">
          Title
        </label>
        <input
          id={`${sourceType}-title`}
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={placeholders.title}
          className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          required
        />
      </div>

      <div>
        <label htmlFor={`${sourceType}-body`} className="block text-sm font-medium text-gray-700 mb-1">
          Description
        </label>
        <textarea
          id={`${sourceType}-body`}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={4}
          placeholder={placeholders.body}
          className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-y"
          required
        />
      </div>

      <div>
        <label htmlFor={`${sourceType}-source-id`} className="block text-sm font-medium text-gray-700 mb-1">
          Source ID{' '}
          <span className="text-gray-400 font-normal">(optional — auto-generated if empty)</span>
        </label>
        <input
          id={`${sourceType}-source-id`}
          type="text"
          value={sourceId}
          onChange={(e) => setSourceId(e.target.value)}
          placeholder={placeholders.sourceId}
          className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
      </div>

      <p className="text-xs text-gray-400">
        Software is automatically inferred from the title and description. Mention a registered vendor or software name.
      </p>

      <button
        type="submit"
        disabled={mutation.isPending}
        className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-50 cursor-pointer"
      >
        <Send className="w-4 h-4" />
        {mutation.isPending ? 'Creating...' : 'Create Jira Ticket'}
      </button>

      <ResultBanner
        isSuccess={mutation.isSuccess}
        isError={mutation.isError}
        error={mutation.error}
        successContent={
          <>
            <p className="font-medium">Signal created</p>
            <p className="text-green-700">
              {mutation.data?.source_type.toUpperCase()}: {mutation.data?.title} — analysis running
            </p>
          </>
        }
      />
    </form>
  );
}

const tabs: { id: Tab; label: string; icon: typeof Mail }[] = [
  { id: 'email', label: 'Email', icon: Mail },
  { id: 'jira', label: 'Jira Ticket', icon: TicketCheck },
];

export function DemoControlPanel() {
  const [activeTab, setActiveTab] = useState<Tab>('email');
  const [selectedCompanyId, setSelectedCompanyId] = useState('');

  const { data: companies, isLoading: companiesLoading } = useQuery({
    queryKey: ['demo-companies'],
    queryFn: getDemoCompanies,
  });

  const selectedCompany = companies?.find((c) => c.id === selectedCompanyId);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Minimal header */}
      <nav className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FlaskConical className="w-6 h-6 text-purple-600" />
          <span className="font-semibold text-lg text-gray-900">Demo Control Panel</span>
          <span className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full font-medium">
            Internal
          </span>
        </div>
      </nav>

      <main className="max-w-3xl mx-auto px-6 py-8 space-y-6">
        {/* Company selector */}
        <div className="bg-white rounded-lg border border-gray-200 p-5">
          <div className="flex items-center gap-2 mb-3">
            <Building2 className="w-5 h-5 text-gray-500" />
            <label htmlFor="demo-company" className="text-sm font-medium text-gray-700">
              Acting as Company
            </label>
          </div>
          {companiesLoading ? (
            <p className="text-sm text-gray-400">Loading companies...</p>
          ) : !companies?.length ? (
            <p className="text-sm text-gray-500">No companies found. Register a company first.</p>
          ) : (
            <select
              id="demo-company"
              value={selectedCompanyId}
              onChange={(e) => setSelectedCompanyId(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
            >
              <option value="">Select a company...</option>
              {companies.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.company_name}
                  {c.industry ? ` (${c.industry})` : ''}
                  {c.company_size ? ` — ${c.company_size}` : ''}
                </option>
              ))}
            </select>
          )}
          {selectedCompany && (
            <p className="text-xs text-gray-400 mt-2">
              All actions below will be performed on behalf of <strong>{selectedCompany.company_name}</strong>.
            </p>
          )}
        </div>

        {/* Forms — only shown after company is selected */}
        {selectedCompanyId ? (
          <div className="bg-white rounded-lg border border-gray-200">
            {/* Tab bar */}
            <div className="flex border-b border-gray-200">
              {tabs.map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setActiveTab(id)}
                  className={`flex items-center gap-2 px-5 py-3 text-sm font-medium border-b-2 -mb-px cursor-pointer ${
                    activeTab === id
                      ? 'border-blue-600 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {label}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div className="p-6">
              {activeTab === 'email' && <EmailForm companyId={selectedCompanyId} />}
              {activeTab === 'jira' && <SignalForm companyId={selectedCompanyId} sourceType="jira" />}
            </div>
          </div>
        ) : (
          <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
            <Building2 className="w-12 h-12 text-gray-300 mx-auto mb-4" />
            <p className="text-gray-500">Select a company above to start composing demo events.</p>
          </div>
        )}
      </main>
    </div>
  );
}
