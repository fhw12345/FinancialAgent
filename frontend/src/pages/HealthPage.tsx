import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { formatTimestamp } from "../utils/timeFormatter";

const API_BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

interface DatabaseStat {
  collection: string;
  document_count: number;
  size_bytes: number;
  size_mb: number;
  avg_document_size_bytes: number;
}

interface SystemMetrics {
  timestamp: string;
  database: DatabaseStat[];
  health_status: string;
}

interface BackendHealth {
  status: "ok" | "degraded";
  version: string;
}

export default function HealthPage() {
  const { i18n } = useTranslation();
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [backendHealth, setBackendHealth] = useState<BackendHealth | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const [metricsResponse, healthResponse] = await Promise.all([
          fetch(`${API_BASE_URL}/api/admin/health`),
          fetch(`${API_BASE_URL}/api/health`),
        ]);
        if (!metricsResponse.ok || !healthResponse.ok) {
          throw new Error("Failed to fetch system metrics");
        }
        const metricsPayload = (await metricsResponse.json()) as SystemMetrics;
        const healthPayload = (await healthResponse.json()) as BackendHealth;
        setMetrics(metricsPayload);
        setBackendHealth(healthPayload);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      }
    };

    void fetchMetrics();
  }, []);

  if (error) {
    return <div className="p-8 text-red-600">Error: {error}</div>;
  }

  if (!metrics || !backendHealth) {
    return <div className="p-8 text-gray-500">Loading system metrics...</div>;
  }

  const totalDocuments = metrics.database.reduce(
    (sum, stat) => sum + stat.document_count,
    0,
  );
  const totalSize = metrics.database.reduce(
    (sum, stat) => sum + stat.size_mb,
    0,
  );

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        <div>
          <h1 className="text-xl font-bold text-gray-900">System Health</h1>
          <p className="text-sm text-gray-500">
            Updated {formatTimestamp(metrics.timestamp, i18n.language)}
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <MetricCard
            label="Status"
            value={metrics.health_status.toUpperCase()}
          />
          <MetricCard
            label="Documents"
            value={totalDocuments.toLocaleString()}
          />
          <MetricCard
            label="Database size"
            value={`${totalSize.toFixed(2)} MB`}
          />
          <MetricCard label="Frontend" value={`v${__APP_VERSION__}`} />
          <MetricCard label="Backend" value={`v${backendHealth.version}`} />
        </div>

        <div className="overflow-hidden rounded-lg bg-white shadow">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-600">
                  Collection
                </th>
                <th className="px-4 py-3 text-right font-medium text-gray-600">
                  Documents
                </th>
                <th className="px-4 py-3 text-right font-medium text-gray-600">
                  Size
                </th>
                <th className="px-4 py-3 text-right font-medium text-gray-600">
                  Average document
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {metrics.database.map((stat) => (
                <tr key={stat.collection}>
                  <td className="px-4 py-3 font-mono text-gray-900">
                    {stat.collection}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {stat.document_count.toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {stat.size_mb.toFixed(2)} MB
                  </td>
                  <td className="px-4 py-3 text-right">
                    {stat.avg_document_size_bytes.toLocaleString()} B
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-white p-5 shadow">
      <p className="text-sm text-gray-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-gray-900">{value}</p>
    </div>
  );
}
