import { useQuery } from '@tanstack/react-query';
import { getPublicIndex } from '../../api/portal';
import { Globe, TrendingUp } from 'lucide-react';

function scoreColor(score: number | null) {
  if (score === null) return 'text-gray-400';
  if (score >= 80) return 'text-green-600';
  if (score >= 60) return 'text-yellow-600';
  return 'text-red-600';
}

export function PublicIndexPage() {
  const { data: software, isLoading } = useQuery({
    queryKey: ['public-index'],
    queryFn: getPublicIndex,
  });

  return (
    <div className="max-w-4xl mx-auto py-8 px-6">
      <div className="flex items-center gap-3 mb-2">
        <Globe className="w-7 h-7 text-blue-600" />
        <h1 className="text-2xl font-bold text-gray-900">Software Intelligence Index</h1>
      </div>
      <p className="text-gray-600 mb-8">
        Aggregated health data from real-world vendor integrations. Data is anonymized and
        only shown when reported by 5+ companies.
      </p>

      {isLoading ? (
        <div className="text-center py-12 text-gray-500">Loading index...</div>
      ) : !software?.length ? (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
          <TrendingUp className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500">
            The public index is empty. Not enough companies are using the same software to
            meet our k-anonymity threshold yet.
          </p>
        </div>
      ) : (
        <div className="grid gap-4">
          {software.map((sw) => (
            <div key={sw.id} className="bg-white rounded-lg border border-gray-200 p-5 flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-gray-900">{sw.software_name}</h3>
                <p className="text-sm text-gray-500">by {sw.vendor_name}</p>
                {sw.common_issues && (
                  <p className="text-xs text-gray-400 mt-1">{sw.common_issues}</p>
                )}
              </div>
              <div className="text-right">
                <p className={`text-2xl font-bold ${scoreColor(sw.avg_health_score)}`}>
                  {sw.avg_health_score ?? '--'}
                </p>
                <p className="text-xs text-gray-500">{sw.company_count} companies</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
