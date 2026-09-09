/** PH-002: real visible refresh -> prefetch -> calculation -> Mongo/Redis. */
import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

test("visible Insights refresh consumes one shared prefetch @ph002 @real-stack", async ({
  page,
  request,
}) => {
  test.setTimeout(90_000);
  const backend = process.env.E2E_BACKEND_URL;
  expect(backend).toBeTruthy();
  await page.setViewportSize({ width: 1440, height: 1200 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByTestId("nav-insights").click();
  await page.getByRole("button", { name: /AI Sector Risk/ }).click();
  await expect(
    page.getByText("AI Price Anomaly", { exact: true }),
  ).toBeVisible();
  expect((await request.post(`${backend}/api/test/insights/reset`)).ok()).toBe(
    true,
  );
  const refresh = page.getByTestId("refresh-insight-category");
  const response = page.waitForResponse(
    (r) =>
      r.request().method() === "POST" &&
      r.url().endsWith("/api/insights/ai_sector_risk/refresh"),
  );
  await refresh.click();
  await expect(refresh).toBeDisabled();
  expect(
    (await request.post(`${backend}/api/test/insights/release`)).ok(),
  ).toBe(true);
  expect((await response).ok()).toBe(true);
  await expect(refresh).toBeEnabled();
  await expect(
    page.getByText("Fed Expectations", { exact: true }),
  ).toBeVisible();
  const evidenceResponse = await request.get(
    `${backend}/api/test/insights/evidence`,
  );
  expect(evidenceResponse.ok()).toBe(true);
  const evidence = (await evidenceResponse.json()) as {
    calls: Record<string, number>;
    outputs: string[];
    prefetch_requests: unknown[];
    snapshot: {
      category_id: string;
      composite_score: number;
      metrics: Record<string, unknown>;
      prefetch_errors: Record<string, string>;
    };
  };
  expect(evidence.prefetch_requests).toEqual([
    {
      symbols: ["NVDA", "MSFT", "AMD", "PLTR"],
      treasury_maturities: ["2y", "10y"],
      include_news: true,
      include_ipo: true,
    },
  ]);
  expect(evidence.calls).toMatchObject({
    "ohlcv:NVDA": 1,
    "ohlcv:MSFT": 1,
    "ohlcv:AMD": 1,
    "ohlcv:PLTR": 1,
    "treasury:2year": 1,
    "treasury:10year": 1,
    news: 1,
    ipo: 1,
  });
  expect(evidence.outputs).toEqual(["full", "full", "full", "full"]);
  expect(evidence.snapshot.category_id).toBe("ai_sector_risk");
  expect(Object.keys(evidence.snapshot.metrics)).toHaveLength(7);
  expect(evidence.snapshot.prefetch_errors).toEqual({});
  const categoryResponse = await request.get(
    `${backend}/api/insights/ai_sector_risk`,
  );
  const category = (await categoryResponse.json()) as {
    composite: { score: number; interpretation: string };
  };
  expect(category.composite.score).toBe(evidence.snapshot.composite_score);
  await expect(
    page.getByText(category.composite.interpretation, { exact: true }),
  ).toBeVisible();
  if (process.env.UPDATE_E2E_EVIDENCE === "true") {
    const dir = path.resolve("..", "docs", "features", "assets", "ph-002");
    mkdirSync(dir, { recursive: true });
    await page.screenshot({
      path: path.join(dir, "01-shared-prefetch-refresh.png"),
      fullPage: true,
      animations: "disabled",
    });
  }
});
