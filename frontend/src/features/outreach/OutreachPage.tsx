import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getCampaigns, createCampaign, sendCampaign, getCampaignMessages } from '../../api/outreach';
import type { Campaign, OutreachMessage } from '../../api/outreach';
import { Mail, Send, Plus, ChevronDown, ChevronUp } from 'lucide-react';

export function OutreachPage() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [form, setForm] = useState({ vendor_name: '', software_name: '', message_template: '' });

  const { data: campaigns, isLoading } = useQuery({
    queryKey: ['campaigns'],
    queryFn: getCampaigns,
  });

  const createMutation = useMutation({
    mutationFn: () => createCampaign(form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['campaigns'] });
      setShowForm(false);
      setForm({ vendor_name: '', software_name: '', message_template: '' });
    },
  });

  const sendMutation = useMutation({
    mutationFn: (id: string) => sendCampaign(id),
    onSuccess: (data) => {
      alert(`Campaign sent! ${data.messages_sent} messages delivered.`);
      queryClient.invalidateQueries({ queryKey: ['campaigns'] });
    },
  });

  const statusBadge = (status: string) => {
    const styles: Record<string, string> = {
      draft: 'bg-gray-100 text-gray-700',
      active: 'bg-green-100 text-green-800',
      completed: 'bg-blue-100 text-blue-800',
    };
    return styles[status] || 'bg-gray-100 text-gray-600';
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Outreach Campaigns</h1>
          <p className="text-gray-600 text-sm mt-1">
            Target companies using specific software with personalized outreach.
          </p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-blue-700 cursor-pointer"
        >
          <Plus className="w-4 h-4" />
          New Campaign
        </button>
      </div>

      {/* Create form */}
      {showForm && (
        <div className="bg-white rounded-lg border border-gray-200 p-4 mb-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">Create Campaign</h3>
          <div className="grid grid-cols-2 gap-4 mb-3">
            <input
              placeholder="Vendor name"
              value={form.vendor_name}
              onChange={(e) => setForm({ ...form, vendor_name: e.target.value })}
              className="border border-gray-300 rounded-md px-3 py-2 text-sm"
            />
            <input
              placeholder="Software name"
              value={form.software_name}
              onChange={(e) => setForm({ ...form, software_name: e.target.value })}
              className="border border-gray-300 rounded-md px-3 py-2 text-sm"
            />
          </div>
          <textarea
            placeholder="Message template (use {vendor} and {software} as placeholders)"
            value={form.message_template}
            onChange={(e) => setForm({ ...form, message_template: e.target.value })}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm h-24 mb-3"
          />
          <div className="flex gap-2">
            <button
              onClick={() => createMutation.mutate()}
              disabled={!form.vendor_name || !form.software_name || !form.message_template}
              className="bg-blue-600 text-white px-4 py-2 rounded-md text-sm hover:bg-blue-700 disabled:opacity-50 cursor-pointer"
            >
              Create
            </button>
            <button
              onClick={() => setShowForm(false)}
              className="bg-gray-100 text-gray-700 px-4 py-2 rounded-md text-sm hover:bg-gray-200 cursor-pointer"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Campaigns list */}
      {isLoading ? (
        <div className="text-center py-12 text-gray-500">Loading...</div>
      ) : !campaigns?.length ? (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
          <Mail className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500">No campaigns yet. Create one to start reaching out.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {campaigns.map((c: Campaign) => (
            <CampaignCard
              key={c.id}
              campaign={c}
              expanded={expandedId === c.id}
              onToggle={() => setExpandedId(expandedId === c.id ? null : c.id)}
              onSend={() => sendMutation.mutate(c.id)}
              sending={sendMutation.isPending}
              statusBadge={statusBadge}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function CampaignCard({
  campaign,
  expanded,
  onToggle,
  onSend,
  sending,
  statusBadge,
}: {
  campaign: Campaign;
  expanded: boolean;
  onToggle: () => void;
  onSend: () => void;
  sending: boolean;
  statusBadge: (s: string) => string;
}) {
  const { data: messages } = useQuery({
    queryKey: ['campaign-messages', campaign.id],
    queryFn: () => getCampaignMessages(campaign.id),
    enabled: expanded,
  });

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <div
        className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-gray-50"
        onClick={onToggle}
      >
        <div className="flex items-center gap-3">
          <span className={`text-xs font-medium px-2 py-1 rounded ${statusBadge(campaign.status)}`}>
            {campaign.status}
          </span>
          <span className="text-sm font-medium text-gray-900">
            {campaign.software_name} by {campaign.vendor_name}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">
            {new Date(campaign.created_at).toLocaleDateString()}
          </span>
          {expanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
        </div>
      </div>

      {expanded && (
        <div className="border-t border-gray-200 px-4 py-4">
          <div className="mb-3">
            <p className="text-xs text-gray-500 mb-1">Message Template</p>
            <pre className="text-sm text-gray-700 whitespace-pre-wrap font-sans bg-gray-50 p-3 rounded">
              {campaign.message_template}
            </pre>
          </div>

          {campaign.status === 'draft' && (
            <button
              onClick={(e) => { e.stopPropagation(); onSend(); }}
              disabled={sending}
              className="flex items-center gap-1.5 bg-blue-600 text-white px-3 py-1.5 rounded text-sm hover:bg-blue-700 cursor-pointer mb-4"
            >
              <Send className="w-3.5 h-3.5" /> Send Campaign
            </button>
          )}

          {messages && messages.length > 0 && (
            <div>
              <p className="text-xs text-gray-500 mb-2">Sent Messages ({messages.length})</p>
              <div className="space-y-2">
                {messages.map((msg: OutreachMessage) => (
                  <div key={msg.id} className="bg-gray-50 rounded p-2 text-xs">
                    <div className="flex justify-between text-gray-500 mb-1">
                      <span>Company: {msg.target_company_id.slice(0, 8)}...</span>
                      <span className={msg.status === 'sent' ? 'text-green-600' : 'text-gray-500'}>
                        {msg.status}
                      </span>
                    </div>
                    <p className="text-gray-700">{msg.message_body}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
