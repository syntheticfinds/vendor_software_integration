import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getReviewDrafts, updateReviewDraft, sendReviewDraft } from '../../api/signals';
import type { ReviewDraft } from '../../api/signals';
import { FileText, Check, X, Edit3, Send, ChevronDown, ChevronUp } from 'lucide-react';

export function ReviewDraftsPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editBody, setEditBody] = useState('');

  const { data: drafts, isLoading } = useQuery({
    queryKey: ['review-drafts', statusFilter],
    queryFn: () => getReviewDrafts(statusFilter),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, status, edited_body }: { id: string; status: string; edited_body?: string }) =>
      updateReviewDraft(id, { status, edited_body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['review-drafts'] });
      setEditingId(null);
    },
  });

  const sendMutation = useMutation({
    mutationFn: (id: string) => sendReviewDraft(id),
    onSuccess: () => {
      alert('Review sent successfully!');
      queryClient.invalidateQueries({ queryKey: ['review-drafts'] });
    },
    onError: (error: unknown) => {
      const message = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Failed to send';
      alert(message);
    },
  });

  const statusBadge = (status: string) => {
    const styles: Record<string, string> = {
      pending: 'bg-yellow-100 text-yellow-800',
      edited: 'bg-blue-100 text-blue-800',
      approved: 'bg-green-100 text-green-800',
      declined: 'bg-red-100 text-red-800',
      sent: 'bg-purple-100 text-purple-800',
    };
    return styles[status] || 'bg-gray-100 text-gray-600';
  };

  const tierStyle = (tier: string) => {
    const styles: Record<string, string> = {
      preliminary: 'bg-gray-100 text-gray-600',
      developing: 'bg-blue-100 text-blue-700',
      solid: 'bg-green-100 text-green-700',
    };
    const labels: Record<string, string> = {
      preliminary: 'Preliminary',
      developing: 'Developing',
      solid: 'Solid',
    };
    return { className: styles[tier] || styles.preliminary, label: labels[tier] || tier };
  };

  const startEditing = (draft: ReviewDraft) => {
    setEditingId(draft.id);
    setEditBody(draft.edited_body || draft.draft_body);
    setExpandedId(draft.id);
  };

  const saveEdit = (id: string) => {
    updateMutation.mutate({ id, status: 'edited', edited_body: editBody });
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Review Drafts</h1>
        <p className="text-gray-600 text-sm mt-1">
          AI-generated review emails for your vendor integrations. Review, edit, and approve before sending.
        </p>
      </div>

      <div className="flex gap-2 mb-4">
        {['all', 'pending', 'edited', 'approved', 'declined', 'sent'].map((s) => (
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
      ) : !drafts?.length ? (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
          <FileText className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500">
            No review drafts yet. Run signal analysis on a software integration to generate drafts.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {drafts.map((draft: ReviewDraft) => (
            <div key={draft.id} className="bg-white rounded-lg border border-gray-200 overflow-hidden">
              {/* Header */}
              <div
                className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-gray-50"
                onClick={() => setExpandedId(expandedId === draft.id ? null : draft.id)}
              >
                <div className="flex items-center gap-3">
                  <span className={`text-xs font-medium px-2 py-1 rounded ${statusBadge(draft.status)}`}>
                    {draft.status}
                  </span>
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${tierStyle(draft.confidence_tier).className}`}>
                    {tierStyle(draft.confidence_tier).label}
                  </span>
                  <span className="text-sm font-medium text-gray-900">
                    {draft.draft_subject || 'Untitled Review'}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500">
                    {new Date(draft.created_at).toLocaleDateString()}
                  </span>
                  {expandedId === draft.id ? (
                    <ChevronUp className="w-4 h-4 text-gray-400" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-gray-400" />
                  )}
                </div>
              </div>

              {/* Expanded body */}
              {expandedId === draft.id && (
                <div className="border-t border-gray-200 px-4 py-4">
                  {editingId === draft.id ? (
                    <div>
                      <textarea
                        value={editBody}
                        onChange={(e) => setEditBody(e.target.value)}
                        className="w-full h-64 border border-gray-300 rounded-md p-3 text-sm font-mono"
                      />
                      <div className="flex gap-2 mt-3">
                        <button
                          onClick={() => saveEdit(draft.id)}
                          disabled={updateMutation.isPending}
                          className="flex items-center gap-1 bg-blue-600 text-white px-3 py-1.5 rounded text-sm hover:bg-blue-700 cursor-pointer"
                        >
                          <Check className="w-3.5 h-3.5" /> Save
                        </button>
                        <button
                          onClick={() => setEditingId(null)}
                          className="flex items-center gap-1 bg-gray-100 text-gray-700 px-3 py-1.5 rounded text-sm hover:bg-gray-200 cursor-pointer"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div>
                      <pre className="text-sm text-gray-700 whitespace-pre-wrap font-sans">
                        {draft.edited_body || draft.draft_body}
                      </pre>
                      <div className="flex gap-2 mt-4 pt-3 border-t border-gray-100">
                        {(draft.status === 'pending' || draft.status === 'edited') && (
                          <>
                            <button
                              onClick={() => updateMutation.mutate({ id: draft.id, status: 'approved' })}
                              className="flex items-center gap-1 bg-green-600 text-white px-3 py-1.5 rounded text-sm hover:bg-green-700 cursor-pointer"
                            >
                              <Check className="w-3.5 h-3.5" /> Approve
                            </button>
                            <button
                              onClick={() => startEditing(draft)}
                              className="flex items-center gap-1 bg-gray-100 text-gray-700 px-3 py-1.5 rounded text-sm hover:bg-gray-200 cursor-pointer"
                            >
                              <Edit3 className="w-3.5 h-3.5" /> Edit
                            </button>
                            <button
                              onClick={() => updateMutation.mutate({ id: draft.id, status: 'declined' })}
                              className="flex items-center gap-1 bg-red-50 text-red-700 px-3 py-1.5 rounded text-sm hover:bg-red-100 cursor-pointer"
                            >
                              <X className="w-3.5 h-3.5" /> Decline
                            </button>
                          </>
                        )}
                        {draft.status === 'approved' && (
                          <button
                            onClick={() => sendMutation.mutate(draft.id)}
                            disabled={sendMutation.isPending}
                            className="flex items-center gap-1 bg-purple-600 text-white px-3 py-1.5 rounded text-sm hover:bg-purple-700 cursor-pointer"
                          >
                            <Send className="w-3.5 h-3.5" /> Send Review
                          </button>
                        )}
                      </div>
                    </div>
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
