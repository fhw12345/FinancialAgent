import { mkdirSync } from "fs";
import path from "path";
import { expect, test } from "@playwright/test";

function resolveBackendUrl() {
  if (process.env.E2E_BACKEND_URL) return process.env.E2E_BACKEND_URL;
  const baseUrl = process.env.PLAYWRIGHT_BASE_URL ?? "";
  return baseUrl.includes(":3008")
    ? "http://host.docker.internal:18089"
    : "http://host.docker.internal:18081";
}

const backendUrl = resolveBackendUrl();
const evidenceDir = path.join(
  process.cwd(),
  "..",
  "docs",
  "features",
  "assets",
  "symbol-date-range",
);
const updateEvidence = process.env.UPDATE_E2E_EVIDENCE === "true";

test("custom range drives chart, technical analysis, and persistence", async ({
  page,
}) => {
  test.setTimeout(120_000);
  mkdirSync(evidenceDir, { recursive: true });
  await page.addInitScript(() =>
    window.localStorage.setItem("i18nextLng", "en"),
  );

  const priceRequests: string[] = [];
  let fibonacciPayload: Record<string, unknown> | null = null;

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
        latest_trading_day: "2026-06-30",
        previous_close: 209,
        change: 1,
        change_percent: "0.48%",
        timestamp: "2026-06-30T20:00:00Z",
      }),
    });
  });
  await page.route("**/api/market/price/AAPL?*", async (route) => {
    priceRequests.push(route.request().url());
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        symbol: "AAPL",
        interval: "1d",
        data: [
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
        ],
        last_updated: "2026-06-30T20:00:00Z",
      }),
    });
  });
  await page.route("**/api/analysis/fibonacci", async (route) => {
    fibonacciPayload = route.request().postDataJSON() as Record<
      string,
      unknown
    >;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        symbol: "AAPL",
        start_date: "2026-06-01",
        end_date: "2026-06-30",
        timeframe: "1d",
        current_price: 210,
        analysis_date: "2026-06-30T20:00:00Z",
        fibonacci_levels: [
          {
            level: 0.618,
            price: 205,
            percentage: "61.8%",
            is_key_level: true,
          },
        ],
        market_structure: {
          trend_direction: "uptrend",
          swing_high: { price: 212, date: "2026-06-30" },
          swing_low: { price: 198, date: "2026-06-01" },
          structure_quality: "high",
          phase: "expansion",
        },
        confidence_score: 0.9,
        pressure_zone: null,
        trend_strength: "strong",
        analysis_summary: "CUSTOM_RANGE_FIBONACCI_OK",
        key_insights: ["Custom date range applied."],
        raw_data: { timeframe: "1d", top_trends: [] },
      }),
    });
  });

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByTestId("nav-chat").click();
  const symbolInput = page.getByTestId("symbol-search-input");
  await symbolInput.fill("AAPL");
  await symbolInput.press("Enter");
  await expect(page.getByTestId("date-range-picker")).toBeVisible();

  await page.getByTestId("date-range-start").fill("2026-06-01");
  await page.getByTestId("date-range-end").fill("2026-06-30");
  await page.getByTestId("date-range-apply").click();

  await expect
    .poll(() =>
      priceRequests.some((url) => {
        const requestUrl = new URL(url);
        return (
          requestUrl.searchParams.get("start_date") === "2026-06-01" &&
          requestUrl.searchParams.get("end_date") === "2026-06-30"
        );
      }),
    )
    .toBe(true);
  await expect(page.getByTestId("date-range-summary")).toContainText(
    /2026-06-01.*2026-06-30.*30/,
  );

  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "01-custom-range-applied.png"),
    });
  }

  await page.getByTestId("analysis-fibonacci").click();
  await expect
    .poll(() => fibonacciPayload)
    .toMatchObject({
      symbol: "AAPL",
      start_date: "2026-06-01",
      end_date: "2026-06-30",
      timeframe: "1d",
    });
  await expect(
    page.getByRole("heading", { name: /Fibonacci Analysis - AAPL/ }),
  ).toBeVisible();

  await expect
    .poll(async () =>
      page.evaluate(async (url) => {
        interface PersistedMessage {
          role?: string;
          metadata?: { raw_data?: Record<string, unknown> };
        }
        const list = (await (
          await fetch(`${url}/api/chat/chats?page=1&page_size=20`)
        ).json()) as { chats?: Array<{ chat_id: string }> };
        const chatId = list.chats?.[0]?.chat_id;
        if (!chatId) return null;
        const detail = (await (
          await fetch(`${url}/api/chat/chats/${chatId}`)
        ).json()) as {
          chat?: {
            ui_state?: {
              current_symbol?: string | null;
              current_interval?: string;
              current_date_range?: {
                start?: string | null;
                end?: string | null;
              };
            };
          };
          messages?: PersistedMessage[];
        };
        const message = detail.messages?.find(
          (item) =>
            item.role === "assistant" &&
            item.metadata?.raw_data?.start_date === "2026-06-01",
        );
        return {
          analysis: message?.metadata?.raw_data ?? null,
          uiState: detail.chat?.ui_state ?? null,
        };
      }, backendUrl),
    )
    .toMatchObject({
      analysis: {
        symbol: "AAPL",
        start_date: "2026-06-01",
        end_date: "2026-06-30",
        timeframe: "1d",
      },
      uiState: {
        current_symbol: "AAPL",
        current_interval: "1d",
        current_date_range: {
          start: "2026-06-01",
          end: "2026-06-30",
        },
      },
    });

  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "02-fibonacci-range-persisted.png"),
    });
  }
});

test("date controls remain available when a valid range has no bars", async ({
  page,
}) => {
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
        volume: 1,
        latest_trading_day: "2026-06-30",
        previous_close: 209,
        change: 1,
        change_percent: "0.48%",
        timestamp: "2026-06-30T20:00:00Z",
      }),
    });
  });
  await page.route("**/api/market/price/AAPL?*", async (route) => {
    await route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({ detail: "No data in requested range" }),
    });
  });

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByTestId("nav-chat").click();
  const symbolInput = page.getByTestId("symbol-search-input");
  await symbolInput.fill("AAPL");
  await symbolInput.press("Enter");

  await expect(page.getByTestId("date-range-picker")).toBeVisible();
  await expect(page.getByTestId("date-range-apply")).toBeEnabled();
});
