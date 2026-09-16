import { CheckCircle2 } from "lucide-react";
import type { DecisionRow } from "../../../hooks/useDecisions";
import { formatDate } from "../../../utils/timeFormatter";
import { Translated } from "../../Translated";
import { IntentBadge } from "../IntentBadge";
import { ResearchPanel } from "../ResearchPanel";
import { PnlCell, SideBadge } from "./LegacyCells";
import type { ResearchModalState } from "./legacyMetrics";
interface DecisionRowsProps {
  d: DecisionRow;
  isOpen: boolean;
  onToggle: () => void;
  onOpenResearch: (state: ResearchModalState) => void;
  /** Visual indent flag for history rows under a group header */
  indented?: boolean;
  locale: string;
}

export function DecisionRows({
  d,
  isOpen,
  onToggle,
  onOpenResearch,
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
            <span
              data-testid="legacy-decision-readonly"
              className="text-xs text-amber-800"
            >
              Legacy / unverified
            </span>
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
              (
                d.metadata?.data_quality as
                  { degraded_fields?: unknown[] } | undefined
              )?.degraded_fields,
            ) &&
              ((d.metadata?.data_quality as { degraded_fields: unknown[] })
                .degraded_fields.length ?? 0) > 0 && (
                <span
                  data-testid="data-quality-degraded"
                  title={
                    "数据降级：相关字段已无法从主源拿到或已过期\n• " +
                    (
                      (
                        d.metadata?.data_quality as {
                          degraded_fields: string[];
                        }
                      ).degraded_fields ?? []
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
            ? `$${d.metadata.entry_price.toFixed(2)}`
            : "—"}
        </td>
        <td className="py-2 pr-3 text-red-600 font-mono text-xs">
          {d.metadata?.stop_loss != null
            ? `$${d.metadata.stop_loss.toFixed(2)}`
            : "—"}
        </td>
        <td className="py-2 pr-3 text-green-600 font-mono text-xs">
          {d.metadata?.take_profit != null
            ? `$${d.metadata.take_profit.toFixed(2)}`
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
          {d.decision_type === "order" &&
          (d.side === "buy" || d.side === "sell") ? (
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
            ) : (
              <span className="text-xs text-amber-800">
                Legacy / unverified
              </span>
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
                precomputed={d.metadata?.reasoning_zh ?? null}
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
                        text_zh: d.metadata?.full_research_zh ?? null,
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
