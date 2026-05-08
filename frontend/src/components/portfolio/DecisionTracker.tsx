/**
 * Decision Tracker — table + per-symbol P&L chart + AI scorecard.
 *
 * Surfaces every AI decision (BUY/SELL orders + HOLD signals + Deep ReAct
 * verdicts) with ex-post P&L snapshots at 7d / 30d / 90d horizons computed
 * by the run_pnl_snapshots.py cron.
 *
 * Layout:
 *   [KPI bar — hit rate, avg P&L per horizon, confidence calibration]
 *   [Per-symbol grouped table — latest decision shown, history expandable]
 *   [P&L line chart — latest decision per symbol across horizons]
 */

import { useMemo, useState, Fragment } from "react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Translated } from "../Translated";
import { useTranslated } from "../../hooks/useTranslated";
import {
  ArrowUpCircle,
  ArrowDownCircle,
  CircleDot,
  Activity,
  CheckCircle2,
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
import { useDecisions, useMarkOrderExecuted, type DecisionRow } from "../../hooks/useDecisions";
import { usePortfolioSettings } from "./SettingsPanel";
import { IntentBadge } from "./IntentBadge";
import { ResearchPanel } from "./ResearchPanel";
import { useHoldings } from "../../hooks/usePortfolio";
import { formatDate } from "../../utils/timeFormatter";

const HORIZONS = ["7d", "30d", "90d"] as const;
type Horizon = (typeof HORIZONS)[number];

// HOLD is "right" if the price barely moved. Symmetric band around 0.
const HOLD_NEUTRAL_BAND_PCT = 2.0;

/**
 * Was this decision "right" at the given horizon?
 *   BUY  → right if price went up
 *   SELL → right if price went down
 *   HOLD → right if price stayed within ±HOLD_NEUTRAL_BAND_PCT
 * Returns null when the snapshot for that horizon doesn't exist yet
 * (decision too recent), so callers can ignore N/A from hit-rate math.
 */
function decisionWasRight(
  side: DecisionRow["side"],
  pnlPct: number | undefined | null,
): boolean | null {
  if (pnlPct === undefined || pnlPct === null) return null;
  switch (side) {
    case "buy":
      return pnlPct > 0;
    case "sell":
      return pnlPct < 0;
    case "hold":
      return Math.abs(pnlPct) < HOLD_NEUTRAL_BAND_PCT;
  }
}

/** Same color contract as PnlCell, but parameterized by "good for the
 * decision" rather than "price went up". A SELL with -8% P&L is GREEN
 * because the AI was right, even though the raw number is negative. */
function PnlCell({
  pct,
  side,
}: {
  pct: number | undefined | null;
  side: DecisionRow["side"];
}) {
  if (pct === undefined || pct === null) {
    return <span className="text-gray-400">—</span>;
  }
  const right = decisionWasRight(side, pct);
  const cls =
    right === true
      ? "text-green-700 font-medium"
      : right === false
        ? "text-red-700 font-medium"
        : "text-gray-600";
  const sign = pct > 0 ? "+" : "";
  return (
    <span className={cls} title={right === true ? "AI was right" : right === false ? "AI was wrong" : "neutral"}>
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

function buildSeries(latestPerSymbol: DecisionRow[]): {
  data: SeriesPoint[];
  symbols: string[];
} {
  const symbols = latestPerSymbol.map((d) => d.symbol);
  const data: SeriesPoint[] = HORIZONS.map((h) => {
    const point: SeriesPoint = { horizon: h };
    for (const d of latestPerSymbol) {
      const snap = d.pnl_snapshots?.[h];
      if (snap?.pnl_pct !== undefined) {
        point[d.symbol] = snap.pnl_pct;
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
  text_zh?: string | null;
}

interface MarkExecutedModalState {
  decision: DecisionRow;
  defaultQty: number;
  defaultPrice: number;
}

// ---------------------------------------------------------------------------
// Grouping: collapse history per symbol so the table doesn't drown in noise.
// API returns decisions newest-first, so the first occurrence of a symbol
// is the latest decision. We preserve that order across groups.
// ---------------------------------------------------------------------------
interface SymbolGroup {
  symbol: string;
  latest: DecisionRow;
  history: DecisionRow[]; // older, newest-first; excludes `latest`
}

function groupBySymbol(decisions: DecisionRow[]): SymbolGroup[] {
  const groups = new Map<string, SymbolGroup>();
  for (const d of decisions) {
    const existing = groups.get(d.symbol);
    if (!existing) {
      groups.set(d.symbol, { symbol: d.symbol, latest: d, history: [] });
    } else {
      existing.history.push(d);
    }
  }
  return Array.from(groups.values());
}

// ---------------------------------------------------------------------------
// KPI bar — answers "is the AI actually any good?" at a glance.
// All metrics computed against currently-filtered decisions only, so tab/
// symbol filter naturally scope the scorecard.
// ---------------------------------------------------------------------------
interface Kpis {
  scoredCount: number; // decisions with at least one horizon snapshot
  hitRate7d: number | null; // 0-1, null if no 7d data
  hitRate30d: number | null;
  hitRate90d: number | null;
  avgPnl7d: number | null; // signed, in percent (price-direction, not "right")
  avgPnl30d: number | null;
  avgPnl90d: number | null;
  highConfHitRate: number | null; // confidence >= 7
  lowConfHitRate: number | null; // confidence <= 5
}

function computeKpis(decisions: DecisionRow[]): Kpis {
  const hits: Record<Horizon, number[]> = { "7d": [], "30d": [], "90d": [] };
  const pnls: Record<Horizon, number[]> = { "7d": [], "30d": [], "90d": [] };
  const high: number[] = [];
  const low: number[] = [];
  let scoredCount = 0;

  for (const d of decisions) {
    let scored = false;
    for (const h of HORIZONS) {
      const pct = d.pnl_snapshots?.[h]?.pnl_pct;
      const right = decisionWasRight(d.side, pct);
      if (right === null) continue;
      scored = true;
      hits[h].push(right ? 1 : 0);
      if (typeof pct === "number") pnls[h].push(pct);
    }
    if (scored) scoredCount += 1;

    // Confidence calibration uses the 7d hit only — longest available horizon
    // would bias toward older decisions; 7d is the leading indicator.
    const r7 = decisionWasRight(d.side, d.pnl_snapshots?.["7d"]?.pnl_pct);
    const conf = d.metadata?.confidence;
    if (r7 !== null && typeof conf === "number") {
      if (conf >= 7) high.push(r7 ? 1 : 0);
      else if (conf <= 5) low.push(r7 ? 1 : 0);
    }
  }

  const mean = (xs: number[]) =>
    xs.length === 0 ? null : xs.reduce((a, b) => a + b, 0) / xs.length;

  return {
    scoredCount,
    hitRate7d: mean(hits["7d"]),
    hitRate30d: mean(hits["30d"]),
    hitRate90d: mean(hits["90d"]),
    avgPnl7d: mean(pnls["7d"]),
    avgPnl30d: mean(pnls["30d"]),
    avgPnl90d: mean(pnls["90d"]),
    highConfHitRate: mean(high),
    lowConfHitRate: mean(low),
  };
}

function fmtPct(v: number | null, opts: { signed?: boolean } = {}) {
  if (v === null || Number.isNaN(v)) return "—";
  const pct = v * (opts.signed === false ? 1 : 1); // pass-through
  const sign = opts.signed && pct > 0 ? "+" : "";
  return `${sign}${(pct * (opts.signed ? 1 : 100)).toFixed(opts.signed ? 2 : 0)}%`;
}

// hit rate is 0-1 → render as integer percent
function fmtHit(v: number | null) {
  if (v === null) return "—";
  return `${Math.round(v * 100)}%`;
}

// signed P&L pct (already in percent units) → "+12.34%" / "-1.20%"
function fmtPnlPct(v: number | null) {
  if (v === null) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function KpiBar({ kpis }: { kpis: Kpis }) {
  if (kpis.scoredCount === 0) {
    return (
      <div className="px-4 py-3 border-b border-gray-200 bg-gray-50 text-xs text-gray-500">
        No scored decisions yet — P&L snapshots fill in 7+ days after each
        decision. Come back later to see the AI scorecard.
      </div>
    );
  }
  const Cell = ({
    label,
    value,
    tooltip,
  }: {
    label: string;
    value: string;
    tooltip?: string;
  }) => (
    <div className="flex flex-col" title={tooltip}>
      <span className="text-[10px] uppercase tracking-wider text-gray-500">
        {label}
      </span>
      <span className="text-sm font-semibold text-gray-900 tabular-nums">
        {value}
      </span>
    </div>
  );
  // Color for hit-rate: green ≥60%, amber 45-59%, red <45%
  const hitColor = (v: number | null) =>
    v === null
      ? "text-gray-400"
      : v >= 0.6
        ? "text-green-700"
        : v >= 0.45
          ? "text-amber-700"
          : "text-red-700";
  return (
    <div className="px-4 py-3 border-b border-gray-200 bg-gray-50 grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-x-6 gap-y-3">
      <Cell
        label="Scored"
        value={`${kpis.scoredCount}`}
        tooltip="Decisions with at least one P&L snapshot"
      />
      <div className="flex flex-col" title="BUY right if up, SELL right if down, HOLD right if |Δ| < 2%">
        <span className="text-[10px] uppercase tracking-wider text-gray-500">
          Hit 7d
        </span>
        <span className={`text-sm font-semibold tabular-nums ${hitColor(kpis.hitRate7d)}`}>
          {fmtHit(kpis.hitRate7d)}
        </span>
      </div>
      <div className="flex flex-col">
        <span className="text-[10px] uppercase tracking-wider text-gray-500">
          Hit 30d
        </span>
        <span className={`text-sm font-semibold tabular-nums ${hitColor(kpis.hitRate30d)}`}>
          {fmtHit(kpis.hitRate30d)}
        </span>
      </div>
      <div className="flex flex-col">
        <span className="text-[10px] uppercase tracking-wider text-gray-500">
          Hit 90d
        </span>
        <span className={`text-sm font-semibold tabular-nums ${hitColor(kpis.hitRate90d)}`}>
          {fmtHit(kpis.hitRate90d)}
        </span>
      </div>
      <Cell label="Avg 7d P&L" value={fmtPnlPct(kpis.avgPnl7d)} />
      <Cell label="Avg 30d P&L" value={fmtPnlPct(kpis.avgPnl30d)} />
      <Cell label="Avg 90d P&L" value={fmtPnlPct(kpis.avgPnl90d)} />
      <div
        className="flex flex-col"
        title="Hit rate at 7d for high-confidence (≥7) vs low-confidence (≤5) decisions. Should diverge if AI is well-calibrated."
      >
        <span className="text-[10px] uppercase tracking-wider text-gray-500">
          Conf calib (≥7 / ≤5)
        </span>
        <span className="text-sm font-semibold tabular-nums">
          <span className={hitColor(kpis.highConfHitRate)}>{fmtHit(kpis.highConfHitRate)}</span>
          <span className="text-gray-400"> / </span>
          <span className={hitColor(kpis.lowConfHitRate)}>{fmtHit(kpis.lowConfHitRate)}</span>
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Full-research modal body — rendered markdown with translation.
// Uses the same `useTranslated` hook as ChatMessages so server-precomputed
// `full_research_zh` short-circuits the /api/translate round-trip; the
// resulting (English or Chinese) markdown is then run through ReactMarkdown
// instead of being dumped as raw text.
// ---------------------------------------------------------------------------
function ResearchBody({
  text,
  precomputed,
}: {
  text: string;
  precomputed: string | null;
}) {
  const { text: shown, isLoading } = useTranslated(text, { precomputed });
  return (
    <div
      className="markdown-content text-sm max-w-none"
      style={isLoading ? { opacity: 0.7 } : undefined}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className="text-xl font-bold mb-3 text-gray-900">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-lg font-bold mb-3 text-gray-900">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-base font-bold mb-2 text-gray-800">
              {children}
            </h3>
          ),
          p: ({ children }) => (
            <p className="mb-3 last:mb-0 leading-relaxed text-sm">{children}</p>
          ),
          ul: ({ children }) => (
            <ul className="list-disc list-inside mb-3 space-y-1 ml-2">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal list-inside mb-3 space-y-1 ml-2">
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li className="text-sm leading-relaxed">{children}</li>
          ),
          strong: ({ children }) => (
            <strong className="font-semibold text-gray-900">{children}</strong>
          ),
          em: ({ children }) => <em className="italic">{children}</em>,
          code: ({ className, children, ...props }) => {
            const isInline = !className;
            return isInline ? (
              <code
                className="bg-blue-100 text-blue-800 px-1.5 py-0.5 rounded text-xs font-mono"
                {...props}
              >
                {children}
              </code>
            ) : (
              <code
                className={`block bg-gray-800 text-gray-100 p-3 rounded text-xs font-mono overflow-x-auto ${className}`}
                {...props}
              >
                {children}
              </code>
            );
          },
          pre: ({ children }) => (
            <pre className="mb-3 rounded overflow-hidden">{children}</pre>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-blue-500 pl-4 my-3 italic text-gray-700">
              {children}
            </blockquote>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto mb-3">
              <table className="min-w-full border-collapse border border-gray-300 text-xs">
                {children}
              </table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border border-gray-300 px-2 py-1 bg-gray-100 font-semibold text-left">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-gray-300 px-2 py-1">{children}</td>
          ),
          hr: () => <hr className="my-4 border-gray-200" />,
          a: ({ children, href }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:underline"
            >
              {children}
            </a>
          ),
        }}
      >
        {shown}
      </ReactMarkdown>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Decision row + (optionally) its reasoning expansion. Pulled out so the
// per-symbol grouping wrapper stays readable.
// ---------------------------------------------------------------------------
interface DecisionRowsProps {
  d: DecisionRow;
  isOpen: boolean;
  onToggle: () => void;
  onOpenResearch: (state: ResearchModalState) => void;
  onMarkExecuted: (d: DecisionRow) => void;
  /** Visual indent flag for history rows under a group header */
  indented?: boolean;
  locale: string;
}

function DecisionRows({
  d,
  isOpen,
  onToggle,
  onOpenResearch,
  onMarkExecuted,
  indented,
  locale,
}: DecisionRowsProps) {
  const reasoning = d.metadata?.reasoning ?? "";
  const conf = d.metadata?.confidence;
  const hasDetail = !!reasoning;
  return (
    <>
      <tr
        className={`border-b border-gray-100 ${hasDetail ? "cursor-pointer hover:bg-blue-50" : "hover:bg-gray-50"} ${indented ? "bg-gray-50/50" : ""}`}
        onClick={() => hasDetail && onToggle()}
      >
        <td className="py-2 pr-3 text-gray-400">
          {hasDetail ? (isOpen ? "▼" : "▶") : ""}
        </td>
        <td
          className={`py-2 pr-3 font-mono text-gray-900 ${indented ? "pl-4 text-xs text-gray-500" : "font-medium"}`}
        >
          {indented ? `↳ ${d.symbol}` : d.symbol}
        </td>
        <td className="py-2 pr-3">
          <div className="flex items-center gap-1">
            <SideBadge side={d.side} />
            <IntentBadge intent={d.intent} />
            {d.metadata?.legacy_short_geometry === true && (
              <span
                data-testid="legacy-geometry-warning"
                title="历史脏数据：原始决策的 stop/target 排布等同做空字段，已自动迁移并标记"
                className="inline-flex items-center rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-800 dark:bg-amber-900/30 dark:text-amber-300"
              >
                ⚠ 几何
              </span>
            )}
            {Array.isArray(
              (d.metadata?.data_quality as { degraded_fields?: unknown[] } | undefined)
                ?.degraded_fields,
            ) &&
              ((d.metadata?.data_quality as { degraded_fields: unknown[] }).degraded_fields
                .length ?? 0) > 0 && (
                <span
                  data-testid="data-quality-degraded"
                  title={
                    "数据降级：相关字段已无法从主源拿到或已过期\n• " +
                    (
                      (d.metadata?.data_quality as { degraded_fields: string[] })
                        .degraded_fields ?? []
                    ).join("\n• ")
                  }
                  className="inline-flex items-center rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-medium text-slate-700 dark:bg-slate-700 dark:text-slate-200"
                >
                  📉 数据降级
                </span>
              )}
          </div>
        </td>
        <td className="py-2 pr-3 text-gray-700">
          {d.decision_price ? `$${d.decision_price.toFixed(2)}` : "—"}
        </td>
        <td className="py-2 pr-3 text-gray-700 font-mono text-xs">
          {d.metadata?.entry_price != null
            ? `$${(d.metadata.entry_price as number).toFixed(2)}`
            : "—"}
        </td>
        <td className="py-2 pr-3 text-red-600 font-mono text-xs">
          {d.metadata?.stop_loss != null
            ? `$${(d.metadata.stop_loss as number).toFixed(2)}`
            : "—"}
        </td>
        <td className="py-2 pr-3 text-green-600 font-mono text-xs">
          {d.metadata?.take_profit != null
            ? `$${(d.metadata.take_profit as number).toFixed(2)}`
            : "—"}
        </td>
        <td className="py-2 pr-3 text-gray-700 text-xs">
          {conf != null ? `${conf}/10` : "—"}
        </td>
        <td className="py-2 pr-3">
          <PnlCell pct={d.pnl_snapshots?.["7d"]?.pnl_pct} side={d.side} />
        </td>
        <td className="py-2 pr-3">
          <PnlCell pct={d.pnl_snapshots?.["30d"]?.pnl_pct} side={d.side} />
        </td>
        <td className="py-2 pr-3">
          <PnlCell pct={d.pnl_snapshots?.["90d"]?.pnl_pct} side={d.side} />
        </td>
        <td className="py-2 pr-3 text-xs text-gray-500">
          {formatDate(d.created_at, locale)}
        </td>
        <td className="py-2 pr-3 text-xs text-gray-500">{d.decision_type}</td>
        <td className="py-2 pr-3" onClick={(e) => e.stopPropagation()}>
          {d.decision_type === "order" && (d.side === "buy" || d.side === "sell") ? (
            d.status === "filled" ? (
              <span
                className="inline-flex items-center gap-1 rounded bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700"
                title={
                  d.filled_at
                    ? `Executed ${formatDate(d.filled_at, locale)}`
                    : "Executed"
                }
              >
                <CheckCircle2 className="h-3 w-3" />
                {d.filled_avg_price != null
                  ? `@ $${d.filled_avg_price.toFixed(2)}`
                  : "Executed"}
              </span>
            ) : d.status === "suggested" ? (
              <button
                onClick={() => onMarkExecuted(d)}
                className="rounded border border-blue-300 bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-700 hover:bg-blue-100"
              >
                Mark Executed
              </button>
            ) : (
              <span className="text-[11px] text-gray-400">{d.status}</span>
            )
          ) : null}
        </td>
      </tr>
      {isOpen && hasDetail && (
        <tr className="bg-blue-50/40">
          <td></td>
          <td colSpan={13} className="py-3 pr-3 text-sm text-gray-700">
            <div className="whitespace-pre-wrap leading-relaxed">
              <span className="text-xs uppercase text-gray-500 font-semibold mr-2">
                AI Reasoning:
              </span>
              <Translated
                text={reasoning}
                precomputed={
                  (d.metadata?.reasoning_zh as string | null | undefined) ??
                  null
                }
              />
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
                      onOpenResearch({
                        symbol: d.symbol,
                        text: String(d.metadata?.full_research || ""),
                        text_zh:
                          (d.metadata?.full_research_zh as
                            | string
                            | null
                            | undefined) ?? null,
                      });
                    }}
                    className="inline-flex items-center gap-1 rounded border border-blue-300 bg-white px-2 py-1 text-xs font-medium text-blue-700 hover:bg-blue-100"
                  >
                    📄 View Full Research
                  </button>
                </div>
              )}
              <ResearchPanel metadata={d.metadata} />
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export function DecisionTracker() {
  const { i18n } = useTranslation();
  const [symbolFilter, setSymbolFilter] = useState("");
  const [tab, setTab] = useState<SourceTab>("all");
  const [expandedReasoning, setExpandedReasoning] = useState<Set<string>>(
    new Set(),
  );
  const [expandedHistory, setExpandedHistory] = useState<Set<string>>(new Set());
  const [researchModal, setResearchModal] =
    useState<ResearchModalState | null>(null);
  const [markModal, setMarkModal] = useState<MarkExecutedModalState | null>(
    null,
  );
  const { data: settings } = usePortfolioSettings();
  const { data: holdings } = useHoldings();
  const markMut = useMarkOrderExecuted();
  const { data, isLoading, error } = useDecisions(
    symbolFilter || undefined,
    tab === "all" ? undefined : tab,
    100,
  );

  const decisions = data?.decisions ?? [];

  const openMarkModal = (d: DecisionRow) => {
    const entry = (d.metadata?.entry_price as number | null | undefined) ?? null;
    const sizePct =
      (d.metadata?.position_size_percent as number | null | undefined) ?? null;
    const cash = settings?.cash_balance ?? 0;
    const px = entry ?? d.decision_price ?? 0;
    let qty = 0;
    if (d.side === "buy") {
      if (px > 0 && sizePct != null && cash > 0) {
        qty = Math.floor((cash * (sizePct / 100)) / px);
      }
    } else if (d.side === "sell") {
      const h = (holdings ?? []).find((x) => x.symbol === d.symbol);
      qty = h?.quantity ?? 0;
    }
    setMarkModal({
      decision: d,
      defaultQty: qty > 0 ? qty : 1,
      defaultPrice: px > 0 ? px : 0,
    });
  };

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

      {!isLoading && !error && decisions.length > 0 && <KpiBar kpis={kpis} />}

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
                          onMarkExecuted={openMarkModal}
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
                              onMarkExecuted={openMarkModal}
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

      {/* Full-research modal — opened from per-row [View Full Research] button.
          Backdrop close uses onMouseDown + e.target===e.currentTarget so a
          drag-select that overshoots into the backdrop doesn't close the
          modal (same fix as AddTransactionModal v0.11.7). */}
      {researchModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setResearchModal(null);
          }}
          role="dialog"
          aria-modal="true"
        >
          <div className="w-full max-w-3xl max-h-[80vh] flex flex-col rounded-lg bg-white shadow-xl">
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

      {markModal && (
        <MarkExecutedModal
          state={markModal}
          isPending={markMut.isPending}
          error={markMut.error as Error | null}
          onClose={() => {
            setMarkModal(null);
            markMut.reset();
          }}
          onSubmit={async (qty, price) => {
            const result = await markMut.mutateAsync({
              orderId: markModal.decision.order_id,
              payload: { filled_qty: qty, filled_avg_price: price },
            });
            setMarkModal(null);
            markMut.reset();
            if (result.cash_warning) {
              window.alert(result.cash_warning);
            }
          }}
        />
      )}
    </div>
  );
}

interface MarkExecutedModalProps {
  state: MarkExecutedModalState;
  isPending: boolean;
  error: Error | null;
  onClose: () => void;
  onSubmit: (qty: number, price: number) => void | Promise<void>;
}

function MarkExecutedModal({
  state,
  isPending,
  error,
  onClose,
  onSubmit,
}: MarkExecutedModalProps) {
  const { decision, defaultQty, defaultPrice } = state;
  const [qtyStr, setQtyStr] = useState<string>(String(defaultQty));
  const [priceStr, setPriceStr] = useState<string>(defaultPrice.toFixed(2));
  const qty = Number(qtyStr);
  const price = Number(priceStr);
  const total =
    Number.isFinite(qty) && Number.isFinite(price) ? qty * price : 0;
  const valid = qty > 0 && price > 0;
  const sideLabel = decision.side === "buy" ? "BUY" : "SELL";
  const sideClass =
    decision.side === "buy" ? "text-green-700" : "text-red-700";
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !isPending) onClose();
      }}
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-md rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
          <h3 className="text-base font-semibold text-gray-900">
            Mark Executed —{" "}
            <span className={sideClass}>{sideLabel}</span>{" "}
            <span className="font-mono">{decision.symbol}</span>
          </h3>
          <button
            onClick={onClose}
            disabled={isPending}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none disabled:opacity-50"
            aria-label="Close"
          >
            ×
          </button>
        </div>
        <div className="px-4 py-4 space-y-3">
          <div className="text-xs text-gray-500">
            LLM suggested:{" "}
            {decision.metadata?.entry_price != null
              ? `entry $${(decision.metadata.entry_price as number).toFixed(2)}`
              : "no entry price"}
            {decision.metadata?.position_size_percent != null
              ? ` · size ${decision.metadata.position_size_percent}%`
              : ""}
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Filled Quantity
            </label>
            <input
              type="number"
              min="0"
              step="any"
              value={qtyStr}
              onChange={(e) => setQtyStr(e.target.value)}
              disabled={isPending}
              className="w-full rounded border border-gray-300 px-2 py-1 text-sm font-mono focus:border-blue-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Fill Price (USD)
            </label>
            <input
              type="number"
              min="0"
              step="0.01"
              value={priceStr}
              onChange={(e) => setPriceStr(e.target.value)}
              disabled={isPending}
              className="w-full rounded border border-gray-300 px-2 py-1 text-sm font-mono focus:border-blue-500 focus:outline-none"
            />
          </div>
          <div className="text-xs text-gray-600">
            Total:{" "}
            <span className="font-mono font-semibold text-gray-900">
              ${total.toFixed(2)}
            </span>
            <span className="text-gray-400">
              {" "}
              (cash will{" "}
              {decision.side === "buy" ? "decrease" : "increase"} by this amount)
            </span>
          </div>
          {error && (
            <div className="rounded border border-red-200 bg-red-50 px-2 py-1 text-xs text-red-700">
              {error.message}
            </div>
          )}
        </div>
        <div className="border-t border-gray-200 px-4 py-2 flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            disabled={isPending}
            className="rounded border border-gray-300 bg-white px-3 py-1 text-xs text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={() => valid && onSubmit(qty, price)}
            disabled={!valid || isPending}
            className="rounded bg-blue-600 px-3 py-1 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {isPending ? "Submitting…" : "Confirm"}
          </button>
        </div>
      </div>
    </div>
  );
}
