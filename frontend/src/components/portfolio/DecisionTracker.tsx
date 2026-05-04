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

import { useMemo, useState } from "react";
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

export function DecisionTracker() {
  const [symbolFilter, setSymbolFilter] = useState("");
  const { data, isLoading, error } = useDecisions(
    symbolFilter || undefined,
    100,
  );

  const decisions = data?.decisions ?? [];
  const { data: chartData, symbols: chartSymbols } = useMemo(
    () => buildSeries(decisions),
    [decisions],
  );
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
                    <th className="py-2 pr-3">Symbol</th>
                    <th className="py-2 pr-3">Side</th>
                    <th className="py-2 pr-3">Decision $</th>
                    <th className="py-2 pr-3">7d</th>
                    <th className="py-2 pr-3">30d</th>
                    <th className="py-2 pr-3">90d</th>
                    <th className="py-2 pr-3">Date</th>
                    <th className="py-2 pr-3">Type</th>
                  </tr>
                </thead>
                <tbody>
                  {decisions.map((d) => (
                    <tr
                      key={d.order_id}
                      className="border-b border-gray-100 hover:bg-gray-50"
                    >
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
                  ))}
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
    </div>
  );
}
