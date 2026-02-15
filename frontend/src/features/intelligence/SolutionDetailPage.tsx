import { useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts';
import { getSolutionDetail, type CUJStage } from '../../api/intelligence';
import { ArrowLeft } from 'lucide-react';

const PIE_COLORS = ['#3b82f6', '#6366f1', '#8b5cf6', '#ec4899', '#f97316', '#eab308', '#22c55e', '#14b8a6'];

function scoreColor(score: number | null) {
  if (score === null) return 'text-gray-400';
  if (score >= 80) return 'text-green-600';
  if (score >= 60) return 'text-yellow-600';
  return 'text-red-600';
}

function stageBarColor(stage: CUJStage) {
  if (stage.total === 0) return '#94a3b8';
  const ratio = stage.satisfied_count / stage.total;
  if (ratio >= 0.7) return '#22c55e';
  if (ratio >= 0.4) return '#eab308';
  return '#ef4444';
}

interface GanttRow {
  name: string;
  order: number;
  description: string;
  offset: number;
  duration: number;
  satisfied_count: number;
  dissatisfied_count: number;
  total: number;
  avg_duration_days: number;
  fill: string;
}

function buildGanttData(stages: CUJStage[]): GanttRow[] {
  // Only include stages with duration data
  const withDuration = stages.filter((s) => s.avg_duration_days && s.avg_duration_days > 0);
  if (withDuration.length === 0) return [];

  // Position stages sequentially
  let offset = 0;
  return withDuration.map((s) => {
    const row: GanttRow = {
      name: s.name,
      order: s.order,
      description: s.description,
      offset,
      duration: s.avg_duration_days!,
      satisfied_count: s.satisfied_count,
      dissatisfied_count: s.dissatisfied_count,
      total: s.total,
      avg_duration_days: s.avg_duration_days!,
      fill: stageBarColor(s),
    };
    offset += s.avg_duration_days!;
    return row;
  });
}

export function SolutionDetailPage() {
  const { vendor, software } = useParams<{ vendor: string; software: string }>();
  const navigate = useNavigate();

  const { data, isLoading, error } = useQuery({
    queryKey: ['intelligence-solution', vendor, software],
    queryFn: () => getSolutionDetail(vendor!, software!),
    enabled: !!vendor && !!software,
  });

  const ganttRows = useMemo(() => {
    if (!data?.cuj?.stages.length) return [];
    return buildGanttData(data.cuj.stages);
  }, [data]);

  if (isLoading) {
    return <div className="text-center py-12 text-gray-400 text-sm">Loading solution details...</div>;
  }

  if (error || !data) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500 mb-4">Solution not found.</p>
        <button onClick={() => navigate('/intelligence')} className="text-blue-600 hover:underline text-sm cursor-pointer">
          Back to Intelligence Index
        </button>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <button
          onClick={() => navigate('/intelligence')}
          className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 mb-3 cursor-pointer"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Index
        </button>
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{data.software_name}</h1>
            <p className="text-gray-500">{data.vendor_name}</p>
            {data.auto_category && (
              <span className="inline-block mt-2 text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full font-medium">
                {data.auto_category}
              </span>
            )}
          </div>
          <div className="text-right">
            <p className={`text-4xl font-bold ${scoreColor(data.avg_health_score)}`}>
              {data.avg_health_score ?? '--'}
            </p>
            <p className="text-xs text-gray-500 mt-1">Avg Health Score</p>
            <p className="text-sm text-gray-600 mt-1">
              {data.company_count} {data.company_count === 1 ? 'company' : 'companies'}
            </p>
          </div>
        </div>
      </div>

      {/* Distribution charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Industry distribution */}
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Industry Distribution</h2>
          {data.industry_distribution.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie
                  data={data.industry_distribution}
                  dataKey="count"
                  nameKey="label"
                  cx="50%"
                  cy="50%"
                  outerRadius={100}
                  label={({ label, count }) => `${label} (${count})`}
                >
                  {data.industry_distribution.map((_entry, idx) => (
                    <Cell key={idx} fill={PIE_COLORS[idx % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[280px] flex items-center justify-center text-gray-400 text-sm">
              No industry data available.
            </div>
          )}
        </div>

        {/* Size distribution */}
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Company Size Distribution</h2>
          {data.size_distribution.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={data.size_distribution}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="label" fontSize={12} />
                <YAxis fontSize={12} />
                <Tooltip />
                <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[280px] flex items-center justify-center text-gray-400 text-sm">
              No size data available.
            </div>
          )}
        </div>
      </div>

      {/* CUJ Gantt Chart */}
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">Critical User Journey</h2>
        {ganttRows.length > 0 ? (
          <>
            <ResponsiveContainer width="100%" height={Math.max(300, ganttRows.length * 56 + 60)}>
              <BarChart data={ganttRows} layout="vertical" barSize={20}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={180}
                  fontSize={12}
                  tick={{ fill: '#374151' }}
                />
                <XAxis
                  type="number"
                  fontSize={11}
                  label={{ value: 'Days (avg)', position: 'insideBottomRight', offset: -5, fontSize: 11, fill: '#6b7280' }}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const row = payload[0]?.payload as GanttRow;
                    return (
                      <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-3 text-sm">
                        <p className="font-semibold text-gray-900 mb-1">{row.name}</p>
                        <p className="text-gray-500 text-xs mb-2">{row.description}</p>
                        <p className="text-gray-600 text-xs mb-2">
                          Avg duration: {row.avg_duration_days} {row.avg_duration_days === 1 ? 'day' : 'days'}
                        </p>
                        <p className="text-green-600">Satisfied: {row.satisfied_count}</p>
                        <p className="text-red-600">Dissatisfied: {row.dissatisfied_count}</p>
                      </div>
                    );
                  }}
                />
                {/* Invisible offset bar */}
                <Bar dataKey="offset" stackId="gantt" fill="transparent" isAnimationActive={false} />
                {/* Visible duration bar — colored by satisfaction ratio */}
                <Bar
                  dataKey="duration"
                  stackId="gantt"
                  cursor="pointer"
                  radius={[4, 4, 4, 4]}
                  isAnimationActive={false}
                  onClick={(row: GanttRow) => {
                    navigate(
                      `/intelligence/${encodeURIComponent(data.vendor_name)}/${encodeURIComponent(data.software_name)}/drilldown/${row.order}`,
                    );
                  }}
                  shape={(props: Record<string, unknown>) => {
                    const { x, y, width, height, payload } = props as {
                      x: number; y: number; width: number; height: number; payload: GanttRow;
                    };
                    return (
                      <rect
                        x={x}
                        y={y}
                        width={Math.max(width, 4)}
                        height={height}
                        rx={4}
                        fill={payload.fill}
                        className="hover:opacity-80 transition-opacity"
                      />
                    );
                  }}
                />
              </BarChart>
            </ResponsiveContainer>
            {/* Legend */}
            <div className="flex items-center gap-4 mt-3 text-xs text-gray-500">
              <div className="flex items-center gap-1">
                <span className="inline-block w-3 h-3 rounded-sm bg-green-500" /> Mostly Satisfied
              </div>
              <div className="flex items-center gap-1">
                <span className="inline-block w-3 h-3 rounded-sm bg-yellow-500" /> Mixed
              </div>
              <div className="flex items-center gap-1">
                <span className="inline-block w-3 h-3 rounded-sm bg-red-500" /> Mostly Dissatisfied
              </div>
              <span className="ml-auto">Click a bar to drill down</span>
            </div>
          </>
        ) : data.cuj && data.cuj.stages.length > 0 ? (
          /* Fallback: stages exist but no duration data — show simple list */
          <div className="space-y-2">
            {data.cuj.stages.map((stage) => (
              <button
                key={stage.order}
                onClick={() =>
                  navigate(
                    `/intelligence/${encodeURIComponent(data.vendor_name)}/${encodeURIComponent(data.software_name)}/drilldown/${stage.order}`,
                  )
                }
                className="w-full flex items-center gap-3 p-3 rounded-lg border border-gray-100 hover:bg-gray-50 text-left cursor-pointer"
              >
                <span className="text-xs font-mono text-gray-400 w-6">{stage.order}</span>
                <div className="flex-1">
                  <p className="text-sm font-medium text-gray-900">{stage.name}</p>
                  <p className="text-xs text-gray-500">{stage.description}</p>
                </div>
                <div className="flex gap-3 text-xs">
                  <span className="text-green-600">{stage.satisfied_count} satisfied</span>
                  <span className="text-red-600">{stage.dissatisfied_count} dissatisfied</span>
                </div>
              </button>
            ))}
            <p className="text-xs text-gray-400 mt-2">
              Add dates to signals via the Demo Panel for a timeline view.
            </p>
          </div>
        ) : (
          <div className="h-[200px] flex items-center justify-center text-gray-400 text-sm">
            No CUJ data available. Rebuild the intelligence index to generate journey stages.
          </div>
        )}
      </div>
    </div>
  );
}
