/**
 * Locale-aware timestamp formatting.
 *
 * Backend ISO strings are UTC (datetime.now(UTC).isoformat() → "...+00:00").
 * For zh-CN UI we display in Beijing time (UTC+8); for other locales we let
 * the browser pick the user's local zone.
 */

const CN_TIMEZONE = "Asia/Shanghai";

function isChinese(locale: string | undefined): boolean {
  return !!locale && locale.toLowerCase().startsWith("zh");
}

function pickLocale(locale: string | undefined): string {
  return isChinese(locale) ? "zh-CN" : "en-US";
}

function withTimezone(
  options: Intl.DateTimeFormatOptions | undefined,
  locale: string | undefined,
): Intl.DateTimeFormatOptions {
  const opts: Intl.DateTimeFormatOptions = { ...(options ?? {}) };
  if (isChinese(locale) && !opts.timeZone) {
    opts.timeZone = CN_TIMEZONE;
  }
  return opts;
}

/**
 * Format an ISO timestamp string.
 *
 * @param iso ISO 8601 string (typically UTC from the backend)
 * @param locale i18next language code (e.g. "zh-CN", "en")
 * @param options Intl.DateTimeFormat options; defaults to date + time
 */
export function formatTimestamp(
  iso: string | number | Date | null | undefined,
  locale: string | undefined,
  options?: Intl.DateTimeFormatOptions,
): string {
  if (iso === null || iso === undefined || iso === "") return "";
  const date = iso instanceof Date ? iso : new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(pickLocale(locale), withTimezone(options, locale));
}

/** Date-only variant (no time component). */
export function formatDate(
  iso: string | number | Date | null | undefined,
  locale: string | undefined,
  options?: Intl.DateTimeFormatOptions,
): string {
  if (iso === null || iso === undefined || iso === "") return "";
  const date = iso instanceof Date ? iso : new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(
    pickLocale(locale),
    withTimezone(options, locale),
  );
}

/** Time-only variant (no date component). */
export function formatTime(
  iso: string | number | Date | null | undefined,
  locale: string | undefined,
  options?: Intl.DateTimeFormatOptions,
): string {
  if (iso === null || iso === undefined || iso === "") return "";
  const date = iso instanceof Date ? iso : new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString(
    pickLocale(locale),
    withTimezone(options, locale),
  );
}

// ISO 8601 with required time component, optional seconds/fractional, required
// timezone (Z or ±HH:MM / ±HHMM). Naive ISO without TZ is intentionally NOT
// matched — it's ambiguous, and we don't want to silently mis-convert.
// All quantifiers are bounded; no catastrophic-backtracking risk.
// eslint-disable-next-line security/detect-unsafe-regex
const ISO_TIMESTAMP_RE =
  /\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})\b/g;

/**
 * Replace every ISO 8601 timestamp inside a markdown/plain-text string with
 * its locale-formatted equivalent. zh-* locales render in Beijing time; other
 * locales fall back to the browser's local zone. Pass `options` to control
 * the output format (e.g. `{ hour: "2-digit", minute: "2-digit" }` for HH:MM).
 */
export function localizeTimestamps(
  text: string,
  locale: string | undefined,
  options?: Intl.DateTimeFormatOptions,
): string {
  if (!text) return text;
  return text.replace(ISO_TIMESTAMP_RE, (match) => {
    const formatted = formatTimestamp(match, locale, options);
    return formatted || match;
  });
}
