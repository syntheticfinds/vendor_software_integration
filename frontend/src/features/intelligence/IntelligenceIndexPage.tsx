import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getIntelligenceIndex } from '../../api/intelligence';
import { Globe, Search } from 'lucide-react';

function scoreColor(score: number | null) {
  if (score === null) return 'text-gray-400';
  if (score >= 80) return 'text-green-600';
  if (score >= 60) return 'text-yellow-600';
  return 'text-red-600';
}

function scoreBg(score: number | null) {
  if (score === null) return 'bg-gray-100';
  if (score >= 80) return 'bg-green-50';
  if (score >= 60) return 'bg-yellow-50';
  return 'bg-red-50';
}

export function IntelligenceIndexPage() {
  const navigate = useNavigate();
  const [category, setCategory] = useState<string>('');
  const [search, setSearch] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['intelligence-index', category, search],
    queryFn: () =>
      getIntelligenceIndex({
        category: category || undefined,
        search: search || undefined,
      }),
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Globe className="w-6 h-6 text-blue-600" />
            Software Intelligence Index
          </h1>
          <p className="text-gray-600 text-sm mt-1">
            Cross-company aggregated intelligence on vendor software products.
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-6">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search vendor or software..."
            className="w-full pl-9 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">All Categories</option>
          {data?.categories.map((cat) => (
            <option key={cat} value={cat}>
              {cat}
            </option>
          ))}
        </select>
      </div>

      {/* Cards grid */}
      {isLoading ? (
        <div className="text-center py-12 text-gray-400 text-sm">Loading intelligence data...</div>
      ) : !data?.items.length ? (
        <div className="text-center py-12 text-gray-400 text-sm">
          No intelligence data available yet. Data is generated automatically when reviews are sent.
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {data.items.map((item) => (
            <button
              key={`${item.vendor_name}-${item.software_name}`}
              onClick={() =>
                navigate(
                  `/intelligence/${encodeURIComponent(item.vendor_name)}/${encodeURIComponent(item.software_name)}`,
                )
              }
              className="bg-white border border-gray-200 rounded-lg p-5 text-left hover:border-blue-300 hover:shadow-sm transition-all cursor-pointer"
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="font-semibold text-gray-900">{item.software_name}</h3>
                  <p className="text-xs text-gray-500">{item.vendor_name}</p>
                </div>
                <span
                  className={`text-xl font-bold ${scoreColor(item.avg_health_score)} ${scoreBg(item.avg_health_score)} px-2 py-0.5 rounded`}
                >
                  {item.avg_health_score ?? '--'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                {item.auto_category && (
                  <span className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full font-medium">
                    {item.auto_category}
                  </span>
                )}
                <span className="text-xs text-gray-500">
                  {item.company_count} {item.company_count === 1 ? 'company' : 'companies'}
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
