import { useState } from "react";
import { AlertCircle, CheckCircle, RefreshCw } from "lucide-react";

const API_BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export function AnalysisRunner() {
  const [isTriggering, setIsTriggering] = useState(false);
  const [status, setStatus] = useState<{
    type: "success" | "error" | null;
    message: string;
  }>({ type: null, message: "" });

  const handleRun = async () => {
    setIsTriggering(true);
    setStatus({ type: null, message: "" });

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/admin/portfolio/trigger-analysis`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
        },
      );
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Failed to trigger analysis");
      }

      setStatus({
        type: "success",
        message: `Analysis started. Run ID: ${data.run_id}`,
      });
    } catch (error) {
      setStatus({
        type: "error",
        message: error instanceof Error ? error.message : "Unknown error",
      });
    } finally {
      setIsTriggering(false);
    }
  };

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-lg">
      <div className="mb-4 flex items-center gap-2">
        <RefreshCw className="h-5 w-5 text-blue-600" />
        <h3 className="text-lg font-semibold text-gray-900">
          Manual Portfolio Analysis
        </h3>
      </div>

      <p className="mb-4 text-sm text-gray-600">
        Run the local research and decision pipeline now. Results are saved as
        analysis and order suggestions; no broker order is submitted.
      </p>

      <button
        onClick={handleRun}
        disabled={isTriggering}
        className="w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isTriggering ? "Starting..." : "Run Analysis"}
      </button>

      {status.type && (
        <div
          className={`mt-3 flex items-start gap-2 rounded-lg border p-3 ${
            status.type === "success"
              ? "border-green-200 bg-green-50 text-green-800"
              : "border-red-200 bg-red-50 text-red-800"
          }`}
        >
          {status.type === "success" ? (
            <CheckCircle className="mt-0.5 h-5 w-5 flex-shrink-0" />
          ) : (
            <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0" />
          )}
          <p className="text-sm">{status.message}</p>
        </div>
      )}
    </div>
  );
}
