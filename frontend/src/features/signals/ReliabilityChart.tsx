import { useQuery } from '@tanstack/react-query';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { getReliability } from '../../api/signals';
import { TrendingDown, TrendingUp, Minus, Info, ShieldAlert, Clock, ArrowDown } from 'lucide-react';

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
  if (hours < 1) return `${(hours * 60).toFixed(0)}m`;
  if (hours < 24) return `${hours.toFixed(1)}h`;
  const days = hours / 24;
  return days < 10 ? `${days.toFixed(1)}d` : `${days.toFixed(0)}d`;
}

interface MergedPoint {
  date: string;
  incident_count: number;
  weighted_density: number;
  mtbf_hours: number | null;
  extracted_downtime_hours: number | null;
  extracted_uptime_pct: number | null;
  extraction_count: number;
  top_incidents: string[];
  peerDensity?: number;
}

function ReliabilityTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;

  const point = payload[0]?.payload as MergedPoint | undefined;
  if (!point) return null;

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-3 shadow-md text-xs">
      <p className="font-medium text-gray-700 mb-1.5">{formatDate(label)}</p>
      <div className="space-y-1">
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">Incident density</span>
          <span className="font-medium text-blue-600">{point.weighted_density}</span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">Incident count</span>
          <span className="text-gray-700">{point.incident_count}</span>
        </div>
        {point.peerDensity !== undefined && (
          <div className="flex justify-between gap-4">
            <span className="text-gray-500">Peer avg density</span>
            <span className="text-gray-700">{point.peerDensity}</span>
          </div>
        )}
        {point.mtbf_hours !== null && (
          <div className="flex justify-between gap-4 pt-1 border-t border-gray-100">
            <span className="text-gray-500">MTBF</span>
            <span className="text-gray-700">{formatHours(point.mtbf_hours)}</span>
          </div>
        )}
        {point.extracted_downtime_hours !== null && (
          <div className="flex justify-between gap-4">
            <span className="text-gray-500">Reported downtime</span>
            <span className="text-gray-700">{formatHours(point.extracted_downtime_hours)}</span>
          </div>
        )}
        {point.extracted_uptime_pct !== null && (
          <div className="flex justify-between gap-4">
            <span className="text-gray-500">Reported uptime</span>
            <span className="text-gray-700">{point.extracted_uptime_pct}%</span>
          </div>
        )}
      </div>
      {point.top_incidents.length > 0 && (
        <div className="mt-2 pt-2 border-t border-gray-100">
          <p className="text-gray-500 mb-1">Recent incidents:</p>
          {point.top_incidents.map((title, i) => (
            <p key={i} className="text-gray-700 pl-2">
              <span className="text-blue-400 mr-1">&bull;</span>
              {title}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

export function ReliabilityChart({ softwareId }: { softwareId: string }) {
  const { data: reliability, isLoading } = useQuery({
    queryKey: ['reliability', softwareId],
    queryFn: () => getReliability(softwareId),
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

  if (!reliability || !reliability.points.length) return null;

  const peer = reliability.peer;
  const commentary = reliability.commentary;
  const trendCfg = TREND_CONFIG[commentary.trend] || TREND_CONFIG.stable;
  const TrendIcon = trendCfg.icon;

  // Merge own + peer data
  const peerMap = new Map<string, number>();
  if (peer) {
    for (const p of peer.points) {
      peerMap.set(p.date, p.count);
    }
  }

  const merged: MergedPoint[] = reliability.points.map((p) => ({
    ...p,
    ...(peer ? { peerDensity: peerMap.get(p.date) ?? 0 } : {}),
  }));

  const tickInterval = Math.max(1, Math.floor(merged.length / 8));

  const allValues = merged.flatMap((p) => [p.weighted_density, p.peerDensity ?? 0]);
  const maxVal = Math.max(...allValues, 1);

  // Latest point stats
  const latest = reliability.points[reliability.points.length - 1];

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 mb-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <ShieldAlert className="w-3.5 h-3.5 text-gray-400" />
          <p className="text-sm text-gray-500">Incident Density</p>
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
            <linearGradient id="reliabilityGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.15} />
              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
            </linearGradient>
            {peer && (
              <linearGradient id="reliabilityPeerGrad" x1="0" y1="0" x2="0" y2="1">
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
          <Tooltip content={<ReliabilityTooltip />} />
          <ReferenceLine y={0} stroke="#e5e7eb" />
          {peer && (
            <Area
              type="monotone"
              dataKey="peerDensity"
              stroke="#9ca3af"
              strokeWidth={1.5}
              strokeDasharray="4 3"
              fill="url(#reliabilityPeerGrad)"
              name="peerDensity"
              connectNulls
            />
          )}
          <Area
            type="monotone"
            dataKey="weighted_density"
            stroke="#3b82f6"
            strokeWidth={2}
            fill="url(#reliabilityGrad)"
            name="weighted_density"
            connectNulls
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-2 px-1">
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-0.5 bg-blue-500 rounded" />
          <span className="text-[10px] text-gray-500">Severity-weighted density</span>
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
          latest.incident_count > 0
            ? 'bg-red-50 border border-red-200'
            : 'bg-green-50 border border-green-200'
        }`}>
          <ShieldAlert className="w-3 h-3" style={{ color: latest.incident_count > 0 ? '#b91c1c' : '#15803d' }} />
          <span className={`text-[10px] font-medium ${
            latest.incident_count > 0 ? 'text-red-700' : 'text-green-700'
          }`}>
            {latest.incident_count} incident{latest.incident_count !== 1 ? 's' : ''}
          </span>
        </div>
        {latest.mtbf_hours !== null && (
          <div className="flex items-center gap-1.5 bg-blue-50 border border-blue-200 rounded-md px-2.5 py-1">
            <Clock className="w-3 h-3 text-blue-600" />
            <span className="text-[10px] text-blue-700 font-medium">
              MTBF: {formatHours(latest.mtbf_hours)}
            </span>
          </div>
        )}
        {latest.extracted_downtime_hours !== null && latest.extracted_downtime_hours > 0 && (
          <div className="flex items-center gap-1.5 bg-orange-50 border border-orange-200 rounded-md px-2.5 py-1">
            <ArrowDown className="w-3 h-3 text-orange-600" />
            <span className="text-[10px] text-orange-700 font-medium">
              {formatHours(latest.extracted_downtime_hours)} reported downtime
            </span>
          </div>
        )}
        {latest.extracted_uptime_pct !== null && (
          <div className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 ${
            latest.extracted_uptime_pct >= 99.9
              ? 'bg-green-50 border border-green-200'
              : latest.extracted_uptime_pct >= 99
                ? 'bg-yellow-50 border border-yellow-200'
                : 'bg-red-50 border border-red-200'
          }`}>
            <span className={`text-[10px] font-medium ${
              latest.extracted_uptime_pct >= 99.9 ? 'text-green-700'
                : latest.extracted_uptime_pct >= 99 ? 'text-yellow-700' : 'text-red-700'
            }`}>
              {latest.extracted_uptime_pct}% uptime
            </span>
          </div>
        )}
        {latest.extraction_count > 0 && (
          <div className="flex items-center gap-1.5 bg-gray-50 border border-gray-200 rounded-md px-2.5 py-1">
            <span className="text-[10px] text-gray-600 font-medium">
              {latest.extraction_count} signal{latest.extraction_count !== 1 ? 's' : ''} with quantitative data
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
          Incident density is a severity-weighted count of outage and incident signals
          (critical=4x, high=2.5x, medium=1x, low=0.3x). MTBF is the average time between
          consecutive incidents. Downtime and uptime numbers are extracted from signal text
          using AI when people mention specific figures, durations, or SLA percentages.
        </p>
      </div>
    </div>
  );
}
