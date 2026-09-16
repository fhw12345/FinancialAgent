import { ArrowUpCircle, ArrowDownCircle, CircleDot } from "lucide-react";
import type { DecisionRow } from "../../../hooks/useDecisions";
import {
  decisionWasRight,
  fmtHit,
  fmtPnlPct,
  type Kpis,
} from "./legacyMetrics";
export function PnlCell({
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
    <span
      className={cls}
      title={
        right === true
          ? "AI was right"
          : right === false
            ? "AI was wrong"
            : "neutral"
      }
    >
      {sign}
      {pct.toFixed(2)}%
    </span>
  );
}

export function SideBadge({ side }: { side: DecisionRow["side"] }) {
  const { Icon, cls, label } =
    side === "buy"
      ? {
          Icon: ArrowUpCircle,
          cls: "bg-green-100 text-green-800",
          label: "BUY",
        }
      : side === "sell"
        ? {
            Icon: ArrowDownCircle,
            cls: "bg-red-100 text-red-800",
            label: "SELL",
          }
        : {
            Icon: CircleDot,
            cls: "bg-yellow-100 text-yellow-800",
            label: "HOLD",
          };
  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium ${cls}`}
    >
      <Icon className="h-3 w-3" />
      {label}
    </span>
  );
}

export function KpiBar({ kpis }: { kpis: Kpis }) {
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
      <div
        className="flex flex-col"
        title="BUY right if up, SELL right if down, HOLD right if |Δ| < 2%"
      >
        <span className="text-[10px] uppercase tracking-wider text-gray-500">
          Hit 7d
        </span>
        <span
          className={`text-sm font-semibold tabular-nums ${hitColor(kpis.hitRate7d)}`}
        >
          {fmtHit(kpis.hitRate7d)}
        </span>
      </div>
      <div className="flex flex-col">
        <span className="text-[10px] uppercase tracking-wider text-gray-500">
          Hit 30d
        </span>
        <span
          className={`text-sm font-semibold tabular-nums ${hitColor(kpis.hitRate30d)}`}
        >
          {fmtHit(kpis.hitRate30d)}
        </span>
      </div>
      <div className="flex flex-col">
        <span className="text-[10px] uppercase tracking-wider text-gray-500">
          Hit 90d
        </span>
        <span
          className={`text-sm font-semibold tabular-nums ${hitColor(kpis.hitRate90d)}`}
        >
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
          <span className={hitColor(kpis.highConfHitRate)}>
            {fmtHit(kpis.highConfHitRate)}
          </span>
          <span className="text-gray-400"> / </span>
          <span className={hitColor(kpis.lowConfHitRate)}>
            {fmtHit(kpis.lowConfHitRate)}
          </span>
        </span>
      </div>
    </div>
  );
}
