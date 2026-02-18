import { useQuery } from '@tanstack/react-query';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { getVendorResponsiveness } from '../../api/signals';
import { TrendingDown, TrendingUp, Minus, Info, Mail } from 'lucide-react';

const TREND_CONFIG: Record<string, { icon: typeof TrendingUp; color: string; bg: string }> = {
  improving: { icon: TrendingDown, color: 'text-green-600', bg: 'bg-green-50 border-green-200' },
  worsening: { icon: TrendingUp, color: 'text-red-600', bg: 'bg-red-50 border-red-200' },
  stable: { icon: Minus, color: 'text-blue-600', bg: 'bg-blue-50 border-blue-200' },
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
  median_lag_hours: number | null;
  p90_lag_hours: number | null;
  response_count: number;
  proactive_count: number;
  unanswered_count: number;
  peerMedian?: number | null;
}

function ResponsivenessTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;

  const point = payload[0]?.payload as MergedPoint | undefined;
  if (!point) return null;

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-3 shadow-md text-xs">
      <p className="font-medium text-gray-700 mb-1.5">{formatDate(label)}</p>
      <div className="space-y-1">
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">Median lag</span>
          <span className="font-medium">{formatHours(point.median_lag_hours)}</span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">P90 lag</span>
          <span className="font-medium">{formatHours(point.p90_lag_hours)}</span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">Responses</span>
          <span className="text-gray-700">{point.response_count} pair{point.response_count !== 1 ? 's' : ''}</span>
        </div>
        {point.proactive_count > 0 && (
          <div className="flex justify-between gap-4">
            <span className="text-gray-500">Proactive</span>
            <span className="text-green-600">{point.proactive_count}</span>
          </div>
        )}
        {point.unanswered_count > 0 && (
          <div className="flex justify-between gap-4">
            <span className="text-gray-500">Unanswered</span>
            <span className="text-orange-600">{point.unanswered_count}</span>
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

export function ResponsivenessChart({ softwareId }: { softwareId: string }) {
  const { data: resp, isLoading } = useQuery({
    queryKey: ['vendor-responsiveness', softwareId],
    queryFn: () => getVendorResponsiveness(softwareId),
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

  if (!resp || !resp.points.length) return null;

  const hasAnyData = resp.points.some((p) => p.median_lag_hours !== null);
  if (!hasAnyData) return null;

  const peer = resp.peer;
  const commentary = resp.commentary;
  const trendCfg = TREND_CONFIG[commentary.trend] || TREND_CONFIG.stable;
  const TrendIcon = trendCfg.icon;

  // Merge own + peer data
  const peerMap = new Map<string, number | null>();
  if (peer) {
    for (const p of peer.points) {
      peerMap.set(p.date, p.median_lag_hours);
    }
  }

  const merged: MergedPoint[] = resp.points.map((p) => ({
    ...p,
    ...(peer ? { peerMedian: peerMap.get(p.date) ?? null } : {}),
  }));

  const tickInterval = Math.max(1, Math.floor(merged.length / 8));

  const allValues = merged.flatMap((p) => [
    p.median_lag_hours, p.p90_lag_hours, p.peerMedian ?? null,
  ]).filter((v): v is number => v !== null && v !== undefined);
  const maxVal = Math.max(...allValues, 1);

  // Latest point stats
  const latest = resp.points[resp.points.length - 1];

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 mb-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Mail className="w-3.5 h-3.5 text-gray-400" />
          <p className="text-sm text-gray-500">Vendor Responsiveness</p>
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
        <AreaChart data={merged} margin={{ top: 4, right: 4, bottom: 0, left: -10 }}>
          <defs>
            <linearGradient id="responsivenessGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#6366f1" stopOpacity={0.12} />
              <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
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
          <Tooltip content={<ResponsivenessTooltip />} />
          <ReferenceLine y={0} stroke="#e5e7eb" />
          {peer && (
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
            dataKey="p90_lag_hours"
            stroke="#6366f1"
            strokeWidth={1}
            strokeDasharray="3 2"
            strokeOpacity={0.4}
            fill="none"
            name="p90_lag_hours"
            connectNulls
          />
          <Area
            type="monotone"
            dataKey="median_lag_hours"
            stroke="#6366f1"
            strokeWidth={2}
            fill="url(#responsivenessGrad)"
            name="median_lag_hours"
            connectNulls
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-1 px-1">
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-0.5 rounded" style={{ backgroundColor: '#6366f1' }} />
          <span className="text-[10px] text-gray-500">Median</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-0.5 rounded" style={{ backgroundColor: '#6366f1', opacity: 0.4 }} />
          <span className="text-[10px] text-gray-500">P90</span>
        </div>
        {peer && (
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-0.5 bg-gray-400 rounded" style={{ borderTop: '1px dashed #9ca3af' }} />
            <span className="text-[10px] text-gray-500">Peer median ({peer.category || 'similar use case'})</span>
          </div>
        )}
      </div>

      {/* Sub-stats badges */}
      <div className="flex items-center gap-3 mt-3">
        <div className="flex items-center gap-1.5 bg-green-50 border border-green-200 rounded-md px-2.5 py-1">
          <span className="text-[10px] text-green-700 font-medium">
            {latest.proactive_count} proactive update{latest.proactive_count !== 1 ? 's' : ''}
          </span>
        </div>
        {latest.unanswered_count > 0 ? (
          <div className="flex items-center gap-1.5 bg-orange-50 border border-orange-200 rounded-md px-2.5 py-1">
            <span className="text-[10px] text-orange-700 font-medium">
              {latest.unanswered_count} awaiting reply
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-1.5 bg-green-50 border border-green-200 rounded-md px-2.5 py-1">
            <span className="text-[10px] text-green-700 font-medium">
              0 unanswered
            </span>
          </div>
        )}
      </div>

      {/* Commentary */}
      <div className={`flex items-start gap-2 mt-3 rounded-md border p-2.5 ${trendCfg.bg}`}>
        <TrendIcon className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${trendCfg.color}`} />
        <p className="text-xs text-gray-700">{commentary.message}</p>
      </div>

      {/* Guidance */}
      <div className="flex items-start gap-2 mt-2 px-1">
        <Info className="w-3 h-3 text-gray-300 mt-0.5 shrink-0" />
        <p className="text-[10px] text-gray-400 leading-relaxed">
          Response lag measures how quickly the vendor replies after you reach out.
          High lag means you're chasing them. Proactive inbound communications
          (maintenance notices, roadmap updates) are a positive sign of vendor engagement.
        </p>
      </div>
    </div>
  );
}
