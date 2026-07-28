import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DateRangePicker } from "../DateRangePicker";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string | number>) => {
      if (key === "chart.dateRange.summary") {
        return `${values?.start} to ${values?.end} (${values?.days} days)`;
      }
      return key;
    },
  }),
}));

describe("DateRangePicker", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2024-01-15T12:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("applies a preset without mutating the current range first", () => {
    const onApply = vi.fn();
    render(
      <DateRangePicker
        value={{ start: "2024-01-01", end: "2024-01-15" }}
        interval="1d"
        symbol="AAPL"
        onApply={onApply}
      />,
    );

    fireEvent.click(screen.getByTestId("date-range-preset-1w"));
    expect(onApply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("date-range-apply"));

    expect(onApply).toHaveBeenCalledWith({
      start: "2024-01-09",
      end: "2024-01-15",
    });
  });

  it("keeps the applied range when the draft is invalid", () => {
    const onApply = vi.fn();
    render(
      <DateRangePicker
        value={{ start: "2024-01-01", end: "2024-01-15" }}
        interval="1d"
        symbol="AAPL"
        onApply={onApply}
      />,
    );

    fireEvent.change(screen.getByTestId("date-range-start"), {
      target: { value: "2024-01-15" },
    });
    fireEvent.change(screen.getByTestId("date-range-end"), {
      target: { value: "2024-01-01" },
    });
    fireEvent.click(screen.getByTestId("date-range-apply"));

    expect(screen.getByRole("alert").textContent).toContain(
      "chart.dateRange.errors.invalidOrder",
    );
    expect(onApply).not.toHaveBeenCalled();
  });

  it("resets to the interval default and applies immediately", () => {
    const onApply = vi.fn();
    render(
      <DateRangePicker
        value={{ start: "2024-01-01", end: "2024-01-15" }}
        interval="1w"
        symbol="AAPL"
        onApply={onApply}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "chart.dateRange.reset" }),
    );

    expect(onApply).toHaveBeenCalledWith({
      start: "2022-01-15",
      end: "2024-01-15",
    });
  });

  it("disables presets outside the intraday provider window", () => {
    render(
      <DateRangePicker
        value={{ start: "2024-01-15", end: "2024-01-15" }}
        interval="1m"
        symbol="AAPL"
        onApply={vi.fn()}
      />,
    );

    expect(
      screen.getByTestId("date-range-preset-1m").hasAttribute("disabled"),
    ).toBe(false);
    expect(
      screen.getByTestId("date-range-preset-3m").hasAttribute("disabled"),
    ).toBe(true);
    expect(screen.getByTestId("date-range-summary").textContent).toContain(
      "2024-01-15 to 2024-01-15 (1 days)",
    );
  });
});
