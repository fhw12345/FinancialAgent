import { mkdirSync } from "fs";
import path from "path";
import { expect, test } from "@playwright/test";

const evidenceDir = path.join(
  process.cwd(),
  "..",
  "docs",
  "features",
  "assets",
  "chart-volume-overlay",
);
const updateEvidence = process.env.UPDATE_E2E_EVIDENCE === "true";

const bars = [
  {
    time: "2026-06-01",
    open: 200,
    high: 204,
    low: 198,
    close: 203,
    volume: 42_000_000,
  },
  {
    time: "2026-06-15",
    open: 204,
    high: 208,
    low: 202,
    close: 207,
    volume: 45_000_000,
  },
  {
    time: "2026-06-30",
    open: 208,
    high: 212,
    low: 207,
    close: 210,
    volume: 50_000_000,
  },
  {
    time: "2026-07-07",
    open: 211,
    high: 214,
    low: 209,
    close: 210,
    volume: 48_000_000,
  },
];

test("volume bars stay synchronized across range and interval changes", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1440, height: 1100 });
  mkdirSync(evidenceDir, { recursive: true });

  await page.route("**/api/market/search?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        query: "AAPL",
        results: [
          {
            symbol: "AAPL",
            name: "Apple Inc.",
            exchange: "NASDAQ",
            type: "EQUITY",
            match_type: "exact",
            confidence: 1,
          },
        ],
      }),
    });
  });
  await page.route("**/api/market/quote/AAPL", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        symbol: "AAPL",
        price: 210,
        open: 208,
        high: 212,
        low: 207,
        volume: 50_000_000,
        latest_trading_day: "2026-07-07",
        previous_close: 209,
        change: 1,
        change_percent: "0.48%",
        timestamp: "2026-07-07T20:00:00Z",
      }),
    });
  });
  await page.route("**/api/market/price/AAPL?*", async (route) => {
    const requestUrl = new URL(route.request().url());
    const interval = requestUrl.searchParams.get("interval");
    const startDate = requestUrl.searchParams.get("start_date");
    const responseBars =
      interval === "1w"
        ? bars
        : startDate === "2026-06-15"
          ? bars.slice(1, 3)
          : bars.slice(0, 3);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        symbol: "AAPL",
        interval: interval ?? "1d",
        data: responseBars,
        last_updated: "2026-07-07T20:00:00Z",
      }),
    });
  });

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByTestId("nav-chat").click();
  const symbolInput = page.getByTestId("symbol-search-input");
  await symbolInput.fill("AAPL");
  await symbolInput.press("Enter");

  const chart = page.getByTestId("trading-chart-container");
  await expect(chart).toHaveAttribute("data-volume-overlay", "ready");
  await expect(chart).toHaveAttribute("data-volume-bars", "3");
  await expect(page.getByTestId("volume-overlay-summary")).toContainText("3");
  const chartInstance = await chart.getAttribute("data-chart-instance");
  if (chartInstance === null) {
    throw new Error("Chart instance marker was not initialized.");
  }

  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "01-volume-overlay-initial.png"),
    });
  }

  await page.getByTestId("date-range-start").fill("2026-06-15");
  await page.getByTestId("date-range-end").fill("2026-06-30");
  await page.getByTestId("date-range-apply").click();
  await expect(chart).toHaveAttribute("data-volume-bars", "2");
  await expect(chart).toHaveAttribute("data-chart-instance", chartInstance);

  await page.getByTestId("chart-interval-1w").click();
  await expect(chart).toHaveAttribute("data-volume-bars", "4");
  await expect(chart).toHaveAttribute("data-chart-instance", chartInstance);
  await expect(page.getByTestId("volume-overlay-summary")).toContainText("4");

  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "02-volume-overlay-weekly.png"),
    });
  }
});
