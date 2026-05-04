/**
 * AnalysisButtons — two background-task triggers:
 *   - "Analyze My Holdings" → flow=holdings (no body)
 *   - "Today's Picks"       → flow=picks (with selected sectors)
 *
 * Each button polls /api/admin/portfolio/status/{run_id} every 3s while
 * status is pending or running, stops on done|error. Disabled until
 * settings are saved (parent passes settingsReady flag).
 */

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, AlertCircle, Briefcase, Sparkles } from "lucide-react";
import { apiClient } from "../../services/api";

interface AnalysisRun {
  run_id: "holdings" | "picks";
  status: "pending" | "running" | "done" | "error";
  started_at: string;
  finished_at: string | null;
  message: string | null;
  result_count: number | null;
  sectors: string[] | null;
}

interface SectorsResponse {
  sectors: string[];
  industries_by_sector: Record<string, string[]>;
}

async function fetchSectors(): Promise<SectorsResponse> {
  const { data } = await apiClient.get<SectorsResponse>(
    "/api/admin/portfolio/universe/sectors",
  );
  return data;
}

async function trigger(
  flow: "holdings" | "picks",
  sectors?: string[],
): Promise<AnalysisRun> {
  const url = `/api/admin/portfolio/trigger-analysis?flow=${flow}`;
  const body = flow === "picks" ? { sectors: sectors || [] } : {};
  const { data } = await apiClient.post<AnalysisRun>(url, body);
  return data;
}

async function fetchStatus(
  run_id: "holdings" | "picks",
): Promise<AnalysisRun | null> {
  try {
    const { data } = await apiClient.get<AnalysisRun>(
      `/api/admin/portfolio/status/${run_id}`,
    );
    return data;
  } catch (e: any) {
    if (e?.response?.status === 404) return null;
    throw e;
  }
}

