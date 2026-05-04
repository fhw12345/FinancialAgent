/**
 * Decision Tracker — table + per-symbol P&L line chart.
 *
 * Surfaces every AI decision (BUY/SELL orders + HOLD signals + Deep ReAct
 * verdicts) with ex-post P&L snapshots at 7d / 30d / 90d horizons computed
 * by the run_pnl_snapshots.py cron.
 *
 * Visual style matches RecentTransactions (light theme, white card, gray-200
 * borders, gray-900 text on white) so it sits naturally on the dashboard.
 */

import { useMemo, useState, Fragment } from "react";
import {
  ArrowUpCircle,
  ArrowDownCircle,
  CircleDot,
  Activity,
} from "lucide-react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useDecisions, type DecisionRow } from "../../hooks/useDecisions";

const HORIZONS = ["7d", "30d", "90d"] as const;
type Horizon = (typeof HORIZONS)[number];

function PnlCell({ pct }: { pct: number | undefined }) {
  if (pct === undefined || pct === null) {
    return <span className="text-gray-400">—</span>;
  }
  const cls =
    pct > 0
      ? "text-green-700 font-medium"
      : pct < 0
        ? "text-red-700 font-medium"
        : "text-gray-600";
  const sign = pct > 0 ? "+" : "";
  return (
    <span className={cls}>
      {sign}
      {pct.toFixed(2)}%
    </span>
  );
}

