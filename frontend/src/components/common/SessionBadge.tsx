/**
 * Pill chip showing the trading session that produced the price.
 *
 * Backend stamps `last_session` (or `session`) on holdings/watchlist rows.
 * Renders `null` for "regular" or undefined to keep the regular-session UI
 * uncluttered. Color tokens follow the existing tailwind chip style used in
 * PortfolioSummaryTable (rounded-full, text-[10px], px-1.5 py-0.5).
 */

import { useTranslation } from "react-i18next";

export type Session = "pre" | "regular" | "post" | "closed";

interface SessionBadgeProps {
  session?: Session | null;
}

function styleFor(session: "pre" | "post" | "closed"): string {
  switch (session) {
    case "pre":
      return "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300";
    case "post":
      return "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300";
    case "closed":
      return "bg-slate-200 text-slate-700 dark:bg-slate-700/40 dark:text-slate-300";
  }
}

export function SessionBadge({ session }: SessionBadgeProps) {
  const { t } = useTranslation("portfolio");
  if (!session || session === "regular") return null;
  return (
    <span
      data-testid="session-badge"
      data-session={session}
      className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium ${styleFor(session)}`}
    >
      {t(`session.${session}`)}
    </span>
  );
}
