import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getSignalEvents, getHealthScores, getHealthScoreBenchmarks, getSummaries, ingestSignals, analyzeSignals } from '../../api/signals';
import { getSoftwareList } from '../../api/software';
import type { SignalEvent } from '../../api/signals';
import { Activity, Zap, TrendingUp, ChevronDown, ChevronUp } from 'lucide-react';
import { TrajectoryCard } from './TrajectoryCard';
import { ResponsivenessChart } from './ResponsivenessChart';
import { FitnessTimeline } from './FitnessTimeline';
import { ReliabilityTimeline } from './ReliabilityTimeline';
import { PerformanceTimeline } from './PerformanceTimeline';

export function SignalFeedPage() {
  const queryClient = useQueryClient();
  const [selectedSoftware, setSelectedSoftware] = useState<string | undefined>(undefined);
  const [severityFilter, setSeverityFilter] = useState<string | undefined>(undefined);
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);

  const { data: softwareList } = useQuery({
    queryKey: ['software'],
    queryFn: () => getSoftwareList(),
  });

  const { data: events, isLoading } = useQuery({
    queryKey: ['signal-events', selectedSoftware, severityFilter],
    queryFn: () => getSignalEvents({ software_id: selectedSoftware, severity: severityFilter }),
  });

  const { data: healthScores } = useQuery({
    queryKey: ['health-scores', selectedSoftware],
    queryFn: () => getHealthScores(selectedSoftware),
  });

  const { data: hsBenchmarks } = useQuery({
    queryKey: ['health-score-benchmarks', selectedSoftware],
    queryFn: () => getHealthScoreBenchmarks(selectedSoftware!),
    enabled: !!selectedSoftware,
  });

  const { data: summaries } = useQuery({
    queryKey: ['summaries', selectedSoftware],
    queryFn: () => getSummaries(selectedSoftware!),
    enabled: !!selectedSoftware,
  });

  const ingestMutation = useMutation({
    mutationFn: (softwareId: string) => ingestSignals(softwareId),
    onSuccess: (data) => {
      alert(`Ingested ${data.ingested_count} signal events.`);
      queryClient.invalidateQueries({ queryKey: ['signal-events'] });
    },
  });

  const analyzeMutation = useMutation({
    mutationFn: (softwareId: string) => analyzeSignals(softwareId),
    onSuccess: (data) => {
      alert(`Analysis ${data.status}. Check health scores and review drafts.`);
      queryClient.invalidateQueries({ queryKey: ['health-scores'] });
      queryClient.invalidateQueries({ queryKey: ['health-score-benchmarks'] });
      queryClient.invalidateQueries({ queryKey: ['review-drafts'] });
      queryClient.invalidateQueries({ queryKey: ['trajectory'] });
      queryClient.invalidateQueries({ queryKey: ['issue-rate'] });
      queryClient.invalidateQueries({ queryKey: ['recurrence-rate'] });
      queryClient.invalidateQueries({ queryKey: ['resolution-time'] });
      queryClient.invalidateQueries({ queryKey: ['vendor-responsiveness'] });
      queryClient.invalidateQueries({ queryKey: ['escalation-rate'] });
      queryClient.invalidateQueries({ queryKey: ['core-peripheral'] });
      queryClient.invalidateQueries({ queryKey: ['fitness-metrics'] });
      queryClient.invalidateQueries({ queryKey: ['fitness-events'] });
      queryClient.invalidateQueries({ queryKey: ['reliability'] });
      queryClient.invalidateQueries({ queryKey: ['reliability-events'] });
      queryClient.invalidateQueries({ queryKey: ['performance'] });
      queryClient.invalidateQueries({ queryKey: ['performance-events'] });
      queryClient.invalidateQueries({ queryKey: ['summaries'] });
    },
  });

  const latestScore = healthScores?.[0];

  const severityColor = (severity: string | null) => {
    const colors: Record<string, string> = {
      critical: 'bg-red-100 text-red-800',
      high: 'bg-orange-100 text-orange-800',
      medium: 'bg-yellow-100 text-yellow-800',
      low: 'bg-blue-100 text-blue-800',
    };
    return colors[severity || ''] || 'bg-gray-100 text-gray-600';
  };

  const sourceIcon = (source: string) => {
    const icons: Record<string, string> = { jira: 'J', email: 'E' };
    return icons[source] || '?';
  };

  const scoreColor = (score: number) => {
    if (score >= 80) return 'text-green-600';
    if (score >= 60) return 'text-yellow-600';
    return 'text-red-600';
  };

  const pctlBadge = (p: number) => {
    const color = p >= 75 ? 'bg-green-100 text-green-700' : p >= 50 ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700';
    return <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${color}`}>P{p}</span>;
  };

  const tierBadge = (tier: string) => {
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
    return (
      <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${styles[tier] || styles.preliminary}`}>
        {labels[tier] || tier} confidence
      </span>
    );
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Signal Feed</h1>
          <p className="text-gray-600 text-sm mt-1">
            Operational signals from your vendor integrations
          </p>
        </div>
        <div className="flex gap-2">
          {selectedSoftware && (
            <>
              <button
                onClick={() => ingestMutation.mutate(selectedSoftware)}
                disabled={ingestMutation.isPending}
                className="flex items-center gap-2 bg-gray-100 text-gray-700 px-4 py-2 rounded-md text-sm font-medium hover:bg-gray-200 disabled:opacity-50 cursor-pointer"
              >
                <Zap className="w-4 h-4" />
                {ingestMutation.isPending ? 'Ingesting...' : 'Ingest Signals'}
              </button>
              <button
                onClick={() => analyzeMutation.mutate(selectedSoftware)}
                disabled={analyzeMutation.isPending}
                className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-50 cursor-pointer"
              >
                <TrendingUp className="w-4 h-4" />
                {analyzeMutation.isPending ? 'Analyzing...' : 'Run Analysis'}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Software selector */}
      <div className="flex gap-4 mb-6">
        <select
          value={selectedSoftware || ''}
          onChange={(e) => setSelectedSoftware(e.target.value || undefined)}
          className="border border-gray-300 rounded-md px-3 py-2 text-sm"
        >
          <option value="">All Software</option>
          {softwareList?.items.map((sw) => (
            <option key={sw.id} value={sw.id}>
              {sw.software_name} ({sw.vendor_name})
            </option>
          ))}
        </select>

        <div className="flex gap-2">
          {['all', 'critical', 'high', 'medium', 'low'].map((s) => (
            <button
              key={s}
              onClick={() => setSeverityFilter(s === 'all' ? undefined : s)}
              className={`px-3 py-1 rounded-full text-sm cursor-pointer ${
                (s === 'all' && !severityFilter) || severityFilter === s
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Health score card */}
      {latestScore && (
        <div className="bg-white rounded-lg border border-gray-200 p-4 mb-6">
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <p className="text-sm text-gray-500">Latest Health Score</p>
                {tierBadge(latestScore.confidence_tier)}
              </div>
              <div className="flex items-center gap-2">
                <p className={`text-3xl font-bold ${scoreColor(latestScore.score)}`}>
                  {latestScore.score}/100
                </p>
                {hsBenchmarks?.overall && pctlBadge(hsBenchmarks.overall.percentile)}
              </div>
              <p className="text-xs text-gray-400 mt-0.5">
                Based on {latestScore.signal_count} signal{latestScore.signal_count !== 1 ? 's' : ''}
              </p>
            </div>
            <div className="flex gap-4">
              {(() => {
                const catConfidence = (latestScore.category_breakdown as Record<string, unknown>).category_confidence as Record<string, string> | undefined;
                return Object.entries(latestScore.category_breakdown)
                  .filter(([key]) => key !== 'support_quality' && key !== 'category_confidence')
                  .map(([key, value]) => {
                    const isLowConf = catConfidence?.[key] === 'low';
                    return (
                      <button
                        key={key}
                        onClick={() => setExpandedCategory(expandedCategory === key ? null : key)}
                        className={`text-center cursor-pointer rounded-lg px-3 py-1.5 transition-colors ${
                          expandedCategory === key ? 'bg-gray-100' : 'hover:bg-gray-50'
                        }`}
                      >
                        <p className="text-xs text-gray-500">{key.replace(/_/g, ' ')}</p>
                        <div className="flex items-center justify-center gap-1">
                          <p className={`text-lg font-semibold ${isLowConf ? 'text-gray-400 italic' : scoreColor(value as number)}`}
                            title={isLowConf ? 'Low confidence — few relevant signals for this category' : undefined}
                          >
                            {isLowConf ? `~${value}` : (value as number)}
                          </p>
                          {hsBenchmarks?.categories[key] && pctlBadge(hsBenchmarks.categories[key].percentile)}
                        </div>
                        {expandedCategory === key
                          ? <ChevronUp className="w-3 h-3 text-gray-400 mx-auto" />
                          : <ChevronDown className="w-3 h-3 text-gray-400 mx-auto" />}
                      </button>
                    );
                  });
              })()}
            </div>
          </div>
          {(summaries?.health?.overall || latestScore.signal_summary) && (
            <p className="text-sm text-gray-600 mt-3 border-t border-gray-100 pt-3">
              {summaries?.health?.overall || latestScore.signal_summary}
            </p>
          )}
          {expandedCategory && selectedSoftware && (() => {
            const charts: Record<string, React.FC<{ softwareId: string }>> = {
              reliability: ReliabilityTimeline,
              performance: PerformanceTimeline,
              fitness_for_purpose: FitnessTimeline,
            };
            const ChartComp = charts[expandedCategory];
            if (!ChartComp) return null;
            const catSummary = summaries?.health?.[expandedCategory as keyof typeof summaries.health];
            return (
              <div className="mt-3 border-t border-gray-100 pt-3">
                {catSummary && (
                  <p className="text-sm text-gray-600 mb-3">{catSummary}</p>
                )}
                <ChartComp softwareId={selectedSoftware} />
              </div>
            );
          })()}
        </div>
      )}

      {/* Trajectory card */}
      {selectedSoftware && <TrajectoryCard softwareId={selectedSoftware} trajectorySummaries={summaries?.trajectory} />}

      {/* Vendor Responsiveness (cross-stage, standalone) */}
      {selectedSoftware && <ResponsivenessChart softwareId={selectedSoftware} />}

      {/* Events table */}
      {isLoading ? (
        <div className="text-center py-12 text-gray-500">Loading signals...</div>
      ) : !events?.items.length ? (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
          <Activity className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500">
            No signal events yet.{' '}
            {selectedSoftware
              ? 'Click "Ingest Signals" to fetch events from connectors.'
              : 'Select a software integration to get started.'}
          </p>
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 text-sm font-medium text-gray-600">Source</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-gray-600">Title</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-gray-600">Type</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-gray-600">Severity</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-gray-600">Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {events.items.map((event: SignalEvent) => (
                <tr key={event.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-gray-100 text-xs font-bold text-gray-600">
                      {sourceIcon(event.source_type)}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="text-sm font-medium text-gray-900">{event.title}</div>
                    {event.body && (
                      <div className="text-xs text-gray-500 mt-0.5 line-clamp-1">{event.body}</div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">{event.event_type}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-medium px-2 py-1 rounded ${severityColor(event.severity)}`}>
                      {event.severity || 'unknown'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500">
                    {new Date(event.occurred_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-4 py-3 border-t border-gray-200 text-sm text-gray-500">
            {events.total} event{events.total !== 1 ? 's' : ''} total
          </div>
        </div>
      )}
    </div>
  );
}