function SideBadge({ side }: { side: DecisionRow["side"] }) {
  const map = {
    buy: {
      Icon: ArrowUpCircle,
      cls: "bg-green-100 text-green-800",
      label: "BUY",
    },
    sell: {
      Icon: ArrowDownCircle,
      cls: "bg-red-100 text-red-800",
      label: "SELL",
    },
    hold: {
      Icon: CircleDot,
      cls: "bg-yellow-100 text-yellow-800",
      label: "HOLD",
    },
  } as const;
  const { Icon, cls, label } = map[side] ?? map.hold;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium ${cls}`}
    >
      <Icon className="h-3 w-3" />
      {label}
    </span>
  );
}

interface SeriesPoint {
  horizon: Horizon;
  [symbol: string]: number | string;
}

function buildSeries(decisions: DecisionRow[]): {
  data: SeriesPoint[];
  symbols: string[];
} {
  // Latest decision per symbol (decisions arrive newest-first from API).
  const latestBySymbol = new Map<string, DecisionRow>();
  for (const d of decisions) {
    if (!latestBySymbol.has(d.symbol)) latestBySymbol.set(d.symbol, d);
  }
  const symbols = Array.from(latestBySymbol.keys());
  const data: SeriesPoint[] = HORIZONS.map((h) => {
    const point: SeriesPoint = { horizon: h };
    for (const sym of symbols) {
      const snap = latestBySymbol.get(sym)?.pnl_snapshots?.[h];
      if (snap?.pnl_pct !== undefined) {
        point[sym] = snap.pnl_pct;
      }
    }
    return point;
  });
  return { data, symbols };
}

const PALETTE = [
  "#059669", // emerald-600
  "#2563eb", // blue-600
  "#d97706", // amber-600
  "#db2777", // pink-600
  "#7c3aed", // violet-600
  "#0891b2", // cyan-600
  "#dc2626", // red-600
  "#ea580c", // orange-600
];

type SourceTab = "all" | "holdings" | "picks";

interface ResearchModalState {
  symbol: string;
  text: string;
}

export function DecisionTracker() {
  const [symbolFilter, setSymbolFilter] = useState("");
  const [tab, setTab] = useState<SourceTab>("all");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [researchModal, setResearchModal] = useState<ResearchModalState | null>(null);
  const { data, isLoading, error } = useDecisions(
    symbolFilter || undefined,
    tab === "all" ? undefined : tab,
    100,
  );

  const decisions = data?.decisions ?? [];
  const { data: chartData, symbols: chartSymbols } = useMemo(
    () => buildSeries(decisions),
    [decisions],
  );

  const toggleExpanded = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const showChart =
    chartSymbols.length > 0 &&
    chartData.some((p) => chartSymbols.some((s) => typeof p[s] === "number"));

  return (
    <div className="bg-white rounded-lg border border-gray-200 mt-6">
      <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
          <Activity className="h-4 w-4" />
          Decision Tracker
          <span className="text-xs font-normal text-gray-500">
            (was the AI right? marks at 7d / 30d / 90d)
          </span>
        </h3>
        <input
          type="text"
          placeholder="Filter symbol…"
          value={symbolFilter}
          onChange={(e) => setSymbolFilter(e.target.value.toUpperCase())}
          className="rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-900 placeholder-gray-400 focus:border-blue-500 focus:outline-none"
        />
      </div>

      <div className="px-4 pt-3 border-b border-gray-200">
        <div className="flex gap-1">
          {(["all", "holdings", "picks"] as SourceTab[]).map((t) => {
            const active = tab === t;
            const label =
              t === "all"
                ? "All"
                : t === "holdings"
                  ? "Holdings Analysis"
                  : "Today's Picks";
            return (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-3 py-1.5 text-xs font-medium rounded-t border-b-2 ${active ? "border-blue-600 text-blue-600" : "border-transparent text-gray-500 hover:text-gray-800"}`}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="p-4">
        {isLoading && (
          <div className="text-sm text-gray-500">Loading decisions…</div>
        )}
        {error && (
          <div className="text-sm text-red-600">
            Failed to load decisions: {(error as Error).message}
          </div>
        )}

        {!isLoading && !error && decisions.length === 0 && (
          <div className="text-sm text-gray-500">
            No AI decisions tracked yet. Run a portfolio analysis or a Deep
            ReAct chat to populate this table; P&L snapshots fill in 7+ days
            later.
          </div>
        )}

        {!isLoading && decisions.length > 0 && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase text-gray-500 border-b border-gray-200">
                    <th className="py-2 pr-3 w-6"></th>
                    <th className="py-2 pr-3">Symbol</th>
                    <th className="py-2 pr-3">Side</th>
                    <th className="py-2 pr-3">Decision $</th>
                    <th className="py-2 pr-3">Conf</th>
                    <th className="py-2 pr-3">7d</th>
                    <th className="py-2 pr-3">30d</th>
                    <th className="py-2 pr-3">90d</th>
                    <th className="py-2 pr-3">Date</th>
                    <th className="py-2 pr-3">Type</th>
                  </tr>
                </thead>
                <tbody>
                  {decisions.map((d) => {
                    const reasoning = d.metadata?.reasoning ?? "";
                    const conf = d.metadata?.confidence;
                    const isOpen = expanded.has(d.order_id);
                    const hasDetail = !!reasoning;
                    return (
                      <Fragment key={d.order_id}>
                        <tr
                          className={`border-b border-gray-100 ${hasDetail ? "cursor-pointer hover:bg-blue-50" : "hover:bg-gray-50"}`}
                          onClick={() => hasDetail && toggleExpanded(d.order_id)}
                        >
                          <td className="py-2 pr-3 text-gray-400">
                            {hasDetail ? (isOpen ? "▼" : "▶") : ""}
                          </td>
                          <td className="py-2 pr-3 font-mono text-gray-900 font-medium">
                            {d.symbol}
                          </td>
                          <td className="py-2 pr-3">
                            <SideBadge side={d.side} />
                          </td>
                          <td className="py-2 pr-3 text-gray-700">
                            {d.decision_price
                              ? `$${d.decision_price.toFixed(2)}`
                              : "—"}
                          </td>
                          <td className="py-2 pr-3 text-gray-700 text-xs">
                            {conf != null ? `${conf}/10` : "—"}
                          </td>
                          <td className="py-2 pr-3">
                            <PnlCell pct={d.pnl_snapshots?.["7d"]?.pnl_pct} />
                          </td>
                          <td className="py-2 pr-3">
                            <PnlCell pct={d.pnl_snapshots?.["30d"]?.pnl_pct} />
                          </td>
                          <td className="py-2 pr-3">
                            <PnlCell pct={d.pnl_snapshots?.["90d"]?.pnl_pct} />
                          </td>
                          <td className="py-2 pr-3 text-xs text-gray-500">
                            {new Date(d.created_at).toLocaleDateString()}
                          </td>
                          <td className="py-2 pr-3 text-xs text-gray-500">
                            {d.decision_type}
                          </td>
                        </tr>
                        {isOpen && hasDetail && (
                          <tr className="bg-blue-50/40">
                            <td></td>
                            <td colSpan={9} className="py-3 pr-3 text-sm text-gray-700">
                              <div className="whitespace-pre-wrap leading-relaxed">
                                <span className="text-xs uppercase text-gray-500 font-semibold mr-2">
                                  AI Reasoning:
                                </span>
                                {reasoning}
                                {d.metadata?.position_size_percent != null && (
                                  <span className="ml-3 text-xs text-gray-500">
                                    · suggested size: {d.metadata.position_size_percent}%
                                  </span>
                                )}
                                {d.metadata?.full_research && (
                                  <div className="mt-2">
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        setResearchModal({
                                          symbol: d.symbol,
                                          text: String(d.metadata?.full_research || ""),
                                        });
                                      }}
                                      className="inline-flex items-center gap-1 rounded border border-blue-300 bg-white px-2 py-1 text-xs font-medium text-blue-700 hover:bg-blue-100"
                                    >
                                      📄 View Full Research
                                    </button>
                                  </div>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {showChart && (
              <div className="mt-6 h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="horizon" stroke="#6b7280" />
                    <YAxis
                      stroke="#6b7280"
                      tickFormatter={(v) => `${v}%`}
                      domain={["auto", "auto"]}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "#ffffff",
                        border: "1px solid #e5e7eb",
                        color: "#111827",
                      }}
                      formatter={(value: number) => `${value.toFixed(2)}%`}
                    />
                    <Legend />
                    {chartSymbols.map((sym, i) => (
                      <Line
                        key={sym}
                        type="monotone"
                        dataKey={sym}
                        stroke={PALETTE[i % PALETTE.length]}
                        strokeWidth={2}
                        dot
                        connectNulls
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </>
        )}
      </div>

      {/* Full-research modal — opened from per-row [View Full Research] button */}
      {researchModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => setResearchModal(null)}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="w-full max-w-3xl max-h-[80vh] flex flex-col rounded-lg bg-white shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
              <h3 className="text-base font-semibold text-gray-900">
                Full Research — {researchModal.symbol}
              </h3>
              <button
                onClick={() => setResearchModal(null)}
                className="text-gray-400 hover:text-gray-600 text-xl leading-none"
                aria-label="Close"
              >
                ×
              </button>
            </div>
            <div className="overflow-y-auto px-4 py-4 text-sm text-gray-800 whitespace-pre-wrap font-sans leading-relaxed">
              {researchModal.text || "(no research text recorded for this decision)"}
            </div>
            <div className="border-t border-gray-200 px-4 py-2 text-right">
              <button
                onClick={() => setResearchModal(null)}
                className="rounded border border-gray-300 bg-white px-3 py-1 text-xs text-gray-700 hover:bg-gray-50"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
