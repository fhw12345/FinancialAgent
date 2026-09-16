/** Read-only historical decisions plus Stage-A assessment results. */
import { useMemo, useState, Fragment } from "react";
import { useTranslation } from "react-i18next";
import { Activity } from "lucide-react";
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
import { useDecisions } from "../../hooks/useDecisions";
import { getRecordValue } from "../../utils/safeRecord";
import {
  buildSeries,
  groupBySymbol,
  computeKpis,
  PALETTE,
  type SourceTab,
  type ResearchModalState,
} from "./decisionTracking/legacyMetrics";
import { KpiBar } from "./decisionTracking/LegacyCells";
import { DecisionRows } from "./decisionTracking/DecisionRows";
import { ResearchBody } from "./decisionTracking/ResearchBody";
import DecisionAssessments from "./DecisionAssessments";
export function DecisionTracker() {
  const { i18n } = useTranslation();
  const [symbolFilter, setSymbolFilter] = useState("");
  const [tab, setTab] = useState<SourceTab>("all");
  const [expandedReasoning, setExpandedReasoning] = useState<Set<string>>(
    new Set(),
  );
  const [expandedHistory, setExpandedHistory] = useState<Set<string>>(
    new Set(),
  );
  const [researchModal, setResearchModal] = useState<ResearchModalState | null>(
    null,
  );
  const { data, isLoading, error } = useDecisions(
    symbolFilter || undefined,
    tab === "all" ? undefined : tab,
    100,
  );

  const decisions = useMemo(() => data?.decisions ?? [], [data?.decisions]);

  const groups = useMemo(() => groupBySymbol(decisions), [decisions]);
  const kpis = useMemo(() => computeKpis(decisions), [decisions]);

  // Chart series: only the latest decision per symbol — plotting every
  // historical decision would create criss-crossing lines that no longer
  // tell a clear story.
  const latestPerSymbol = useMemo(() => groups.map((g) => g.latest), [groups]);
  const { data: chartData, symbols: chartSymbols } = useMemo(
    () => buildSeries(latestPerSymbol),
    [latestPerSymbol],
  );

  const toggleReasoning = (id: string) =>
    setExpandedReasoning((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const toggleHistory = (symbol: string) =>
    setExpandedHistory((prev) => {
      const next = new Set(prev);
      if (next.has(symbol)) next.delete(symbol);
      else next.add(symbol);
      return next;
    });

  const showChart =
    chartSymbols.length > 0 &&
    chartData.some((point) =>
      chartSymbols.some(
        (symbol) =>
          typeof getRecordValue<string, string | number>(point, symbol) ===
          "number",
      ),
    );

  return (
    <div className="bg-white rounded-lg border border-gray-200 mt-6">
      <DecisionAssessments
        symbol={symbolFilter || undefined}
        source={tab === "all" ? undefined : tab}
      />
      <p
        className="p-4 text-sm text-amber-900"
        data-testid="legacy-history-notice"
      >
        Historical AI drafts are unverified and read-only. Use Add Transaction
        to record actual trades independently.
      </p>
      <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
          <Activity className="h-4 w-4" />
          Decision Tracker
          <span className="text-xs font-normal text-gray-500">
            (legacy directional history — not validated strategy returns)
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

      {!isLoading && !error && decisions.length > 0 && <KpiBar kpis={kpis} />}

      <div className="p-4">
        {isLoading && (
          <div className="text-sm text-gray-500">Loading decisions…</div>
        )}
        {error && (
          <div className="text-sm text-red-600">
            Failed to load decisions: {error.message}
          </div>
        )}

        {!isLoading && !error && decisions.length === 0 && (
          <div className="text-sm text-gray-500">
            No legacy AI records. New research appears in the non-actionable
            assessments above.
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
                    <th className="py-2 pr-3">Entry</th>
                    <th className="py-2 pr-3">Stop</th>
                    <th className="py-2 pr-3">Target</th>
                    <th className="py-2 pr-3">Conf</th>
                    <th className="py-2 pr-3">7d</th>
                    <th className="py-2 pr-3">30d</th>
                    <th className="py-2 pr-3">90d</th>
                    <th className="py-2 pr-3">Date</th>
                    <th className="py-2 pr-3">Type</th>
                    <th className="py-2 pr-3">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {groups.map((g) => {
                    const histOpen = expandedHistory.has(g.symbol);
                    const moreCount = g.history.length;
                    return (
                      <Fragment key={g.symbol}>
                        <DecisionRows
                          d={g.latest}
                          isOpen={expandedReasoning.has(g.latest.order_id)}
                          onToggle={() => toggleReasoning(g.latest.order_id)}
                          onOpenResearch={setResearchModal}
                          locale={i18n.language}
                        />
                        {moreCount > 0 && (
                          <tr className="bg-white">
                            <td></td>
                            <td colSpan={13} className="py-1 pr-3">
                              <button
                                onClick={() => toggleHistory(g.symbol)}
                                className="text-xs text-blue-600 hover:text-blue-800 hover:underline"
                              >
                                {histOpen
                                  ? `▼ Hide ${moreCount} earlier decision${moreCount === 1 ? "" : "s"} for ${g.symbol}`
                                  : `▶ Show ${moreCount} earlier decision${moreCount === 1 ? "" : "s"} for ${g.symbol}`}
                              </button>
                            </td>
                          </tr>
                        )}
                        {histOpen &&
                          g.history.map((h) => (
                            <DecisionRows
                              key={h.order_id}
                              d={h}
                              isOpen={expandedReasoning.has(h.order_id)}
                              onToggle={() => toggleReasoning(h.order_id)}
                              onOpenResearch={setResearchModal}
                              indented
                              locale={i18n.language}
                            />
                          ))}
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
                        stroke={PALETTE.at(i % PALETTE.length) ?? "#2563eb"}
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

      {/* Full-research modal — opened from per-row [View Full Research] button.
          Backdrop close uses onMouseDown + e.target===e.currentTarget so a
          drag-select that overshoots into the backdrop doesn't close the
          modal (same fix as AddTransactionModal v0.11.7). */}
      {researchModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
        >
          <button
            type="button"
            aria-label="Close full research dialog"
            className="absolute inset-0 cursor-default"
            onClick={() => setResearchModal(null)}
          />
          <div className="relative w-full max-w-3xl max-h-[80vh] flex flex-col rounded-lg bg-white shadow-xl">
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
            <div className="overflow-y-auto px-4 py-4 text-sm text-gray-800 leading-relaxed">
              {researchModal.text ? (
                <ResearchBody
                  text={researchModal.text}
                  precomputed={researchModal.text_zh ?? null}
                />
              ) : (
                "(no research text recorded for this decision)"
              )}
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
