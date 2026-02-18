import { useQuery } from '@tanstack/react-query';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { getCorePeripheral } from '../../api/signals';
import { TrendingDown, TrendingUp, Minus, Info, Layers } from 'lucide-react';

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
  peripheral_ratio: number;
  core_count: number;
  peripheral_count: number;
  total_count: number;
  top_peripheral_categories: string[];
  peerRatio?: number;
}

function CorePeripheralTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;

  const point = payload[0]?.payload as MergedPoint | undefined;
  if (!point) return null;

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-3 shadow-md text-xs">
      <p className="font-medium text-gray-700 mb-1.5">{formatDate(label)}</p>
      <div className="space-y-1">
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">Peripheral ratio</span>
          <span className="font-medium text-teal-600">{point.peripheral_ratio}%</span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">Core issues</span>
          <span className="text-gray-700">{point.core_count}</span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">Peripheral issues</span>
          <span className="text-gray-700">{point.peripheral_count}</span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">Total</span>
          <span className="text-gray-700">{point.total_count}</span>
        </div>
        {point.peerRatio !== undefined && (
          <div className="flex justify-between gap-4">
            <span className="text-gray-500">Peer avg</span>
            <span className="text-gray-700">{point.peerRatio}%</span>
          </div>
        )}
      </div>
      {point.top_peripheral_categories.length > 0 && (
        <div className="mt-2 pt-2 border-t border-gray-100">
          <p className="text-gray-500 mb-1">Top peripheral categories:</p>
          {point.top_peripheral_categories.map((cat, i) => (
            <p key={i} className="text-gray-700 pl-2">
              <span className="text-teal-400 mr-1">&bull;</span>
              {cat}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

export function CorePeripheralChart({ softwareId, stageTopic }: { softwareId: string; stageTopic?: string }) {
  const { data: cpData, isLoading } = useQuery({
    queryKey: ['core-peripheral', softwareId, stageTopic],
    queryFn: () => getCorePeripheral(softwareId, stageTopic),
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

  if (!cpData || !cpData.points.length) return null;

  const hasAnyData = cpData.points.some((p) => p.total_count > 0);
  if (!hasAnyData) return null;

  const peer = cpData.peer;
  const commentary = cpData.commentary;
  const trendCfg = TREND_CONFIG[commentary.trend] || TREND_CONFIG.stable;
  const TrendIcon = trendCfg.icon;

  // Merge own + peer data
  const peerMap = new Map<string, number>();
  if (peer) {
    for (const p of peer.points) {
      peerMap.set(p.date, p.count);
    }
  }

  const merged: MergedPoint[] = cpData.points.map((p) => ({
    ...p,
    ...(peer ? { peerRatio: peerMap.get(p.date) ?? 0 } : {}),
  }));

  const tickInterval = Math.max(1, Math.floor(merged.length / 8));

  const allValues = merged.flatMap((p) => [p.peripheral_ratio, p.peerRatio ?? 0]);
  const maxVal = Math.max(...allValues, 5);

  // Latest point stats
  const latest = cpData.points[cpData.points.length - 1];

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 mb-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Layers className="w-3.5 h-3.5 text-gray-400" />
          <p className="text-sm text-gray-500">Core vs Peripheral Issues</p>
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
            <linearGradient id="corePeripheralGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#14b8a6" stopOpacity={0.15} />
              <stop offset="95%" stopColor="#14b8a6" stopOpacity={0} />
            </linearGradient>
            {peer && (
              <linearGradient id="corePeripheralPeerGrad" x1="0" y1="0" x2="0" y2="1">
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
          <Tooltip content={<CorePeripheralTooltip />} />
          <ReferenceLine y={0} stroke="#e5e7eb" />
          {peer && (
            <Area
              type="monotone"
              dataKey="peerRatio"
              stroke="#9ca3af"
              strokeWidth={1.5}
              strokeDasharray="4 3"
              fill="url(#corePeripheralPeerGrad)"
              name="peerRatio"
              connectNulls
            />
          )}
          <Area
            type="monotone"
            dataKey="peripheral_ratio"
            stroke="#14b8a6"
            strokeWidth={2}
            fill="url(#corePeripheralGrad)"
            name="peripheral_ratio"
            connectNulls
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-2 px-1">
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-0.5 bg-teal-500 rounded" />
          <span className="text-[10px] text-gray-500">Peripheral ratio</span>
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
        <div className="flex items-center gap-1.5 bg-teal-50 border border-teal-200 rounded-md px-2.5 py-1">
          <span className="text-[10px] text-teal-700 font-medium">
            {latest.core_count} core issue{latest.core_count !== 1 ? 's' : ''}
          </span>
        </div>
        <div className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 ${
          latest.peripheral_count > 0
            ? 'bg-orange-50 border border-orange-200'
            : 'bg-green-50 border border-green-200'
        }`}>
          <span className={`text-[10px] font-medium ${
            latest.peripheral_count > 0 ? 'text-orange-700' : 'text-green-700'
          }`}>
            {latest.peripheral_count} peripheral issue{latest.peripheral_count !== 1 ? 's' : ''}
          </span>
        </div>
        {latest.top_peripheral_categories.length > 0 && (
          <div className="flex items-center gap-1.5 bg-gray-50 border border-gray-200 rounded-md px-2.5 py-1">
            <span className="text-[10px] text-gray-600 font-medium">
              Top: {latest.top_peripheral_categories.join(', ')}
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
          Peripheral issues (SSO, billing, access, compliance) indicate ecosystem friction
          around the integration — not the product itself. A high peripheral ratio means the
          integration works but the surrounding infrastructure doesn't. Core issues reflect
          problems directly related to the software's intended use case.
        </p>
      </div>
    </div>
  );
}
