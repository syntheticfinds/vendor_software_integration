import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getFitnessEvents } from '../../api/signals';
import type { FitnessEvent } from '../../api/signals';
import { ChevronDown, ChevronUp } from 'lucide-react';

const SOURCE_LABELS: Record<string, string> = {
  email: 'Email',
  jira: 'Jira',
};

function dotColor(event: FitnessEvent): string {
  if (event.status === 'fulfillment') return 'bg-green-500';
  if (event.status === 'fulfilled') return 'bg-emerald-400';
  // open request
  const colors: Record<string, string> = {
    critical: 'bg-pink-600',
    high: 'bg-pink-500',
    medium: 'bg-pink-400',
    low: 'bg-pink-300',
  };
  return colors[event.severity] || 'bg-pink-400';
}

function statusBadge(event: FitnessEvent): { label: string; style: string } {
  if (event.status === 'fulfillment') {
    return { label: 'Fulfilled', style: 'bg-green-100 text-green-700' };
  }
  if (event.status === 'fulfilled') {
    return { label: 'Request (fulfilled)', style: 'bg-emerald-100 text-emerald-700' };
  }
  return { label: 'Open request', style: 'bg-pink-100 text-pink-700' };
}

function formatDate(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export function FitnessTimeline({ softwareId }: { softwareId: string }) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['fitness-events', softwareId],
    queryFn: () => getFitnessEvents(softwareId),
    enabled: !!softwareId,
  });

  if (isLoading) {
    return (
      <div className="py-4">
        <div className="animate-pulse space-y-3">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="flex items-center gap-3">
              <div className="w-2.5 h-2.5 bg-gray-200 rounded-full" />
              <div className="flex-1 h-4 bg-gray-200 rounded" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  const events = data?.events || [];

  if (!events.length) {
    return (
      <p className="text-xs text-gray-400 py-3">No feature request events found.</p>
    );
  }

  let lastDate = '';

  return (
    <div className="relative pl-4 py-2 max-h-80 overflow-y-auto">
      {/* Vertical timeline line */}
      <div className="absolute left-[9px] top-2 bottom-2 w-px bg-gray-200" />

      {events.map((event, idx) => {
        const dateStr = formatDate(event.date);
        const showDate = dateStr !== lastDate;
        if (showDate) lastDate = dateStr;
        const isExpanded = expandedIdx === idx;
        const badge = statusBadge(event);

        return (
          <div key={idx}>
            {showDate && (
              <div className="relative flex items-center gap-2 mb-1 -ml-4">
                <span className="text-[10px] font-medium text-gray-400 bg-white pr-2 pl-1 z-10">
                  {dateStr}
                </span>
                <div className="flex-1 h-px bg-gray-100" />
              </div>
            )}
            <div className="relative flex items-start gap-2.5 mb-2.5">
              {/* Dot — pink for open, green for fulfilled */}
              <div className={`w-2.5 h-2.5 rounded-full mt-1.5 shrink-0 z-10 ${dotColor(event)}`} />

              {/* Content */}
              <div className="flex-1 min-w-0">
                <button
                  className="w-full text-left cursor-pointer"
                  onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                >
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-sm text-gray-800 font-medium">
                      {event.summary}
                    </span>
                    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full shrink-0 ${badge.style}`}>
                      {badge.label}
                    </span>
                    <span className="text-[10px] text-gray-400 shrink-0">
                      {SOURCE_LABELS[event.source_type] || event.source_type}
                    </span>
                    {isExpanded
                      ? <ChevronUp className="w-3 h-3 text-gray-300 shrink-0" />
                      : <ChevronDown className="w-3 h-3 text-gray-300 shrink-0" />}
                  </div>
                </button>

                {isExpanded && (
                  <p className="mt-1 text-xs text-gray-500 leading-relaxed pl-0.5">
                    {event.fitness_implication}
                  </p>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
