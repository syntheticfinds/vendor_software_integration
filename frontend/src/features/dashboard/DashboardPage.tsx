import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, Legend,
} from 'recharts';
import { useAuthStore } from '../../stores/authStore';
import { getOverview, getSoftwareSummary, getHealthTrends, getIssueCategories, getSourceDistribution } from '../../api/analytics';
import { Activity, AlertTriangle, Package, TrendingUp, FileText, Shield, X } from 'lucide-react';

const PIE_COLORS = ['#ef4444', '#f97316', '#eab308', '#3b82f6', '#6b7280'];
const LINE_COLORS = ['#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316', '#6366f1', '#14b8a6'];

function scoreColor(score: number | null) {
  if (score === null) return 'text-gray-400';
  if (score >= 80) return 'text-green-600';
  if (score >= 60) return 'text-yellow-600';
  return 'text-red-600';
}

function scoreBg(score: number | null) {
  if (score === null) return 'bg-gray-50';
  if (score >= 80) return 'bg-green-50';
  if (score >= 60) return 'bg-yellow-50';
  return 'bg-red-50';
}

export function DashboardPage() {
  const company = useAuthStore((s) => s.company);
  const [selectedSoftwareIds, setSelectedSoftwareIds] = useState<string[]>([]);

  const filterParam = selectedSoftwareIds.length > 0 ? selectedSoftwareIds : undefined;

  const { data: softwareSummary } = useQuery({
    queryKey: ['analytics-software-summary'],
    queryFn: getSoftwareSummary,
  });

  const { data: overview } = useQuery({
    queryKey: ['analytics-overview', filterParam],
    queryFn: () => getOverview(filterParam),
  });

  const { data: healthTrends } = useQuery({
    queryKey: ['analytics-health-trends'],
    queryFn: () => getHealthTrends(30),
  });

  const { data: issueCategories } = useQuery({
    queryKey: ['analytics-issue-categories', filterParam],
    queryFn: () => getIssueCategories(filterParam),
  });

  const { data: sourceDistribution } = useQuery({
    queryKey: ['analytics-source-distribution', filterParam],
    queryFn: () => getSourceDistribution(filterParam),
  });

  // Pivot health trends into multi-line format: { date, "Software A": 85, "Software B": 72, ... }
  const { pivotedData, softwareNames } = useMemo(() => {
    if (!healthTrends?.length) return { pivotedData: [], softwareNames: [] };

    // Filter to selected software (or show all)
    const filtered = filterParam
      ? healthTrends.filter((p) => filterParam.includes(p.software_id))
      : healthTrends;

    const names = [...new Set(filtered.map((p) => p.software_name))];
    const byDate = new Map<string, Record<string, number | string>>();

    for (const point of filtered) {
      if (!byDate.has(point.date)) {
        byDate.set(point.date, { date: point.date });
      }
      byDate.get(point.date)![point.software_name] = point.score;
    }

    return {
      pivotedData: Array.from(byDate.values()).sort((a, b) =>
        (a.date as string).localeCompare(b.date as string),
      ),
      softwareNames: names,
    };
  }, [healthTrends, filterParam]);

  const toggleSoftware = (id: string) => {
    setSelectedSoftwareIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Dashboard</h1>
      <p className="text-gray-600 mb-4">
        Welcome back, {company?.company_name}. Your vendor integrations at a glance.
      </p>

      {/* Software filter chips */}
      {softwareSummary && softwareSummary.length >= 2 && (
        <div className="flex flex-wrap items-center gap-2 mb-6">
          <span className="text-xs text-gray-500 font-medium mr-1">Filter:</span>
          {softwareSummary.map((sw) => {
            const active = selectedSoftwareIds.includes(sw.software_id);
            return (
              <button
                key={sw.software_id}
                onClick={() => toggleSoftware(sw.software_id)}
                className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                  active
                    ? 'bg-blue-100 text-blue-700 border border-blue-300'
                    : 'bg-gray-100 text-gray-600 border border-gray-200 hover:bg-gray-200'
                }`}
              >
                {sw.software_name}
                {active && <X className="w-3 h-3" />}
              </button>
            );
          })}
          {selectedSoftwareIds.length > 0 && (
            <button
              onClick={() => setSelectedSoftwareIds([])}
              className="text-xs text-gray-500 hover:text-gray-700 underline ml-1"
            >
              Clear all
            </button>
          )}
        </div>
      )}

      {/* Stats cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-8">
        <StatCard
          icon={<Package className="w-5 h-5 text-blue-600" />}
          label="Software"
          value={overview?.total_software ?? 0}
        />
        <StatCard
          icon={<Shield className="w-5 h-5 text-green-600" />}
          label="Active"
          value={overview?.active_software ?? 0}
        />
        <StatCard
          icon={<Activity className="w-5 h-5 text-indigo-600" />}
          label="Signals"
          value={overview?.total_signals ?? 0}
        />
        <StatCard
          icon={<TrendingUp className="w-5 h-5 text-emerald-600" />}
          label="Avg Score"
          value={overview?.avg_health_score != null ? `${overview.avg_health_score}` : '--'}
          valueColor={scoreColor(overview?.avg_health_score ?? null)}
        />
        <StatCard
          icon={<FileText className="w-5 h-5 text-yellow-600" />}
          label="Pending Reviews"
          value={overview?.pending_reviews ?? 0}
        />
        <StatCard
          icon={<AlertTriangle className="w-5 h-5 text-red-600" />}
          label="Critical"
          value={overview?.critical_signals ?? 0}
          valueColor={overview?.critical_signals ? 'text-red-600' : undefined}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Health trends chart — multi-line per software */}
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Health Score Trends</h2>
          {pivotedData.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={pivotedData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" fontSize={12} />
                <YAxis domain={[0, 100]} fontSize={12} />
                <Tooltip />
                <Legend />
                {softwareNames.map((name, idx) => (
                  <Line
                    key={name}
                    type="monotone"
                    dataKey={name}
                    stroke={LINE_COLORS[idx % LINE_COLORS.length]}
                    strokeWidth={2}
                    dot={{ r: 3 }}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[250px] flex items-center justify-center text-gray-400 text-sm">
              No health score data yet. Run signal analysis to see trends.
            </div>
          )}
        </div>

        {/* Severity distribution pie */}
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Signal Severity Distribution</h2>
          {issueCategories && issueCategories.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie
                  data={issueCategories}
                  dataKey="count"
                  nameKey="category"
                  cx="50%"
                  cy="50%"
                  outerRadius={90}
                  label={(props) => `${(props as any).category} (${(props as any).percentage}%)`}
                >
                  {issueCategories.map((_entry, idx) => (
                    <Cell key={idx} fill={PIE_COLORS[idx % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[250px] flex items-center justify-center text-gray-400 text-sm">
              No signal data yet.
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Source distribution bar chart */}
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Signals by Source</h2>
          {sourceDistribution && sourceDistribution.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={sourceDistribution}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="source_type" fontSize={12} />
                <YAxis fontSize={12} />
                <Tooltip />
                <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[200px] flex items-center justify-center text-gray-400 text-sm">
              No source data yet.
            </div>
          )}
        </div>

        {/* Software health summary table */}
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Software Health</h2>
          {softwareSummary && softwareSummary.length > 0 ? (
            <div className="overflow-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100">
                    <th className="text-left py-2 font-medium text-gray-600">Software</th>
                    <th className="text-center py-2 font-medium text-gray-600">Score</th>
                    <th className="text-center py-2 font-medium text-gray-600">Signals</th>
                    <th className="text-center py-2 font-medium text-gray-600">Critical</th>
                  </tr>
                </thead>
                <tbody>
                  {softwareSummary.map((sw) => (
                    <tr key={sw.software_id} className="border-b border-gray-50">
                      <td className="py-2">
                        <div className="font-medium text-gray-900">{sw.software_name}</div>
                        <div className="text-xs text-gray-500">{sw.vendor_name}</div>
                      </td>
                      <td className="text-center py-2">
                        <span className={`inline-block px-2 py-0.5 rounded text-sm font-semibold ${scoreBg(sw.latest_score)} ${scoreColor(sw.latest_score)}`}>
                          {sw.latest_score ?? '--'}
                        </span>
                      </td>
                      <td className="text-center py-2 text-gray-700">{sw.signal_count}</td>
                      <td className="text-center py-2">
                        <span className={sw.critical_count > 0 ? 'text-red-600 font-semibold' : 'text-gray-400'}>
                          {sw.critical_count}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="h-[200px] flex items-center justify-center text-gray-400 text-sm">
              No software registered yet.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  valueColor,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  valueColor?: string;
}) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-xs text-gray-500 font-medium">{label}</span>
      </div>
      <p className={`text-2xl font-bold ${valueColor || 'text-gray-900'}`}>{value}</p>
    </div>
  );
}
