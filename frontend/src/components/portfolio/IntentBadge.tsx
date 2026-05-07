/**
 * IntentBadge — direction-aware intent indicator (W1.3).
 *
 * Pairs with SideBadge to disambiguate ambiguous orders:
 *   side=sell + intent=close_long  → "平多"  (gray, selling existing long)
 *   side=sell + intent=open_short  → "做空"  (red, opening new short)
 *   side=buy  + intent=open_long   → "建多"  (green)
 *   side=buy  + intent=close_short → "平空"  (gray)
 *
 * If `intent` is null (legacy doc not yet migrated), renders nothing —
 * SideBadge alone is the fallback.
 *
 * Carries a data-testid so e2e can assert intent without snapshotting
 * the entire row.
 */
import type { OrderIntent } from "../../hooks/useDecisions";

const STYLES: Record<
  OrderIntent,
  { label: string; className: string }
> = {
  open_long: {
    label: "建多",
    className:
      "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300",
  },
  close_long: {
    label: "平多",
    className:
      "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  },
  open_short: {
    label: "做空",
    className:
      "bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-300",
  },
  close_short: {
    label: "平空",
    className:
      "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  },
  hold: { label: "", className: "" },
};

export function IntentBadge({
  intent,
}: {
  intent: OrderIntent | null | undefined;
}) {
  if (!intent || intent === "hold") return null;
  const style = STYLES[intent];
  if (!style || !style.label) return null;
  return (
    <span
      data-testid="intent-badge"
      data-intent={intent}
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium ${style.className}`}
    >
      {style.label}
    </span>
  );
}
