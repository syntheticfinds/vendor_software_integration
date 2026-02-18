import { useQuery } from '@tanstack/react-query';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { getPerformanceMetrics } from '../../api/signals';
import { TrendingDown, TrendingUp, Minus, Info, Timer, Zap } from 'lucide-react';

const TREND_CONFIG: Record<string, { icon: typeof TrendingUp; color: string; bg: string }> = {
  improving: { icon: TrendingDown, color: 'text-green-600', bg: 'bg-green-50 border-green-200' },
  worsening: { icon: TrendingUp, color: 'text-red-600', bg: 'bg-red-50 border-red-200' },
  stable: { icon: Minus, color: 'text-blue-600', bg: 'bg-blue-50 border-blue-200' },
};

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

interface MergedPoint {
  date: string;
  latency_count: number;
  rate_limit_count: number;
  total_signals: number;
  top_latency_issues: string[];
  top_rate_limit_issues: string[];
  peerCount?: number;
}

function PerformanceTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;

  const point = payload[0]?.payload as MergedPoint | undefined;
  if (!point) return null;

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-3 shadow-md text-xs">
      <p className="font-medium text-gray-700 mb-1.5">{formatDate(label)}</p>
      <div className="space-y-1">
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">Latency complaints</span>
          <span className="font-medium text-violet-600">{point.latency_count}</span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">Rate-limit events</span>
          <span className="font-medium text-cyan-600">{point.rate_limit_count}</span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">Total signals</span>
          <span className="text-gray-700">{point.total_signals}</span>
        </div>
        {point.peerCount !== undefined && (
          <div className="flex justify-between gap-4">
            <span className="text-gray-500">Peer avg combined</span>
            <span className="text-gray-700">{point.peerCount}</span>
          </div>
        )}
      </div>
      {point.top_latency_issues.length > 0 && (
        <div className="mt-2 pt-2 border-t border-gray-100">
          <p className="text-gray-500 mb-1">Latency issues:</p>
          {point.top_latency_issues.map((title, i) => (
            <p key={i} className="text-gray-700 pl-2">
              <span className="text-violet-400 mr-1">&bull;</span>
              {title}
            </p>
          ))}
        </div>
      )}
      {point.top_rate_limit_issues.length > 0 && (
        <div className="mt-2 pt-2 border-t border-gray-100">
          <p className="text-gray-500 mb-1">Rate-limit issues:</p>
          {point.top_rate_limit_issues.map((title, i) => (
            <p key={i} className="text-gray-700 pl-2">
              <span className="text-cyan-400 mr-1">&bull;</span>
              {title}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

export function PerformanceChart({ softwareId }: { softwareId: string }) {
  const { data: performance, isLoading } = useQuery({
    queryKey: ['performance', softwareId],
    queryFn: () => getPerformanceMetrics(softwareId),
    enabled: !!softwareId,
  });

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-4 mb-6">
        <div className="animate-pulse">
          <div className="h-4 w-48 bg-gray-200 rounded mb-4" />
          <div className="h-48 bg-gray-100 rounded" />
        </div>
      </div>
    );
  }

  if (!performance || !performance.points.length) return null;

  const peer = performance.peer;
  const commentary = performance.commentary;
  const trendCfg = TREND_CONFIG[commentary.trend] || TREND_CONFIG.stable;
  const TrendIcon = trendCfg.icon;

  // Merge own + peer data
  const peerMap = new Map<string, number>();
  if (peer) {
    for (const p of peer.points) {
      peerMap.set(p.date, p.count);
    }
  }

  const merged: MergedPoint[] = performance.points.map((p) => ({
    ...p,
    ...(peer ? { peerCount: peerMap.get(p.date) ?? 0 } : {}),
  }));

  const tickInterval = Math.max(1, Math.floor(merged.length / 8));

  const allValues = merged.flatMap((p) => [
    p.latency_count,
    p.rate_limit_count,
    p.peerCount ?? 0,
  ]);
  const maxVal = Math.max(...allValues, 1);

  const latest = performance.points[performance.points.length - 1];

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 mb-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Timer className="w-3.5 h-3.5 text-gray-400" />
          <p className="text-sm text-gray-500">Performance Complaints</p>
          <span className="text-[10px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">
            30-day rolling window
          </span>
        </div>
        {peer && (
          <span className="text-[10px] text-gray-400">
            vs {peer.peer_count} {peer.category || 'similar'} peer{peer.peer_count !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* Chart */}
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={merged} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
          <defs>
            <linearGradient id="perfLatencyGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#7c3aed" stopOpacity={0.15} />
              <stop offset="95%" stopColor="#7c3aed" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="perfRateLimitGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.12} />
              <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
            </linearGradient>
            {peer && (
              <linearGradient id="perfPeerGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#9ca3af" stopOpacity={0.1} />
                <stop offset="95%" stopColor="#9ca3af" stopOpacity={0} />
              </linearGradient>
            )}
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
            allowDecimals={false}
            domain={[0, Math.ceil(maxVal * 1.2)]}
            tick={{ fontSize: 10, fill: '#9ca3af' }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<PerformanceTooltip />} />
          <ReferenceLine y={0} stroke="#e5e7eb" />
          {peer && (
            <Area
              type="monotone"
              dataKey="peerCount"
              stroke="#9ca3af"
              strokeWidth={1.5}
              strokeDasharray="4 3"
              fill="url(#perfPeerGrad)"
              name="peerCount"
              connectNulls
            />
          )}
          <Area
            type="monotone"
            dataKey="rate_limit_count"
            stroke="#06b6d4"
            strokeWidth={1.5}
            fill="url(#perfRateLimitGrad)"
            name="rate_limit_count"
            connectNulls
          />
          <Area
            type="monotone"
            dataKey="latency_count"
            stroke="#7c3aed"
            strokeWidth={2}
            fill="url(#perfLatencyGrad)"
            name="latency_count"
            connectNulls
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-2 px-1">
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-0.5 bg-violet-600 rounded" />
          <span className="text-[10px] text-gray-500">Latency / slowness</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-0.5 bg-cyan-500 rounded" />
          <span className="text-[10px] text-gray-500">Rate limit / throttling</span>
        </div>
        {peer && (
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-0.5 bg-gray-400 rounded" style={{ borderTop: '1px dashed #9ca3af' }} />
            <span className="text-[10px] text-gray-500">Peer avg ({peer.category || 'similar use case'})</span>
          </div>
        )}
      </div>

      {/* Sub-stats badges */}
      <div className="flex items-center gap-3 mt-3 flex-wrap">
        <div className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 ${
          latest.latency_count > 0
            ? 'bg-violet-50 border border-violet-200'
            : 'bg-green-50 border border-green-200'
        }`}>
          <Timer className="w-3 h-3" style={{ color: latest.latency_count > 0 ? '#6d28d9' : '#15803d' }} />
          <span className={`text-[10px] font-medium ${
            latest.latency_count > 0 ? 'text-violet-700' : 'text-green-700'
          }`}>
            {latest.latency_count} latency complaint{latest.latency_count !== 1 ? 's' : ''}
          </span>
        </div>
        <div className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 ${
          latest.rate_limit_count > 0
            ? 'bg-cyan-50 border border-cyan-200'
            : 'bg-green-50 border border-green-200'
        }`}>
          <Zap className="w-3 h-3" style={{ color: latest.rate_limit_count > 0 ? '#0891b2' : '#15803d' }} />
          <span className={`text-[10px] font-medium ${
            latest.rate_limit_count > 0 ? 'text-cyan-700' : 'text-green-700'
          }`}>
            {latest.rate_limit_count} rate-limit event{latest.rate_limit_count !== 1 ? 's' : ''}
          </span>
        </div>
      </div>

      {/* Commentary */}
      <div className={`flex items-start gap-2 mt-3 rounded-md border p-3 ${trendCfg.bg}`}>
        <TrendIcon className={`w-4 h-4 mt-0.5 shrink-0 ${trendCfg.color}`} />
        <p className="text-sm text-gray-700">{commentary.message}</p>
      </div>

      {/* Guidance */}
      <div className="flex items-start gap-2 mt-2 px-1">
        <Info className="w-3 h-3 text-gray-300 mt-0.5 shrink-0" />
        <p className="text-[10px] text-gray-400 leading-relaxed">
          Latency complaints track signals mentioning slow response times,
          timeouts, or sluggish performance. Rate-limit events track signals
          about throttling, API quota limits, or 429 errors — indicating the
          vendor&apos;s infrastructure may not be scaling with your usage.
        </p>
      </div>
    </div>
  );
}
