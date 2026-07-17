import { expect, test, type Page, type Route } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const evidenceDir = path.resolve(
  process.cwd(),
  "..",
  "docs",
  "features",
  "assets",
  "uaw-004",
);
const updateEvidence = process.env.UPDATE_E2E_EVIDENCE === "true";

async function openWatchlist(page: Page) {
  await page.goto("/");
  await page.getByTestId("nav-portfolio").click();
  await expect(page.getByTestId("watchlist-panel")).toBeVisible();
  await expect(page.getByTestId("watchlist-row-AAPL")).toBeVisible();
}

test("Watchlist analysis timestamp persists and refreshes @uaw004", async ({
  page,
}) => {
  test.setTimeout(90_000);
  mkdirSync(evidenceDir, { recursive: true });

  let blockNextWatchlistGet = false;
  let blockedRefetchStarted = false;
  let releaseRefetch: (() => void) | undefined;
  const refetchGate = new Promise<void>((resolve) => {
    releaseRefetch = resolve;
  });

  await page.route("**/api/watchlist", async (route: Route) => {
    if (route.request().method() === "GET" && blockNextWatchlistGet) {
      blockNextWatchlistGet = false;
      blockedRefetchStarted = true;
      await refetchGate;
    }
    await route.continue();
  });

  await openWatchlist(page);
  const timestamp = page.getByTestId("watchlist-last-analyzed-AAPL");
  await expect(timestamp).toHaveAttribute("data-last-analyzed-at", "");

  blockNextWatchlistGet = true;
  const analysisResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().includes("/api/watchlist/analyze?symbol=AAPL"),
  );
  await page.getByTestId("watchlist-analyze-AAPL").click();

  const response = await analysisResponse;
  expect(response.status()).toBe(202);
  const body = (await response.json()) as {
    watchlist_updated: boolean;
    last_analyzed_at: string;
  };
  expect(body.watchlist_updated).toBe(true);
  expect(body.last_analyzed_at).toBeTruthy();

  await expect.poll(() => blockedRefetchStarted).toBe(true);
  await expect(timestamp).toHaveAttribute(
    "data-last-analyzed-at",
    body.last_analyzed_at,
  );

  if (updateEvidence) {
    await page.getByTestId("watchlist-panel").screenshot({
      path: path.join(evidenceDir, "01-last-analyzed-updated.png"),
    });
  }

  const refetchResponse = page.waitForResponse(
    (candidate) =>
      candidate.request().method() === "GET" &&
      candidate.url().endsWith("/api/watchlist"),
  );
  releaseRefetch?.();
  await refetchResponse;

  await page.reload();
  await page.getByTestId("nav-portfolio").click();
  await expect(page.getByTestId("watchlist-row-AAPL")).toBeVisible();
  const restoredTimestamp = page.getByTestId("watchlist-last-analyzed-AAPL");
  await expect(restoredTimestamp).not.toHaveAttribute(
    "data-last-analyzed-at",
    "",
  );

  if (updateEvidence) {
    await page.getByTestId("watchlist-panel").screenshot({
      path: path.join(evidenceDir, "02-timestamp-persists-after-reload.png"),
    });
  }
});
