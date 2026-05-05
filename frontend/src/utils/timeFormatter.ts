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
