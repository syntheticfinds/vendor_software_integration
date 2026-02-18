import { useQuery } from '@tanstack/react-query';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { getResolutionTime } from '../../api/signals';
import type { ResolutionTimeCategoryData } from '../../api/signals';
import { TrendingDown, TrendingUp, Minus, Info, Clock } from 'lucide-react';

const TREND_CONFIG: Record<string, { icon: typeof TrendingUp; color: string; bg: string }> = {
  improving: { icon: TrendingDown, color: 'text-green-600', bg: 'bg-green-50 border-green-200' },
  worsening: { icon: TrendingUp, color: 'text-red-600', bg: 'bg-red-50 border-red-200' },
  stable: { icon: Minus, color: 'text-blue-600', bg: 'bg-blue-50 border-blue-200' },
};

const CATEGORY_CONFIG: Record<string, { label: string; stroke: string; gradientId: string }> = {
  issue: { label: 'Issue Tickets', stroke: '#ef4444', gradientId: 'resTimeIssueGrad' },
  feature: { label: 'Feature Implementation', stroke: '#8b5cf6', gradientId: 'resTimeFeatureGrad' },
};

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function formatHours(hours: number | null): string {
  if (hours === null) return '\u2014';
  if (hours < 24) return `${hours.toFixed(0)}h`;
  const days = hours / 24;
  return days < 10 ? `${days.toFixed(1)}d` : `${days.toFixed(0)}d`;
}

interface MergedPoint {
  date: string;
  median_hours: number | null;
  p90_hours: number | null;
  pair_count: number;
  open_count: number;
  peerMedian?: number | null;
}

function CategoryTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;

  const point = payload[0]?.payload as MergedPoint | undefined;
  if (!point) return null;

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-3 shadow-md text-xs">
      <p className="font-medium text-gray-700 mb-1.5">{formatDate(label)}</p>
      <div className="space-y-1">
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">Median</span>
          <span className="font-medium">{formatHours(point.median_hours)}</span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">P90</span>
          <span className="font-medium">{formatHours(point.p90_hours)}</span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">Resolved</span>
          <span className="text-gray-700">{point.pair_count} ticket{point.pair_count !== 1 ? 's' : ''}</span>
        </div>
        {point.open_count > 0 && (
          <div className="flex justify-between gap-4">
            <span className="text-gray-500">Still open</span>
            <span className="text-orange-600">{point.open_count}</span>
          </div>
        )}
        {point.peerMedian !== undefined && point.peerMedian !== null && (
          <div className="flex justify-between gap-4 pt-1 border-t border-gray-100">
            <span className="text-gray-500">Peer median</span>
            <span className="text-gray-700">{formatHours(point.peerMedian)}</span>
          </div>
        )}
      </div>
    </div>
  );
}

