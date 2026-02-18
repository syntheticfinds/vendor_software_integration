import { useQuery } from '@tanstack/react-query';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { getRecurrenceRate } from '../../api/signals';
import { TrendingDown, TrendingUp, Minus, Info, RefreshCw } from 'lucide-react';

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
  rate: number;
  recurring_count: number;
  total_threads: number;
  top_topics: string[];
  peerRate?: number;
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;

  const point = payload[0]?.payload as MergedPoint | undefined;
  if (!point) return null;

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-3 shadow-md text-xs">
      <p className="font-medium text-gray-700 mb-1.5">{formatDate(label)}</p>
      <div className="space-y-1">
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">Recurrence rate</span>
          <span className="font-medium text-orange-600">{point.rate}%</span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">Recurring / Total</span>
          <span className="text-gray-700">{point.recurring_count} / {point.total_threads}</span>
        </div>
        {point.peerRate !== undefined && (
          <div className="flex justify-between gap-4">
            <span className="text-gray-500">Peer avg</span>
            <span className="text-gray-700">{point.peerRate}%</span>
          </div>
        )}
      </div>
      {point.top_topics.length > 0 && (
        <div className="mt-2 pt-2 border-t border-gray-100">
          <p className="text-gray-500 mb-1">Recurring topics:</p>
          {point.top_topics.map((topic, i) => (
            <p key={i} className="text-gray-700 pl-2">
              <span className="text-orange-400 mr-1">&bull;</span>
              {topic}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

export function RecurrenceChart({ softwareId, stageTopic }: { softwareId: string; stageTopic?: string }) {
  const { data: recurrence, isLoading } = useQuery({
    queryKey: ['recurrence-rate', softwareId, stageTopic],
    queryFn: () => getRecurrenceRate(softwareId, stageTopic),
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

  if (!recurrence || !recurrence.points.length) return null;

  const { commentary, peer } = recurrence;
  const trendCfg = TREND_CONFIG[commentary.trend] || TREND_CONFIG.stable;
  const TrendIcon = trendCfg.icon;

  // Merge own and peer data
  const peerMap = new Map<string, number>();
  if (peer) {
    for (const p of peer.points) {
      peerMap.set(p.date, p.count);
    }
  }

  const merged: MergedPoint[] = recurrence.points.map((p) => ({
    ...p,
    ...(peer ? { peerRate: peerMap.get(p.date) ?? 0 } : {}),
  }));

  const tickInterval = Math.max(1, Math.floor(merged.length / 8));

  const maxRate = Math.max(
    ...merged.map((p) => Math.max(p.rate, p.peerRate ?? 0)),
    10,
  );

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 mb-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <RefreshCw className="w-3.5 h-3.5 text-gray-400" />
          <p className="text-sm text-gray-500">Issue Recurrence Rate</p>
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
            <linearGradient id="recurrenceGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#f97316" stopOpacity={0.15} />
              <stop offset="95%" stopColor="#f97316" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="recurrPeerGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#9ca3af" stopOpacity={0.1} />
              <stop offset="95%" stopColor="#9ca3af" stopOpacity={0} />
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
            allowDecimals={false}
            domain={[0, Math.ceil(maxRate * 1.2)]}
            tickFormatter={(v: number) => `${v}%`}
            tick={{ fontSize: 10, fill: '#9ca3af' }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip />} />
          <ReferenceLine y={0} stroke="#e5e7eb" />
          {peer && (
            <Area
              type="monotone"
              dataKey="peerRate"
              stroke="#9ca3af"
              strokeWidth={1.5}
              strokeDasharray="4 3"
              fill="url(#recurrPeerGrad)"
              name="peerRate"
            />
          )}
          <Area
            type="monotone"
            dataKey="rate"
            stroke="#f97316"
            strokeWidth={2}
            fill="url(#recurrenceGrad)"
            name="rate"
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-2 px-1">
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-0.5 bg-orange-500 rounded" />
          <span className="text-[10px] text-gray-500">Your recurrence rate</span>
        </div>
        {peer && (
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-0.5 bg-gray-400 rounded" style={{ borderTop: '1px dashed #9ca3af' }} />
            <span className="text-[10px] text-gray-500">Peer avg ({peer.category || 'similar use case'})</span>
          </div>
        )}
      </div>

      {/* Commentary */}
      <div className={`flex items-start gap-2 mt-3 rounded-md border p-3 ${trendCfg.bg}`}>
        <TrendIcon className={`w-4 h-4 mt-0.5 shrink-0 ${trendCfg.color}`} />
        <p className="text-sm text-gray-700">{commentary.message}</p>
      </div>

      {/* Contextual guidance */}
      <div className="flex items-start gap-2 mt-2 px-1">
        <Info className="w-3 h-3 text-gray-300 mt-0.5 shrink-0" />
        <p className="text-[10px] text-gray-400 leading-relaxed">
          Persistent recurrence on the same topic signals the vendor isn&rsquo;t fixing root causes.
          A declining recurrence rate indicates issues are being resolved permanently.
        </p>
      </div>
    </div>
  );
}
