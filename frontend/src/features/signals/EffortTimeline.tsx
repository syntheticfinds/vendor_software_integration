import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getEffortEvents } from '../../api/signals';
import type { EffortEvent } from '../../api/signals';
import { ChevronDown, ChevronUp } from 'lucide-react';

const SOURCE_LABELS: Record<string, string> = {
  email: 'Email',
  jira: 'Jira',
};

function dotColor(event: EffortEvent): string {
  if (event.classification === 'peripheral') return 'bg-orange-500';
  // Core events: color by severity
  const colors: Record<string, string> = {
    critical: 'bg-red-600',
    high: 'bg-teal-600',
    medium: 'bg-teal-500',
    low: 'bg-teal-400',
  };
  return colors[event.severity] || 'bg-teal-400';
}

function classificationBadge(event: EffortEvent): { label: string; style: string } {
  if (event.classification === 'peripheral') {
    return {
      label: event.peripheral_category || 'Peripheral',
      style: 'bg-orange-100 text-orange-700',
    };
  }
  return {
    label: 'Core',
    style: 'bg-teal-100 text-teal-700',
  };
}

function formatDate(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export function EffortTimeline({ softwareId, stageTopic }: { softwareId: string; stageTopic?: string }) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['effort-events', softwareId, stageTopic],
    queryFn: () => getEffortEvents(softwareId, stageTopic),
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
      <p className="text-xs text-gray-400 py-3">No effort events found for this stage.</p>
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
        const badge = classificationBadge(event);

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
              {/* Dot — teal for core, orange for peripheral */}
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
                    {event.effort_implication}
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