function CategoryPanel({ data }: { data: ResolutionTimeCategoryData }) {
  const config = CATEGORY_CONFIG[data.category] || CATEGORY_CONFIG.issue;
  const trendCfg = TREND_CONFIG[data.commentary.trend] || TREND_CONFIG.stable;
  const TrendIcon = trendCfg.icon;

  const hasData = data.points.some((p) => p.median_hours !== null);
  if (!hasData) {
    return (
      <div className="mb-4">
        <p className="text-xs font-medium text-gray-500 mb-2">{config.label}</p>
        <p className="text-xs text-gray-400 italic">No resolved tickets in this category yet.</p>
      </div>
    );
  }

  // Merge own and peer data
  const peerMap = new Map<string, number | null>();
  if (data.peer) {
    for (const p of data.peer.points) {
      peerMap.set(p.date, p.median_hours);
    }
  }

  const merged: MergedPoint[] = data.points.map((p) => ({
    ...p,
    ...(data.peer ? { peerMedian: peerMap.get(p.date) ?? null } : {}),
  }));

  const tickInterval = Math.max(1, Math.floor(merged.length / 8));

  const allValues = merged.flatMap((p) => [
    p.median_hours, p.p90_hours, p.peerMedian ?? null,
  ]).filter((v): v is number => v !== null && v !== undefined);
  const maxVal = Math.max(...allValues, 1);

  return (
    <div className="mb-4">
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-medium text-gray-500">{config.label}</p>
        {data.peer && (
          <span className="text-[10px] text-gray-400">
            vs {data.peer.peer_count} {data.peer.category || 'similar'} peer{data.peer.peer_count !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      <ResponsiveContainer width="100%" height={170}>
        <AreaChart data={merged} margin={{ top: 4, right: 4, bottom: 0, left: -10 }}>
          <defs>
            <linearGradient id={config.gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={config.stroke} stopOpacity={0.12} />
              <stop offset="95%" stopColor={config.stroke} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis
            dataKey="date"
            tickFormatter={formatDate}
            interval={tickInterval}
            tick={{ fontSize: 10, fill: '#9ca3af' }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tickFormatter={(v: number) => formatHours(v)}
            domain={[0, Math.ceil(maxVal * 1.2)]}
            tick={{ fontSize: 10, fill: '#9ca3af' }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<CategoryTooltip />} />
          <ReferenceLine y={0} stroke="#e5e7eb" />
          {data.peer && (
            <Area
              type="monotone"
              dataKey="peerMedian"
              stroke="#9ca3af"
              strokeWidth={1.5}
              strokeDasharray="4 3"
              fill="none"
              name="peerMedian"
              connectNulls
            />
          )}
          <Area
            type="monotone"
            dataKey="p90_hours"
            stroke={config.stroke}
            strokeWidth={1}
            strokeDasharray="3 2"
            strokeOpacity={0.4}
            fill="none"
            name="p90_hours"
            connectNulls
          />
          <Area
            type="monotone"
            dataKey="median_hours"
            stroke={config.stroke}
            strokeWidth={2}
            fill={`url(#${config.gradientId})`}
            name="median_hours"
            connectNulls
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-1 px-1">
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-0.5 rounded" style={{ backgroundColor: config.stroke }} />
          <span className="text-[10px] text-gray-500">Median</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-0.5 rounded" style={{ backgroundColor: config.stroke, opacity: 0.4 }} />
          <span className="text-[10px] text-gray-500">P90</span>
        </div>
        {data.peer && (
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-0.5 bg-gray-400 rounded" style={{ borderTop: '1px dashed #9ca3af' }} />
            <span className="text-[10px] text-gray-500">Peer median ({data.peer.category || 'similar use case'})</span>
          </div>
        )}
      </div>

      {/* Commentary */}
      <div className={`flex items-start gap-2 mt-2 rounded-md border p-2.5 ${trendCfg.bg}`}>
        <TrendIcon className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${trendCfg.color}`} />
        <p className="text-xs text-gray-700">{data.commentary.message}</p>
      </div>
    </div>
  );
}

export function ResolutionTimeChart({ softwareId, stageTopic }: { softwareId: string; stageTopic?: string }) {
  const { data: resTime, isLoading } = useQuery({
    queryKey: ['resolution-time', softwareId, stageTopic],
    queryFn: () => getResolutionTime(softwareId, stageTopic),
    enabled: !!softwareId,
  });

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-4 mb-6">
        <div className="animate-pulse">
          <div className="h-4 w-48 bg-gray-200 rounded mb-4" />
          <div className="h-48 bg-gray-100 rounded mb-4" />
          <div className="h-48 bg-gray-100 rounded" />
        </div>
      </div>
    );
  }

  if (!resTime || !resTime.categories.length) return null;

  // Only render if at least one category has data
  const hasAnyData = resTime.categories.some((c) =>
    c.points.some((p) => p.median_hours !== null),
  );
  if (!hasAnyData) return null;

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 mb-6">
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <Clock className="w-3.5 h-3.5 text-gray-400" />
        <p className="text-sm text-gray-500">Resolution Time</p>
        <span className="text-[10px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">
          30-day rolling window
        </span>
      </div>

      {/* Category panels */}
      {resTime.categories.map((cat) => (
        <CategoryPanel key={cat.category} data={cat} />
      ))}

      {/* Guidance */}
      <div className="flex items-start gap-2 mt-2 px-1">
        <Info className="w-3 h-3 text-gray-300 mt-0.5 shrink-0" />
        <p className="text-[10px] text-gray-400 leading-relaxed">
          Resolution time measures how long it takes from ticket creation to resolution.
          Median captures typical experience; P90 highlights worst-case delays.
          Slow resolution erodes the value of the integration.
        </p>
      </div>
    </div>
  );
}
