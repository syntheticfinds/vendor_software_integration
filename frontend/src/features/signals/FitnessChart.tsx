import { useQuery } from '@tanstack/react-query';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { getFitnessMetrics } from '../../api/signals';
import { TrendingDown, TrendingUp, Minus, Info, Lightbulb, RefreshCw, CheckCircle } from 'lucide-react';

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
  request_ratio: number;
  request_count: number;
  total_signals: number;
  repeat_count: number;
  unique_request_topics: number;
  fulfilled_count: number;
  total_request_threads: number;
  fulfillment_rate: number;
  top_repeats: string[];
  peerRatio?: number;
}

function FitnessTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;

  const point = payload[0]?.payload as MergedPoint | undefined;
  if (!point) return null;

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-3 shadow-md text-xs">
      <p className="font-medium text-gray-700 mb-1.5">{formatDate(label)}</p>
      <div className="space-y-1">
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">Feature request ratio</span>
          <span className="font-medium text-pink-600">{point.request_ratio}%</span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">Requests / Total</span>
          <span className="text-gray-700">{point.request_count} / {point.total_signals}</span>
        </div>
        {point.peerRatio !== undefined && (
          <div className="flex justify-between gap-4">
            <span className="text-gray-500">Peer avg</span>
            <span className="text-gray-700">{point.peerRatio}%</span>
          </div>
        )}
        <div className="flex justify-between gap-4 pt-1 border-t border-gray-100">
          <span className="text-gray-500">Recurring topics</span>
          <span className="text-gray-700">
            {point.repeat_count} of {point.unique_request_topics}
          </span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">Fulfillment rate</span>
          <span className="text-gray-700">
            {point.fulfillment_rate}% ({point.fulfilled_count}/{point.total_request_threads})
          </span>
        </div>
      </div>
      {point.top_repeats.length > 0 && (
        <div className="mt-2 pt-2 border-t border-gray-100">
          <p className="text-gray-500 mb-1">Recurring requests:</p>
          {point.top_repeats.map((topic, i) => (
            <p key={i} className="text-gray-700 pl-2">
              <span className="text-pink-400 mr-1">&bull;</span>
              {topic}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

export function FitnessChart({ softwareId }: { softwareId: string }) {
  const { data: fitness, isLoading } = useQuery({
    queryKey: ['fitness-metrics', softwareId],
    queryFn: () => getFitnessMetrics(softwareId),
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

  if (!fitness || !fitness.points.length) return null;

  const hasAnyData = fitness.points.some((p) => p.total_signals > 0);
  if (!hasAnyData) return null;

  const peer = fitness.peer;
  const commentary = fitness.commentary;
  const trendCfg = TREND_CONFIG[commentary.trend] || TREND_CONFIG.stable;
  const TrendIcon = trendCfg.icon;

  // Merge own + peer data
  const peerMap = new Map<string, number>();
  if (peer) {
    for (const p of peer.points) {
      peerMap.set(p.date, p.count);
    }
  }

  const merged: MergedPoint[] = fitness.points.map((p) => ({
    ...p,
    ...(peer ? { peerRatio: peerMap.get(p.date) ?? 0 } : {}),
  }));

  const tickInterval = Math.max(1, Math.floor(merged.length / 8));

  const allValues = merged.flatMap((p) => [p.request_ratio, p.peerRatio ?? 0]);
  const maxVal = Math.max(...allValues, 5);

  // Latest point stats
  const latest = fitness.points[fitness.points.length - 1];

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 mb-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Lightbulb className="w-3.5 h-3.5 text-gray-400" />
          <p className="text-sm text-gray-500">Feature Request Pressure</p>
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
            <linearGradient id="fitnessGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#ec4899" stopOpacity={0.15} />
              <stop offset="95%" stopColor="#ec4899" stopOpacity={0} />
            </linearGradient>
            {peer && (
              <linearGradient id="fitnessPeerGrad" x1="0" y1="0" x2="0" y2="1">
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
            tickFormatter={(v: number) => `${v}%`}
            tick={{ fontSize: 10, fill: '#9ca3af' }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<FitnessTooltip />} />
          <ReferenceLine y={0} stroke="#e5e7eb" />
          {peer && (
            <Area
              type="monotone"
              dataKey="peerRatio"
              stroke="#9ca3af"
              strokeWidth={1.5}
              strokeDasharray="4 3"
              fill="url(#fitnessPeerGrad)"
              name="peerRatio"
              connectNulls
            />
          )}
          <Area
            type="monotone"
            dataKey="request_ratio"
            stroke="#ec4899"
            strokeWidth={2}
            fill="url(#fitnessGrad)"
            name="request_ratio"
            connectNulls
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-2 px-1">
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-0.5 bg-pink-500 rounded" />
          <span className="text-[10px] text-gray-500">Feature request ratio</span>
        </div>
        {peer && (
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-0.5 bg-gray-400 rounded" style={{ borderTop: '1px dashed #9ca3af' }} />
            <span className="text-[10px] text-gray-500">Peer avg ({peer.category || 'similar use case'})</span>
          </div>
        )}
      </div>

      {/* Sub-stats badges */}
      <div className="flex items-center gap-3 mt-3">
        <div className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 ${
          latest.repeat_count > 0
            ? 'bg-orange-50 border border-orange-200'
            : 'bg-green-50 border border-green-200'
        }`}>
          <RefreshCw className="w-3 h-3" style={{ color: latest.repeat_count > 0 ? '#c2410c' : '#15803d' }} />
          <span className={`text-[10px] font-medium ${
            latest.repeat_count > 0 ? 'text-orange-700' : 'text-green-700'
          }`}>
            {latest.repeat_count} recurring request{latest.repeat_count !== 1 ? 's' : ''}
          </span>
        </div>
        {latest.total_request_threads > 0 && (
          <div className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 ${
            latest.fulfillment_rate >= 50
              ? 'bg-green-50 border border-green-200'
              : latest.fulfillment_rate >= 25
                ? 'bg-yellow-50 border border-yellow-200'
                : 'bg-red-50 border border-red-200'
          }`}>
            <CheckCircle className="w-3 h-3" style={{
              color: latest.fulfillment_rate >= 50 ? '#15803d'
                : latest.fulfillment_rate >= 25 ? '#a16207' : '#b91c1c'
            }} />
            <span className={`text-[10px] font-medium ${
              latest.fulfillment_rate >= 50 ? 'text-green-700'
                : latest.fulfillment_rate >= 25 ? 'text-yellow-700' : 'text-red-700'
            }`}>
              {latest.fulfillment_rate.toFixed(0)}% fulfilled ({latest.fulfilled_count}/{latest.total_request_threads})
            </span>
          </div>
        )}
        {latest.top_repeats.length > 0 && (
          <div className="flex items-center gap-1.5 bg-gray-50 border border-gray-200 rounded-md px-2.5 py-1">
            <span className="text-[10px] text-gray-600 font-medium">
              Top: {latest.top_repeats.join(', ')}
            </span>
          </div>
        )}
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
          Feature request ratio measures what fraction of your signals are asking for missing
          capabilities. A high ratio means the product doesn't fully fit your use case.
          Recurring requests highlight pain points the vendor hasn't addressed.
          Fulfillment rate tracks whether the vendor ships what you ask for.
        </p>
      </div>
    </div>
  );
}