function statusBadge(s: AnalysisRun["status"] | null) {
  if (!s) return null;
  const map: Record<string, string> = {
    pending: "bg-blue-100 text-blue-800",
    running: "bg-blue-100 text-blue-800",
    done: "bg-green-100 text-green-800",
    error: "bg-red-100 text-red-800",
  };
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${map[s]}`}
    >
      {s}
    </span>
  );
}

interface Props {
  settingsReady: boolean;
  onRunComplete?: (run_id: "holdings" | "picks") => void;
}

export function AnalysisButtons({ settingsReady, onRunComplete }: Props) {
  const qc = useQueryClient();
  const sectorsQ = useQuery({
    queryKey: ["sector-universe"],
    queryFn: fetchSectors,
    staleTime: 60 * 60 * 1000,
  });
  const sectors = sectorsQ.data?.sectors ?? [];

  const [selectedSectors, setSelectedSectors] = useState<string[]>([]);

  // Per-button polling status
  const holdingsStatusQ = useQuery({
    queryKey: ["analysis-status", "holdings"],
    queryFn: () => fetchStatus("holdings"),
    refetchInterval: (q) => {
      const d = q.state.data as AnalysisRun | null;
      return d && (d.status === "pending" || d.status === "running")
        ? 3000
        : false;
    },
    refetchOnWindowFocus: false,
  });
  const picksStatusQ = useQuery({
    queryKey: ["analysis-status", "picks"],
    queryFn: () => fetchStatus("picks"),
    refetchInterval: (q) => {
      const d = q.state.data as AnalysisRun | null;
      return d && (d.status === "pending" || d.status === "running")
        ? 3000
        : false;
    },
    refetchOnWindowFocus: false,
  });

  const triggerHoldings = useMutation({
    mutationFn: () => trigger("holdings"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["analysis-status", "holdings"] });
    },
  });
  const triggerPicks = useMutation({
    mutationFn: () => trigger("picks", selectedSectors),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["analysis-status", "picks"] });
    },
  });

  // Detect transition to done → notify parent
  const lastHoldings = holdingsStatusQ.data?.status;
  const lastPicks = picksStatusQ.data?.status;
  useEffect(() => {
    if (lastHoldings === "done") onRunComplete?.("holdings");
  }, [lastHoldings, onRunComplete]);
  useEffect(() => {
    if (lastPicks === "done") onRunComplete?.("picks");
  }, [lastPicks, onRunComplete]);

  const holdingsRunning =
    holdingsStatusQ.data?.status === "running" ||
    holdingsStatusQ.data?.status === "pending" ||
    triggerHoldings.isPending;
  const picksRunning =
    picksStatusQ.data?.status === "running" ||
    picksStatusQ.data?.status === "pending" ||
    triggerPicks.isPending;

  const toggleSector = (s: string) => {
    setSelectedSectors((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s],
    );
  };

  const disabledTip = useMemo(() => {
    if (!settingsReady) return "Save Portfolio Settings above first.";
    return "";
  }, [settingsReady]);

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 mt-4">
      <h3 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
        <Activity className="h-4 w-4" />
        AI Analysis
      </h3>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* ---- Holdings ---- */}
        <div className="border border-gray-200 rounded p-3">
          <div className="flex items-center gap-2 mb-2">
            <Briefcase className="h-4 w-4 text-gray-700" />
            <h4 className="text-sm font-medium text-gray-900">
              Analyze My Holdings
            </h4>
          </div>
          <p className="text-xs text-gray-500 mb-3">
            Get a BUY / SELL / HOLD recommendation for each position you
            currently own.
          </p>
          <button
            disabled={!settingsReady || holdingsRunning}
            onClick={() => triggerHoldings.mutate()}
            title={disabledTip}
            className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-blue-300"
          >
            {holdingsRunning ? "Analyzing…" : "Analyze My Holdings"}
          </button>
          {holdingsStatusQ.data && (
            <p className="mt-2 text-xs text-gray-600 flex items-center gap-2">
              {statusBadge(holdingsStatusQ.data.status)}
              <span>{holdingsStatusQ.data.message ?? ""}</span>
            </p>
          )}
        </div>

        {/* ---- Picks ---- */}
        <div className="border border-gray-200 rounded p-3">
          <div className="flex items-center gap-2 mb-2">
            <Sparkles className="h-4 w-4 text-gray-700" />
            <h4 className="text-sm font-medium text-gray-900">
              Today's Picks
            </h4>
          </div>
          <p className="text-xs text-gray-500 mb-2">
            Top 5 BUY recommendations from sectors you choose
            (S&P 500 + Nasdaq 100 universe).
          </p>

          {sectorsQ.isLoading && (
            <p className="text-xs text-gray-500">Loading sectors…</p>
          )}
          {sectors.length > 0 && (
            <div className="flex flex-wrap gap-1 mb-2">
              {sectors.map((s) => {
                const on = selectedSectors.includes(s);
                return (
                  <button
                    key={s}
                    onClick={() => toggleSector(s)}
                    className={`text-xs rounded px-2 py-0.5 border ${on ? "bg-blue-600 text-white border-blue-600" : "bg-white text-gray-700 border-gray-300 hover:bg-gray-50"}`}
                  >
                    {s}
                  </button>
                );
              })}
            </div>
          )}

          <button
            disabled={
              !settingsReady || picksRunning || selectedSectors.length === 0
            }
            onClick={() => triggerPicks.mutate()}
            title={
              !settingsReady
                ? disabledTip
                : selectedSectors.length === 0
                  ? "Pick at least one sector."
                  : ""
            }
            className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-blue-300"
          >
            {picksRunning
              ? "Picking…"
              : `Today's Picks${selectedSectors.length ? ` (${selectedSectors.length} sector${selectedSectors.length > 1 ? "s" : ""})` : ""}`}
          </button>
          {picksStatusQ.data && (
            <p className="mt-2 text-xs text-gray-600 flex items-center gap-2">
              {statusBadge(picksStatusQ.data.status)}
              <span>{picksStatusQ.data.message ?? ""}</span>
            </p>
          )}
        </div>
      </div>

      {(triggerHoldings.error || triggerPicks.error) && (
        <p className="mt-3 text-xs text-red-600 flex items-center gap-1">
          <AlertCircle className="h-3 w-3" />
          {((triggerHoldings.error || triggerPicks.error) as Error)?.message}
        </p>
      )}
    </div>
  );
}
