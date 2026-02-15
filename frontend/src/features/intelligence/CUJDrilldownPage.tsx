import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { getCUJDrilldown, generateOutreach, type DrilldownCompany } from '../../api/intelligence';
import { ArrowLeft, ChevronDown, ChevronRight, CheckCircle, XCircle, Mail, Copy, Check, User } from 'lucide-react';

/** Track per-contact outreach keyed by "companyId::contactName" */
type OutreachMap = Record<
  string,
  { company_name: string; contact_name: string | null; generated_message: string; pain_points: string[] }
>;

export function CUJDrilldownPage() {
  const { vendor, software, stage } = useParams<{ vendor: string; software: string; stage: string }>();
  const navigate = useNavigate();
  const [expandedCompany, setExpandedCompany] = useState<string | null>(null);
  const [outreachResults, setOutreachResults] = useState<OutreachMap>({});
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [pendingContact, setPendingContact] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ['intelligence-drilldown', vendor, software, stage],
    queryFn: () => getCUJDrilldown(vendor!, software!, Number(stage!)),
    enabled: !!vendor && !!software && !!stage,
  });

  const outreach = useMutation({
    mutationFn: ({ companyId, contactName }: { companyId: string; contactName?: string }) =>
      generateOutreach(vendor!, software!, Number(stage!), companyId, contactName),
    onSuccess: (result, { companyId, contactName }) => {
      const key = `${companyId}::${contactName ?? '__company__'}`;
      setOutreachResults((prev) => ({ ...prev, [key]: result }));
      setPendingContact(null);
    },
    onError: () => {
      setPendingContact(null);
    },
  });

  const handleGenerate = (companyId: string, contactName?: string) => {
    const key = `${companyId}::${contactName ?? '__company__'}`;
    setPendingContact(key);
    outreach.mutate({ companyId, contactName });
  };

  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  if (isLoading) {
    return <div className="text-center py-12 text-gray-400 text-sm">Loading drilldown data...</div>;
  }

  if (error || !data) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500 mb-4">Stage data not found.</p>
        <button
          onClick={() => navigate(`/intelligence/${encodeURIComponent(vendor!)}/${encodeURIComponent(software!)}`)}
          className="text-blue-600 hover:underline text-sm cursor-pointer"
        >
          Back to Solution Detail
        </button>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <button
          onClick={() => navigate(`/intelligence/${encodeURIComponent(vendor!)}/${encodeURIComponent(software!)}`)}
          className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 mb-3 cursor-pointer"
        >
          <ArrowLeft className="w-4 h-4" /> Back to {software}
        </button>
        <h1 className="text-2xl font-bold text-gray-900">Stage {data.stage_order}: {data.stage_name}</h1>
        <p className="text-gray-500 text-sm mt-1">
          {data.companies.length} {data.companies.length === 1 ? 'company' : 'companies'} at this stage
        </p>
      </div>

      {/* Companies list */}
      <div className="bg-white rounded-lg border border-gray-200">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="text-left py-3 px-4 font-medium text-gray-600 w-8"></th>
              <th className="text-left py-3 px-4 font-medium text-gray-600">Company</th>
              <th className="text-left py-3 px-4 font-medium text-gray-600">Industry</th>
              <th className="text-left py-3 px-4 font-medium text-gray-600">Size</th>
              <th className="text-center py-3 px-4 font-medium text-gray-600">Status</th>
              <th className="text-left py-3 px-4 font-medium text-gray-600">Contacts</th>
            </tr>
          </thead>
          <tbody>
            {data.companies.map((company) => (
              <CompanyRow
                key={company.company_id}
                company={company}
                isExpanded={expandedCompany === company.company_id}
                onToggle={() => setExpandedCompany(expandedCompany === company.company_id ? null : company.company_id)}
                outreachResults={outreachResults}
                pendingContact={pendingContact}
                copiedKey={copiedKey}
                onGenerate={handleGenerate}
                onCopy={handleCopy}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function OutreachPanel({
  result,
  label,
  outreachKey,
  copiedKey,
  onCopy,
}: {
  result: OutreachMap[string];
  label: string;
  outreachKey: string;
  copiedKey: string | null;
  onCopy: (text: string, key: string) => void;
}) {
  return (
    <div className="mt-2 bg-blue-50 rounded-lg p-3">
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-semibold text-blue-800">Message for {label}</p>
        <button
          onClick={() => onCopy(result.generated_message, outreachKey)}
          className="text-xs text-blue-600 hover:text-blue-800 inline-flex items-center gap-1 cursor-pointer"
        >
          {copiedKey === outreachKey ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
          {copiedKey === outreachKey ? 'Copied' : 'Copy'}
        </button>
      </div>
      {result.pain_points.length > 0 && (
        <div className="mb-2">
          <p className="text-xs text-blue-700 font-medium mb-1">Pain Points:</p>
          <ul className="text-xs text-blue-800 list-disc list-inside">
            {result.pain_points.map((point, i) => (
              <li key={i}>{point}</li>
            ))}
          </ul>
        </div>
      )}
      <pre className="text-xs text-gray-800 whitespace-pre-wrap font-sans bg-white rounded p-3 border border-blue-100">
        {result.generated_message}
      </pre>
    </div>
  );
}

function CompanyRow({
  company,
  isExpanded,
  onToggle,
  outreachResults,
  pendingContact,
  copiedKey,
  onGenerate,
  onCopy,
}: {
  company: DrilldownCompany;
  isExpanded: boolean;
  onToggle: () => void;
  outreachResults: OutreachMap;
  pendingContact: string | null;
  copiedKey: string | null;
  onGenerate: (companyId: string, contactName?: string) => void;
  onCopy: (text: string, key: string) => void;
}) {
  return (
    <tr className="border-b border-gray-50">
      <td className="py-3 px-4" colSpan={6}>
        {/* Main row */}
        <div className="flex items-center">
          <button
            onClick={onToggle}
            className="mr-3 text-gray-400 hover:text-gray-600 cursor-pointer"
          >
            {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          </button>
          <div className="flex-1 grid grid-cols-5 gap-4 items-center">
            <div className="font-medium text-gray-900">{company.company_name}</div>
            <div>
              {company.industry ? (
                <span className="text-xs bg-purple-50 text-purple-700 px-2 py-0.5 rounded-full">
                  {company.industry}
                </span>
              ) : (
                <span className="text-gray-400">--</span>
              )}
            </div>
            <div>
              {company.company_size ? (
                <span className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded-full capitalize">
                  {company.company_size}
                </span>
              ) : (
                <span className="text-gray-400">--</span>
              )}
            </div>
            <div className="text-center">
              {company.satisfied ? (
                <CheckCircle className="w-5 h-5 text-green-500 inline" />
              ) : (
                <XCircle className="w-5 h-5 text-red-500 inline" />
              )}
            </div>
            <div className="text-xs text-gray-500">
              {company.contacts.length > 0
                ? `${company.contacts.length} ${company.contacts.length === 1 ? 'contact' : 'contacts'}`
                : '--'}
            </div>
          </div>
        </div>

        {/* Expanded: reporter selection + outreach */}
        {isExpanded && (
          <div className="mt-3 ml-7">
            {company.contacts.length > 0 ? (
              <div className="bg-gray-50 rounded-lg p-4 space-y-3">
                <p className="text-xs font-medium text-gray-500">Select a contact to generate outreach</p>
                {company.contacts.map((contact) => {
                  const key = `${company.company_id}::${contact}`;
                  const result = outreachResults[key];
                  const isPending = pendingContact === key;

                  return (
                    <div key={contact}>
                      <div className="flex items-center gap-2">
                        <User className="w-3.5 h-3.5 text-gray-400" />
                        <span className="text-sm text-gray-800">{contact}</span>
                        {!result && (
                          <button
                            onClick={() => onGenerate(company.company_id, contact)}
                            disabled={isPending}
                            className="ml-auto text-xs bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700 disabled:opacity-50 inline-flex items-center gap-1 cursor-pointer"
                          >
                            <Mail className="w-3 h-3" />
                            {isPending ? 'Generating...' : 'Generate Outreach'}
                          </button>
                        )}
                      </div>
                      {result && (
                        <OutreachPanel
                          result={result}
                          label={result.contact_name ?? contact}
                          outreachKey={key}
                          copiedKey={copiedKey}
                          onCopy={onCopy}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            ) : !company.satisfied ? (
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-xs font-medium text-gray-500 mb-3">No named contacts found for this company.</p>
                {(() => {
                  const key = `${company.company_id}::__company__`;
                  const result = outreachResults[key];
                  const isPending = pendingContact === key;
                  return (
                    <>
                      {!result && (
                        <button
                          onClick={() => onGenerate(company.company_id)}
                          disabled={isPending}
                          className="text-xs bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700 disabled:opacity-50 inline-flex items-center gap-1 cursor-pointer"
                        >
                          <Mail className="w-3 h-3" />
                          {isPending ? 'Generating...' : 'Generate Company Outreach'}
                        </button>
                      )}
                      {result && (
                        <OutreachPanel
                          result={result}
                          label={result.company_name}
                          outreachKey={key}
                          copiedKey={copiedKey}
                          onCopy={onCopy}
                        />
                      )}
                    </>
                  );
                })()}
              </div>
            ) : (
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-xs text-gray-400">No contacts or outreach actions for this company.</p>
              </div>
            )}
          </div>
        )}
      </td>
    </tr>
  );
}
