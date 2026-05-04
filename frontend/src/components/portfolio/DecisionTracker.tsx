/**
 * Decision Tracker — table + per-symbol P&L line chart.
 *
 * Surfaces every AI decision (BUY/SELL orders + HOLD signals + Deep ReAct
 * verdicts) with ex-post P&L snapshots at 7d / 30d / 90d horizons computed
 * by the run_pnl_snapshots.py cron.
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
    return <span className="text-gray-500">—</span>;
  }
  const cls =
    pct > 0
      ? "text-emerald-400"
      : pct < 0
        ? "text-red-400"
        : "text-gray-300";
  const sign = pct > 0 ? "+" : "";
  return <span className={cls}>{sign}{pct.toFixed(2)}%</span>;
}

function SideBadge({ side }: { side: DecisionRow["side"] }) {
  const map = {
    buy: { Icon: ArrowUpCircle, cls: "bg-emerald-500/15 text-emerald-300", label: "BUY" },
    sell: { Icon: ArrowDownCircle, cls: "bg-red-500/15 text-red-300", label: "SELL" },
    hold: { Icon: CircleDot, cls: "bg-gray-500/15 text-gray-300", label: "HOLD" },
  } as const;
  const { Icon, cls, label } = map[side] ?? map.hold;
  return (
    <span className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium ${cls}`}>
      <Icon className="h-3 w-3" />
      {label}
    </span>
  );
}

interface SeriesPoint {
  horizon: Horizon;
  [symbol: string]: number | string;
}

function buildSeries(decisions: DecisionRow[]): { data: SeriesPoint[]; symbols: string[] } {
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
  "#10b981",
  "#3b82f6",
  "#f59e0b",
  "#ec4899",
  "#8b5cf6",
  "#14b8a6",
  "#ef4444",
  "#f97316",
];

export function DecisionTracker() {
  const [symbolFilter, setSymbolFilter] = useState("");
  const { data, isLoading, error } = useDecisions(symbolFilter || undefined, 100);

  const decisions = data?.decisions ?? [];
  const { data: chartData, symbols: chartSymbols } = useMemo(
    () => buildSeries(decisions),
    [decisions],
  );
  const showChart = chartSymbols.length > 0 && chartData.some((p) =>
    chartSymbols.some((s) => typeof p[s] === "number"),
  );

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900/40 p-4 mt-6">
      <header className="flex items-center justify-between mb-3">
        <h3 className="flex items-center gap-2 text-base font-semibold text-gray-100">
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
          className="rounded border border-gray-700 bg-gray-950 px-2 py-1 text-xs text-gray-200 placeholder-gray-600 focus:border-emerald-500 focus:outline-none"
        />
      </header>

      {isLoading && <div className="text-sm text-gray-500">Loading decisions…</div>}
      {error && (
        <div className="text-sm text-red-400">
          Failed to load decisions: {(error as Error).message}
        </div>
      )}

      {!isLoading && !error && decisions.length === 0 && (
        <div className="text-sm text-gray-500">
          No AI decisions tracked yet. Run a portfolio analysis or a Deep ReAct chat
          to populate this table; P&L snapshots fill in 7+ days later.
        </div>
      )}

      {!isLoading && decisions.length > 0 && (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase text-gray-500 border-b border-gray-800">
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
                  <tr key={d.order_id} className="border-b border-gray-800/60">
                    <td className="py-2 pr-3 font-mono text-gray-200">{d.symbol}</td>
                    <td className="py-2 pr-3"><SideBadge side={d.side} /></td>
                    <td className="py-2 pr-3 text-gray-300">
                      {d.decision_price ? `$${d.decision_price.toFixed(2)}` : "—"}
                    </td>
                    <td className="py-2 pr-3"><PnlCell pct={d.pnl_snapshots?.["7d"]?.pnl_pct} /></td>
                    <td className="py-2 pr-3"><PnlCell pct={d.pnl_snapshots?.["30d"]?.pnl_pct} /></td>
                    <td className="py-2 pr-3"><PnlCell pct={d.pnl_snapshots?.["90d"]?.pnl_pct} /></td>
                    <td className="py-2 pr-3 text-xs text-gray-400">
                      {new Date(d.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-2 pr-3 text-xs text-gray-500">{d.decision_type}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {showChart && (
            <div className="mt-6 h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                  <XAxis dataKey="horizon" stroke="#9ca3af" />
                  <YAxis
                    stroke="#9ca3af"
                    tickFormatter={(v) => `${v}%`}
                    domain={["auto", "auto"]}
                  />
                  <Tooltip
                    contentStyle={{ background: "#0b1220", border: "1px solid #1f2937" }}
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
  );
}
