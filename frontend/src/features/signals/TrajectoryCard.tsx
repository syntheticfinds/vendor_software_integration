import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getTrajectory } from '../../api/signals';
import type { TrajectoryStage, StageSmoothnessMetrics, BenchmarkComparison, StageBenchmark, TrajectoryBenchmarks, TrajectorySummaries, StageSummaries } from '../../api/signals';
import { AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react';
import { FrictionTimeline } from './FrictionTimeline';
import { RecurrenceTimeline } from './RecurrenceTimeline';
import { ResolutionTimeline } from './ResolutionTimeline';
import { EscalationTimeline } from './EscalationTimeline';
import { EffortTimeline } from './EffortTimeline';

const STAGE_LABELS: Record<string, string> = {
  onboarding: 'Onboarding',
  integration: 'Integration',
  stabilization: 'Stabilization',
  productive: 'Productive',
  optimization: 'Optimization',
};

const STAGE_DESCRIPTIONS: Record<string, string> = {
  onboarding: 'Initial setup, account creation, first logins, and early orientation with the vendor.',
  integration: 'Connecting systems, API setup, data pipelines, and technical wiring.',
  stabilization: 'Resolving bugs, tuning performance, and hardening the integration.',
  productive: 'Day-to-day usage where the integration delivers its core value.',
  optimization: 'Fine-tuning, expanding use cases, and maximizing ROI.',
};

const METRIC_LABELS: Record<string, string> = {
  friction: 'Friction',
  recurrence: 'Recurrence',
  escalation: 'Escalation',
  resolution: 'Resolution',
  effort: 'Effort',
};

const METRIC_DESCRIPTIONS: Record<string, string> = {
  friction: 'How much operational friction (bugs, delays, blockers) the integration is generating.',
  recurrence: 'Whether previously resolved issues are resurfacing as new incidents.',
  escalation: 'How often issue severity is increasing within threads (e.g., medium to high).',
  resolution: 'How long it takes for tickets to go from creation to resolution.',
  effort: 'Whether effort is spent on core product work vs. peripheral ecosystem friction (SSO, billing, access).',
};

const METRIC_CHART: Record<string, React.FC<{ softwareId: string; stageTopic?: string }>> = {
  friction: FrictionTimeline,
  recurrence: RecurrenceTimeline,
  escalation: EscalationTimeline,
  resolution: ResolutionTimeline,
  effort: EffortTimeline,
};

function smoothnessColor(score: number | null): string {
  if (score === null) return 'bg-gray-200';
  if (score >= 70) return 'bg-green-500';
  if (score >= 40) return 'bg-yellow-500';
  return 'bg-red-500';
}

function smoothnessTextColor(score: number | null): string {
  if (score === null) return 'text-gray-400';
  if (score >= 70) return 'text-green-600';
  if (score >= 40) return 'text-yellow-600';
  return 'text-red-600';
}

function metricBarColor(score: number): string {
  if (score >= 70) return 'bg-green-500';
  if (score >= 40) return 'bg-yellow-500';
  return 'bg-red-500';
}

function tierBadge(tier: string) {
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
}

function percentileLabel(p: number): string {
  if (p >= 80) return 'Well above peers';
  if (p >= 60) return 'Above average';
  if (p >= 40) return 'On par with peers';
  if (p >= 20) return 'Below average';
  return 'Needs attention';
}

function BenchmarkTooltip({ score, benchmark, category }: {
  score: number;
  benchmark: BenchmarkComparison;
  category?: string | null;
}) {
  const diff = score - benchmark.average;
  const sign = diff >= 0 ? '+' : '';
  return (
    <div className="bg-gray-900 text-white text-xs rounded-md px-3 py-2.5 shadow-lg w-56">
      <p className="font-medium mb-1.5">
        {category ? `vs. similar ${category} tools` : 'vs. similar tools'}
      </p>
      <div className="space-y-1">
        <div className="flex justify-between">
          <span className="text-gray-400">Your score</span>
          <span className="font-medium">{score}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-400">Peer avg</span>
          <span>{benchmark.average.toFixed(1)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-400">Peer median</span>
          <span>{benchmark.median.toFixed(1)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-400">Difference</span>
          <span className={diff >= 0 ? 'text-green-400' : 'text-red-400'}>
            {sign}{diff.toFixed(1)}
          </span>
        </div>
      </div>
      <div className="mt-2 pt-2 border-t border-gray-700">
        <div className="flex justify-between items-center">
          <span className="text-gray-400">{percentileLabel(benchmark.percentile)}</span>
          <span className="font-medium">{benchmark.percentile}th pctl</span>
        </div>
        <p className="text-gray-500 mt-0.5">{benchmark.peer_count} peer integration{benchmark.peer_count !== 1 ? 's' : ''}</p>
      </div>
    </div>
  );
}

function percentileBadgeColor(p: number): string {
  if (p >= 60) return 'bg-green-100 text-green-700';
  if (p >= 40) return 'bg-yellow-100 text-yellow-700';
  return 'bg-red-100 text-red-700';
}

function SmoothnessWithBenchmark({ score, benchmark, category }: {
  score: number;
  benchmark?: BenchmarkComparison | null;
  category?: string | null;
}) {
  return (
    <div className="group/bench relative">
      <div className={`flex items-center gap-1.5 ${benchmark ? 'cursor-help' : ''}`}>
        <p className={`text-lg font-bold ${smoothnessTextColor(score)}`}>
          {score}
        </p>
        {benchmark && (
          <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${percentileBadgeColor(benchmark.percentile)}`}>
            P{benchmark.percentile}
          </span>
        )}
      </div>
      {benchmark && (
        <div className="absolute right-0 top-full mt-1 hidden group-hover/bench:block z-20">
          <BenchmarkTooltip score={score} benchmark={benchmark} category={category} />
        </div>
      )}
    </div>
  );
}

function StageDetail({ stage, benchmarks, softwareId, stageSummaries }: {
  stage: TrajectoryStage;
  benchmarks?: TrajectoryBenchmarks | null;
  softwareId: string;
  stageSummaries?: StageSummaries | null;
}) {
  return (
    <div className="mt-4 p-4 bg-gray-50 rounded-lg border border-gray-200">
      <div className="flex items-center justify-between mb-2">
        <div>
          <h4 className="font-medium text-gray-900">{STAGE_LABELS[stage.name] || stage.name}</h4>
          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
            stage.status === 'completed' ? 'bg-green-100 text-green-700' :
            stage.status === 'current' ? 'bg-blue-100 text-blue-700' :
            'bg-gray-100 text-gray-500'
          }`}>
            {stage.status}
          </span>
        </div>
        {stage.smoothness_score !== null && (
          <div className="text-right">
            <SmoothnessWithBenchmark
              score={stage.smoothness_score}
              benchmark={benchmarks?.stages[stage.name]}
              category={benchmarks?.category}
            />
            <p className="text-xs text-gray-400">smoothness</p>
          </div>
        )}
      </div>

      {stage.date_range && (
        <p className="text-xs text-gray-400 mb-2">
          {new Date(stage.date_range.start).toLocaleDateString()} — {new Date(stage.date_range.end).toLocaleDateString()}
        </p>
      )}

      {stageSummaries?.overall
        ? <p className="text-sm text-gray-600 mb-3">{stageSummaries.overall}</p>
        : <p className="text-sm text-gray-600 mb-3">{stage.explanation}</p>
      }

      {stage.metrics && (
        <MetricBars
          metrics={stage.metrics}
          metricConfidence={stage.metric_confidence}
          softwareId={softwareId}
          stageTopic={stage.name}
          metricBenchmarks={benchmarks?.stages[stage.name]?.metrics}
          metricSummaries={stageSummaries}
        />
      )}
    </div>
  );
}

function MetricBars({ metrics, metricConfidence, softwareId, stageTopic, metricBenchmarks, metricSummaries }: {
  metrics: StageSmoothnessMetrics;
  metricConfidence?: Record<string, 'high' | 'low'> | null;
  softwareId: string;
  stageTopic: string;
  metricBenchmarks?: Record<string, BenchmarkComparison> | null;
  metricSummaries?: StageSummaries | null;
}) {
  const [expandedMetric, setExpandedMetric] = useState<string | null>(null);

  return (
    <div className="space-y-2">
      {(Object.keys(METRIC_LABELS) as (keyof StageSmoothnessMetrics)[]).map((key) => {
        const value = metrics[key];
        const ChartComponent = METRIC_CHART[key];
        const isExpanded = expandedMetric === key;
        const mbm = metricBenchmarks?.[key];
        const metricSummary = metricSummaries?.[key as keyof StageSummaries];
        const isLowConfidence = metricConfidence?.[key] === 'low';

        return (
          <div key={key}>
            <div
              className="group/metric relative flex items-center gap-2 cursor-pointer"
              onClick={() => setExpandedMetric(isExpanded ? null : key)}
            >
              <span className="text-xs text-gray-500 w-20 shrink-0 cursor-help">{METRIC_LABELS[key]}</span>
              <div className="flex-1 bg-gray-200 rounded-full h-2">
                <div
                  className={`h-2 rounded-full ${isLowConfidence ? 'bg-gray-300' : metricBarColor(value)}`}
                  style={{ width: `${Math.max(2, value)}%` }}
                />
              </div>
              <span className={`text-xs w-8 text-right ${isLowConfidence ? 'text-gray-400 italic' : 'text-gray-600'}`}
                title={isLowConfidence ? 'Low confidence — not enough data for this metric' : undefined}
              >{isLowConfidence ? `~${value}` : value}</span>
              {mbm && (
                <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full shrink-0 ${percentileBadgeColor(mbm.percentile)}`}>
                  P{mbm.percentile}
                </span>
              )}
              {isExpanded
                ? <ChevronUp className="w-3 h-3 text-gray-400 shrink-0" />
                : <ChevronDown className="w-3 h-3 text-gray-400 shrink-0" />}
              {METRIC_DESCRIPTIONS[key] && (
                <div className="absolute left-0 right-0 bottom-full mb-1 hidden group-hover/metric:block z-10 pointer-events-none">
                  <div className="bg-gray-900 text-white text-xs rounded-md px-3 py-2 shadow-lg max-w-sm">
                    {METRIC_DESCRIPTIONS[key]}
                  </div>
                </div>
              )}
            </div>
            {isExpanded && (
              <div className="mt-2">
                {metricSummary && (
                  <p className="text-xs text-gray-600 mb-2 pl-[88px]">{metricSummary}</p>
                )}
                {ChartComponent && (
                  <ChartComponent softwareId={softwareId} stageTopic={stageTopic} />
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function TrajectoryCard({ softwareId, trajectorySummaries }: { softwareId: string; trajectorySummaries?: TrajectorySummaries | null }) {
  const [expandedStage, setExpandedStage] = useState<string | null>(null);

  const { data: trajectory, isLoading } = useQuery({
    queryKey: ['trajectory', softwareId],
    queryFn: () => getTrajectory(softwareId),
    enabled: !!softwareId,
  });

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-4 mb-6">
        <div className="animate-pulse flex items-center gap-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="flex-1 flex flex-col items-center gap-2">
              <div className="w-10 h-10 bg-gray-200 rounded-full" />
              <div className="w-16 h-3 bg-gray-200 rounded" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!trajectory) return null;

  const stages = trajectory.stages;

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 mb-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <p className="text-sm text-gray-500">Integration Trajectory</p>
          {tierBadge(trajectory.confidence)}
        </div>
        <div className="flex items-center gap-2">
          <p className="text-xs text-gray-400">Overall smoothness</p>
          <SmoothnessWithBenchmark
            score={trajectory.overall_smoothness}
            benchmark={trajectory.benchmarks?.overall}
            category={trajectory.benchmarks?.category}
          />
        </div>
      </div>

      {/* Trajectory overall summary */}
      {trajectorySummaries?.overall && (
        <p className="text-sm text-gray-600 mb-3">{trajectorySummaries.overall}</p>
      )}

      {/* Regression warning */}
      {trajectory.regression_detected && trajectory.regression_detail && (
        <div className="flex items-start gap-2 bg-orange-50 border border-orange-200 rounded-md p-3 mb-4">
          <AlertTriangle className="w-4 h-4 text-orange-500 mt-0.5 shrink-0" />
          <p className="text-sm text-orange-700">{trajectory.regression_detail}</p>
        </div>
      )}

      {/* Stepper */}
      <div className="flex items-center justify-between px-2">
        {stages.map((stage, i) => {
          const isExpanded = expandedStage === stage.name;
          const isCurrent = stage.status === 'current';
          const isUpcoming = stage.status === 'upcoming';
          const hasData = stage.signal_count > 0;

          return (
            <div key={stage.name} className="flex items-center flex-1">
              {/* Stage circle + label */}
              <button
                onClick={() => setExpandedStage(isExpanded ? null : stage.name)}
                className="flex flex-col items-center gap-1.5 cursor-pointer group/stage relative"
              >
                <div
                  className={`w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold transition-all
                    ${isCurrent ? 'ring-2 ring-offset-2 ring-blue-400' : ''}
                    ${isUpcoming
                      ? 'bg-gray-200 text-gray-400'
                      : `${smoothnessColor(stage.smoothness_score)} text-white`
                    }
                  `}
                >
                  {stage.signal_count || (isUpcoming ? '-' : '0')}
                </div>
                <span className={`text-xs font-medium ${
                  isCurrent ? 'text-blue-600' : isUpcoming ? 'text-gray-400' : 'text-gray-700'
                }`}>
                  {STAGE_LABELS[stage.name] || stage.name}
                </span>
                {(!isUpcoming || hasData) && (
                  isExpanded
                    ? <ChevronUp className="w-3 h-3 text-gray-400" />
                    : <ChevronDown className="w-3 h-3 text-gray-400" />
                )}
                {STAGE_DESCRIPTIONS[stage.name] && (
                  <div className="absolute left-1/2 -translate-x-1/2 top-full mt-1 hidden group-hover/stage:block z-20 pointer-events-none">
                    <div className="bg-gray-900 text-white text-xs rounded-md px-3 py-2 shadow-lg w-52 text-center">
                      {STAGE_DESCRIPTIONS[stage.name]}
                    </div>
                  </div>
                )}
              </button>

              {/* Connector line */}
              {i < stages.length - 1 && (
                <div className={`flex-1 h-0.5 mx-1 mt-[-20px] ${
                  stages[i + 1].status === 'upcoming' ? 'bg-gray-200' : 'bg-gray-300'
                }`} />
              )}
            </div>
          );
        })}
      </div>

      {/* Expanded detail panel */}
      {expandedStage && (() => {
        const stage = stages.find(s => s.name === expandedStage);
        const stageSums = trajectorySummaries?.stages?.[expandedStage];
        return stage && (stage.status !== 'upcoming' || stage.signal_count > 0) ? (
          <StageDetail stage={stage} benchmarks={trajectory.benchmarks} softwareId={softwareId} stageSummaries={stageSums} />
        ) : null;
      })()}
    </div>
  );
}
