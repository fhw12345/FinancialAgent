/**
 * Admin Health Dashboard - System monitoring and database statistics
 */

import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { authStorage } from "../services/authService";
import { formatTimestamp } from "../utils/timeFormatter";

const API_BASE_URL = import.meta.env.VITE_API_URL || "";

interface DatabaseStat {
  collection: string;
  document_count: number;
  size_bytes: number;
  size_mb: number;
  avg_document_size_bytes: number;
}

interface PodMetric {
  name: string;
  cpu_usage: string;
  memory_usage: string;
  cpu_percentage: number;
  memory_percentage: number;
  node_name?: string | null;
  node_pool?: string | null;
  cpu_request?: string | null;
  cpu_limit?: string | null;
  memory_request?: string | null;
  memory_limit?: string | null;
}

interface NodeMetric {
  name: string;
  cpu_usage: string;
  memory_usage: string;
  cpu_capacity: string;
  memory_capacity: string;
  cpu_percentage: number;
  memory_percentage: number;
}

interface SystemMetrics {
  timestamp: string;
  database: DatabaseStat[];
  pods: PodMetric[] | null;
  nodes: NodeMetric[] | null;
  health_status: string;
  kubernetes_available: boolean;
}


// Mock data for local development when K8s is not available
const mockPods: PodMetric[] = [
  {
    name: "backend-7d4f8b9c5-abc12",
    cpu_usage: "150m",
    memory_usage: "256Mi",
    cpu_percentage: 15,
    memory_percentage: 25,
  },
  {
    name: "frontend-6c8a7d5b4-def34",
    cpu_usage: "80m",
    memory_usage: "128Mi",
    cpu_percentage: 8,
    memory_percentage: 12,
  },
  {
    name: "redis-5b9c8d7a6-ghi56",
    cpu_usage: "50m",
    memory_usage: "96Mi",
    cpu_percentage: 5,
    memory_percentage: 9,
  },
];

const mockNodes: NodeMetric[] = [
  {
    name: "aks-nodepool1-12345678-vmss000000",
    cpu_usage: "1200m",
    memory_usage: "3.2Gi",
    cpu_capacity: "4000m",
    memory_capacity: "8Gi",
    cpu_percentage: 30,
    memory_percentage: 40,
  },
  {
    name: "aks-nodepool1-12345678-vmss000001",
    cpu_usage: "800m",
    memory_usage: "2.1Gi",
    cpu_capacity: "4000m",
    memory_capacity: "8Gi",
    cpu_percentage: 20,
    memory_percentage: 26,
  },
];

