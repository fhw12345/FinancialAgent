/**
 * ExtHoursLine — W3.18 inline companion line under the primary price.
 *
 * Renders "AH $215.05 (-0.07%)" or "PM $214.80 (-0.19%)" beneath the
 * regular/closed-session price cell on the Holdings and Watchlist
 * tables. Stays silent during active pre/post sessions (the primary
 * price IS the ext-hours print, surfaced by SessionBadge).
 *
 * Inputs are independently nullable to match the backend response
 * shape — when any of them is null we render nothing rather than
 * showing "$null (--%)".
 */

export interface ExtHoursLineProps {
  price: number | null;
  session: "pre" | "post" | null;
  changePercent: number | null;
}

const fmt = (v: number) => `$${v.toFixed(2)}`;

export function ExtHoursLine({
  price,
  session,
  changePercent,
}: ExtHoursLineProps) {
  if (price == null || session == null) {
    return null;
  }
  const label = session === "pre" ? "PM" : "AH";
  const pct = changePercent;
  const colorClass =
    pct == null
      ? "text-gray-400"
      : pct >= 0
        ? "text-green-600"
        : "text-red-600";
  return (
    <div className="text-[11px] text-gray-500 leading-tight">
      <span className="font-medium">{label}</span>{" "}
      <span>{fmt(price)}</span>
      {pct != null && (
        <span className={`ml-1 ${colorClass}`}>
          ({pct >= 0 ? "+" : ""}
          {pct.toFixed(2)}%)
        </span>
      )}
    </div>
  );
}
