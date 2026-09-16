/** Historical directional metrics only; not investment-quality validation. */
import type { DecisionRow } from "../../../hooks/useDecisions";
import { getRecordValue, setRecordValue } from "../../../utils/safeRecord";
export const HORIZONS = ["7d", "30d", "90d"] as const;
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
export function decisionWasRight(
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

interface SeriesPoint {
  horizon: Horizon;
  [symbol: string]: number | string;
}

export function buildSeries(latestPerSymbol: DecisionRow[]): {
  data: SeriesPoint[];
  symbols: string[];
} {
  const symbols = latestPerSymbol.map((d) => d.symbol);
  const data: SeriesPoint[] = HORIZONS.map((h) => {
    const point: SeriesPoint = { horizon: h };
    for (const d of latestPerSymbol) {
      const snap = d.pnl_snapshots
        ? getRecordValue(d.pnl_snapshots, h)
        : undefined;
      if (snap?.pnl_pct !== undefined) {
        setRecordValue<string, string | number>(point, d.symbol, snap.pnl_pct);
      }
    }
    return point;
  });
  return { data, symbols };
}

export const PALETTE = [
  "#059669", // emerald-600
  "#2563eb", // blue-600
  "#d97706", // amber-600
  "#db2777", // pink-600
  "#7c3aed", // violet-600
  "#0891b2", // cyan-600
  "#dc2626", // red-600
  "#ea580c", // orange-600
];

export type SourceTab = "all" | "holdings" | "picks";

export interface ResearchModalState {
  symbol: string;
  text: string;
  text_zh?: string | null;
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

export function groupBySymbol(decisions: DecisionRow[]): SymbolGroup[] {
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
export interface Kpis {
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

export function computeKpis(decisions: DecisionRow[]): Kpis {
  const hits: Record<Horizon, number[]> = { "7d": [], "30d": [], "90d": [] };
  const pnls: Record<Horizon, number[]> = { "7d": [], "30d": [], "90d": [] };
  const high: number[] = [];
  const low: number[] = [];
  let scoredCount = 0;

  for (const d of decisions) {
    let scored = false;
    for (const h of HORIZONS) {
      const pct = d.pnl_snapshots
        ? getRecordValue(d.pnl_snapshots, h)?.pnl_pct
        : undefined;
      const right = decisionWasRight(d.side, pct);
      if (right === null) continue;
      scored = true;
      getRecordValue(hits, h)?.push(right ? 1 : 0);
      if (typeof pct === "number") getRecordValue(pnls, h)?.push(pct);
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

// hit rate is 0-1 → render as integer percent
export function fmtHit(v: number | null) {
  if (v === null) return "—";
  return `${Math.round(v * 100)}%`;
}

// signed P&L pct (already in percent units) → "+12.34%" / "-1.20%"
export function fmtPnlPct(v: number | null) {
  if (v === null) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}