export default function HealthPage() {
  const { i18n } = useTranslation();
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMetrics = async () => {
    try {
      const token = authStorage.getAccessToken();
      if (!token) {
        setError("Not authenticated");
        setLoading(false);
        return;
      }

      const response = await fetch(`${API_BASE_URL}/api/admin/health`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        if (response.status === 403) {
          throw new Error("Admin access required");
        }
        throw new Error("Failed to fetch system metrics");
      }

      const data = await response.json();

      // Use mock data for local dev when K8s is not available
      if (!data.kubernetes_available) {
        data.pods = mockPods;
        data.nodes = mockNodes;
      }

      setMetrics(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchMetrics();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl">Loading system metrics...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-red-600 text-xl">Error: {error}</div>
      </div>
    );
  }

  if (!metrics) {
    return null;
  }

  const formatBytes = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

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
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-xl font-bold bg-gradient-to-r from-gray-900 via-blue-900 to-indigo-900 bg-clip-text text-transparent mb-2">
            System Health Dashboard
          </h1>
          <p className="text-gray-600">
            Last updated: {formatTimestamp(metrics.timestamp, i18n.language)}
          </p>
        </div>

        {/* Health Status */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <div className="flex items-center gap-4">
            <div
              className={`w-4 h-4 rounded-full ${
                metrics.health_status === "healthy"
                  ? "bg-green-500"
                  : "bg-yellow-500"
              }`}
            ></div>
            <div>
              <h2 className="text-xl font-semibold">
                Status: {metrics.health_status.toUpperCase()}
              </h2>
              {!metrics.kubernetes_available && (
                <p className="text-sm text-orange-600 mt-1">
                  ⚠️ Kubernetes metrics unavailable - showing mock data for
                  local development
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Kubernetes Pod Metrics */}
        {metrics.pods && metrics.pods.length > 0 && (
          <div className="mb-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              Pod Resource Usage
              {!metrics.kubernetes_available && (
                <span className="ml-2 text-sm font-normal text-orange-600">
                  (Mock Data - Local Dev)
                </span>
              )}
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {metrics.pods.map((pod) => (
                <div
                  key={pod.name}
                  className="bg-white rounded-lg shadow p-4 border-l-4 border-blue-500"
                >
                  <h3 className="text-sm font-mono text-gray-700 mb-3 truncate">
                    {pod.name}
                  </h3>

                  {/* Usage Metrics */}
                  <div className="space-y-2 mb-3">
                    <div>
                      <div className="flex justify-between text-xs text-gray-600 mb-1">
                        <span>CPU: {pod.cpu_usage}</span>
                        <span>{pod.cpu_percentage}%</span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2">
                        <div
                          className={`h-2 rounded-full ${
                            pod.cpu_percentage > 70
                              ? "bg-red-500"
                              : pod.cpu_percentage > 50
                                ? "bg-yellow-500"
                                : "bg-green-500"
                          }`}
                          style={{ width: `${pod.cpu_percentage}%` }}
                        ></div>
                      </div>
                    </div>
                    <div>
                      <div className="flex justify-between text-xs text-gray-600 mb-1">
                        <span>Memory: {pod.memory_usage}</span>
                        <span>{pod.memory_percentage}%</span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2">
                        <div
                          className={`h-2 rounded-full ${
                            pod.memory_percentage > 70
                              ? "bg-red-500"
                              : pod.memory_percentage > 50
                                ? "bg-yellow-500"
                                : "bg-green-500"
                          }`}
                          style={{ width: `${pod.memory_percentage}%` }}
                        ></div>
                      </div>
                    </div>
                  </div>

                  {/* Kubernetes Metadata */}
                  {(pod.node_name || pod.node_pool || pod.cpu_request) && (
                    <div className="border-t border-gray-200 pt-3 space-y-2">
                      {/* Node Pool - Highlighted */}
                      {pod.node_pool && (
                        <div className="flex justify-between items-center px-2 py-1 bg-gradient-to-r from-blue-50 to-indigo-50 rounded border border-blue-200">
                          <span className="text-xs font-medium text-gray-600">Node Pool:</span>
                          <span className="text-xs font-bold text-blue-700">{pod.node_pool}</span>
                        </div>
                      )}

                      {/* Node Name */}
                      {pod.node_name && (
                        <div className="flex justify-between items-center px-2 py-1 bg-gray-50 rounded">
                          <span className="text-xs text-gray-600">Node:</span>
                          <span className="text-xs font-mono text-gray-700 truncate max-w-[200px]" title={pod.node_name}>
                            {pod.node_name}
                          </span>
                        </div>
                      )}

                      {/* Resource Requests/Limits */}
                      {(pod.cpu_request || pod.memory_request) && (
                        <div className="grid grid-cols-2 gap-1 text-xs">
                          {pod.cpu_request && (
                            <div className="px-2 py-1 bg-green-50 rounded">
                              <div className="text-gray-600">CPU Req:</div>
                              <div className="font-mono text-gray-700">{pod.cpu_request}</div>
                            </div>
                          )}
                          {pod.cpu_limit && (
                            <div className="px-2 py-1 bg-green-50 rounded">
                              <div className="text-gray-600">CPU Lim:</div>
                              <div className="font-mono text-gray-700">{pod.cpu_limit}</div>
                            </div>
                          )}
                          {pod.memory_request && (
                            <div className="px-2 py-1 bg-green-50 rounded">
                              <div className="text-gray-600">Mem Req:</div>
                              <div className="font-mono text-gray-700">{pod.memory_request}</div>
                            </div>
                          )}
                          {pod.memory_limit && (
                            <div className="px-2 py-1 bg-green-50 rounded">
                              <div className="text-gray-600">Mem Lim:</div>
                              <div className="font-mono text-gray-700">{pod.memory_limit}</div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Kubernetes Node Metrics */}
        {metrics.nodes && metrics.nodes.length > 0 && (
          <div className="mb-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              Node Resource Usage
              {!metrics.kubernetes_available && (
                <span className="ml-2 text-sm font-normal text-orange-600">
                  (Mock Data - Local Dev)
                </span>
              )}
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {metrics.nodes.map((node) => (
                <div
                  key={node.name}
                  className="bg-white rounded-lg shadow p-5 border-l-4 border-indigo-500"
                >
                  <h3 className="text-sm font-mono text-gray-700 mb-3 truncate">
                    {node.name}
                  </h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs text-gray-500 mb-1">CPU</p>
                      <p className="text-lg font-bold text-gray-900">
                        {node.cpu_percentage}%
                      </p>
                      <p className="text-xs text-gray-600">
                        {node.cpu_usage} / {node.cpu_capacity}
                      </p>
                      <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
                        <div
                          className={`h-2 rounded-full ${
                            node.cpu_percentage > 70
                              ? "bg-red-500"
                              : node.cpu_percentage > 50
                                ? "bg-yellow-500"
                                : "bg-green-500"
                          }`}
                          style={{ width: `${node.cpu_percentage}%` }}
                        ></div>
                      </div>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500 mb-1">Memory</p>
                      <p className="text-lg font-bold text-gray-900">
                        {node.memory_percentage}%
                      </p>
                      <p className="text-xs text-gray-600">
                        {node.memory_usage} / {node.memory_capacity}
                      </p>
                      <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
                        <div
                          className={`h-2 rounded-full ${
                            node.memory_percentage > 70
                              ? "bg-red-500"
                              : node.memory_percentage > 50
                                ? "bg-yellow-500"
                                : "bg-green-500"
                          }`}
                          style={{ width: `${node.memory_percentage}%` }}
                        ></div>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Database Summary */}
        <div className="mb-6">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">
            Database Overview
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-white rounded-lg shadow p-6">
              <h3 className="text-sm font-medium text-gray-500 mb-2">
                Total Collections
              </h3>
              <p className="text-3xl font-bold text-gray-900">
                {metrics.database.length}
              </p>
            </div>
            <div className="bg-white rounded-lg shadow p-6">
              <h3 className="text-sm font-medium text-gray-500 mb-2">
                Total Documents
              </h3>
              <p className="text-3xl font-bold text-gray-900">
                {totalDocuments.toLocaleString()}
              </p>
            </div>
            <div className="bg-white rounded-lg shadow p-6">
              <h3 className="text-sm font-medium text-gray-500 mb-2">
                Total Size
              </h3>
              <p className="text-3xl font-bold text-gray-900">
                {totalSize.toFixed(2)} MB
              </p>
            </div>
          </div>
        </div>

        {/* Database Collections Table */}
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200">
            <h2 className="text-xl font-semibold text-gray-900">
              Database Collections
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Collection
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Documents
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Size (MB)
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Avg Doc Size
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {metrics.database.map((stat) => (
                  <tr key={stat.collection} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 font-mono">
                      {stat.collection}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 text-right">
                      {stat.document_count.toLocaleString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 text-right">
                      {stat.size_mb.toFixed(2)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 text-right">
                      {formatBytes(stat.avg_document_size_bytes)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
