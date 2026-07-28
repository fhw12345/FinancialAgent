import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TimeInterval } from "../../services/market";
import {
  calculateDateRangeForSymbol,
  countInclusiveDays,
  getDateRangePreset,
  getMarketTimeZone,
  isIntradayInterval,
  validateDateRange,
  type DateRange,
  type DateRangePreset,
  type DateRangeValidationCode,
} from "../../utils/dateRangeCalculator";

const PRESETS: Array<{ key: DateRangePreset; label: string }> = [
  { key: "1w", label: "1W" },
  { key: "1m", label: "1M" },
  { key: "3m", label: "3M" },
  { key: "6m", label: "6M" },
  { key: "1y", label: "1Y" },
  { key: "ytd", label: "YTD" },
  { key: "max", label: "Max" },
];

interface DateRangePickerProps {
  value: DateRange;
  interval: TimeInterval;
  symbol: string;
  onApply: (range: DateRange) => void;
  disabled?: boolean;
}

export function DateRangePicker({
  value,
  interval,
  symbol,
  onApply,
  disabled = false,
}: DateRangePickerProps) {
  const { t } = useTranslation("market");
  const [draft, setDraft] = useState<DateRange>(value);
  const [error, setError] = useState<DateRangeValidationCode | null>(null);
  const timeZone = getMarketTimeZone(symbol);
  const today = useMemo(
    () => calculateDateRangeForSymbol({ start: "", end: "" }, "1m", symbol).end,
    [symbol],
  );
  const minimumDate = useMemo(
    () =>
      isIntradayInterval(interval)
        ? getDateRangePreset("1m", new Date(), timeZone).start
        : getDateRangePreset("max", new Date(), timeZone).start,
    [interval, timeZone],
  );

  useEffect(() => {
    setDraft(value);
    setError(null);
  }, [value, interval]);

  const apply = () => {
    const validationError = validateDateRange(
      draft,
      interval,
      new Date(),
      timeZone,
    );
    setError(validationError);
    if (!validationError) onApply(draft);
  };

  const reset = () => {
    const defaultRange = calculateDateRangeForSymbol(
      { start: "", end: "" },
      interval,
      symbol,
    );
    setDraft(defaultRange);
    setError(null);
    onApply(defaultRange);
  };

  return (
    <div
      className="mt-3 rounded-lg border border-gray-200 bg-gray-50 p-3"
      data-testid="date-range-picker"
    >
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex min-w-[135px] flex-1 flex-col gap-1 text-xs font-medium text-gray-600">
          {t("chart.dateRange.start")}
          <input
            type="date"
            value={draft.start}
            min={minimumDate}
            max={today}
            disabled={disabled}
            onChange={(event) => {
              setError(null);
              setDraft((current) => ({
                ...current,
                start: event.target.value,
              }));
            }}
            className="rounded border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-900 disabled:opacity-60"
            data-testid="date-range-start"
          />
        </label>
        <label className="flex min-w-[135px] flex-1 flex-col gap-1 text-xs font-medium text-gray-600">
          {t("chart.dateRange.end")}
          <input
            type="date"
            value={draft.end}
            min={minimumDate}
            max={today}
            disabled={disabled}
            onChange={(event) => {
              setError(null);
              setDraft((current) => ({
                ...current,
                end: event.target.value,
              }));
            }}
            className="rounded border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-900 disabled:opacity-60"
            data-testid="date-range-end"
          />
        </label>
        <button
          type="button"
          onClick={apply}
          disabled={disabled}
          className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          data-testid="date-range-apply"
        >
          {t("chart.dateRange.apply")}
        </button>
        <button
          type="button"
          onClick={reset}
          disabled={disabled}
          className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {t("chart.dateRange.reset")}
        </button>
      </div>

      <div className="mt-2 flex flex-wrap gap-1">
        {PRESETS.map((preset) => {
          const unavailable =
            isIntradayInterval(interval) && !["1w", "1m"].includes(preset.key);
          return (
            <button
              key={preset.key}
              type="button"
              disabled={disabled || unavailable}
              onClick={() => {
                setDraft(getDateRangePreset(preset.key, new Date(), timeZone));
                setError(null);
              }}
              className="rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-600 hover:border-blue-300 hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
              data-testid={`date-range-preset-${preset.key}`}
            >
              {preset.label}
            </button>
          );
        })}
      </div>

      {error ? (
        <p className="mt-2 text-xs text-red-600" role="alert">
          {t(`chart.dateRange.errors.${error}`)}
        </p>
      ) : (
        <p
          className="mt-2 text-xs text-gray-500"
          data-testid="date-range-summary"
        >
          {t("chart.dateRange.summary", {
            start: value.start,
            end: value.end,
            days: countInclusiveDays(value),
          })}
        </p>
      )}
    </div>
  );
}
