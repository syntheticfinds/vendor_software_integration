import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getRecurrenceEvents } from '../../api/signals';
import type { RecurrenceEvent } from '../../api/signals';
import { ChevronDown, ChevronUp, RotateCcw } from 'lucide-react';

function impactStyle(impact: string): string {
  if (impact.includes('improvement')) return 'bg-green-100 text-green-700';
  if (impact.includes('major')) return 'bg-red-100 text-red-700';
  if (impact.includes('significant')) return 'bg-orange-100 text-orange-700';
  if (impact.includes('minor')) return 'bg-blue-100 text-blue-700';
  return 'bg-yellow-100 text-yellow-700'; // moderate setback / default
}

const SOURCE_LABELS: Record<string, string> = {
  email: 'Email',
  jira: 'Jira',
};

function dotColor(event: RecurrenceEvent): string {
  if (event.valence === 'positive') return 'bg-green-500';
  const colors: Record<string, string> = {
    critical: 'bg-red-600',
    high: 'bg-orange-500',
    medium: 'bg-yellow-500',
    low: 'bg-blue-400',
  };
  return colors[event.severity] || 'bg-gray-400';
}

function formatDate(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function incidentBadgeColor(num: number): string {
  if (num >= 4) return 'bg-red-100 text-red-700';
  if (num >= 3) return 'bg-orange-100 text-orange-700';
  return 'bg-purple-100 text-purple-700';
}

export function RecurrenceTimeline({ softwareId, stageTopic }: { softwareId: string; stageTopic?: string }) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['recurrence-events', softwareId, stageTopic],
    queryFn: () => getRecurrenceEvents(softwareId, stageTopic),
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
      <p className="text-xs text-gray-400 py-3">No recurring issues found for this stage.</p>
    );
  }

  // Group events by date for date headers
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
              {/* Dot */}
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
                    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full shrink-0 ${impactStyle(event.impact)}`}>
                      {event.impact}
                    </span>
                    <span className={`inline-flex items-center gap-0.5 text-[10px] font-medium px-1.5 py-0.5 rounded-full shrink-0 ${incidentBadgeColor(event.incident_number)}`}>
                      <RotateCcw className="w-2.5 h-2.5" />
                      #{event.incident_number}
                      {event.first_seen && (
                        <span className="text-[9px] opacity-75 ml-0.5">
                          (1st: {event.first_seen})
                        </span>
                      )}
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
                    {event.recurrence_implication}
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
