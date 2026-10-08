import { expect, test, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import type { PaperView } from "../src/services/paperLedger";
const backend = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:18096";
const headers = { "X-Financial-Agent-Local": "1" };

async function create(page: Page, slip = "10") {
  await page.setViewportSize({ width: 1800, height: 1200 });
  await page.addInitScript(() =>
    localStorage.setItem("portfolio:leftWidth", "700"),
  );
  await page.goto("/");
  await page.getByTestId("nav-portfolio").click();
  await page.getByTestId("paper-open").click();
  await page.getByTestId("paper-new").click();
  await expect(page.getByTestId("paper-initial-cash")).toHaveValue("");
  await expect(page.getByTestId("paper-create")).toBeDisabled();
  await page.getByTestId("paper-name").fill("Recorded manual PAPER");
  await page.getByTestId("paper-initial-cash").fill("10000.00");
  await page.getByTestId("paper-symbols").fill("AAPL, MSFT");
  await page.getByTestId("paper-commission").fill("0");
  await page.getByTestId("paper-slippage").fill(slip);
  await page.getByTestId("paper-create-ack").check();
  const saved = page.waitForResponse(
    (r) =>
      r.url().endsWith("/paper/experiments") && r.request().method() === "POST",
  );
  await page.getByTestId("paper-create").click();
  const response = await saved;
  expect(response.status()).toBe(200);
  await expect(page.getByTestId("paper-cash")).toHaveText("10000.00");
  return (await response.json()) as PaperView;
}
async function trade(
  page: Page,
  side: string,
  quantity: string,
  price: string,
  symbol = "AAPL",
) {
  await page.getByTestId("paper-entry-kind").selectOption("trade");
  await page.getByTestId("paper-entry-symbol").selectOption(symbol);
  await page.getByTestId("paper-trade-side").selectOption(side);
  await page.getByTestId("paper-trade-quantity").fill(quantity);
  await page.getByTestId("paper-trade-price").fill(price);
  await page.getByTestId("paper-entry-ack").check();
  const saved = page.waitForResponse(
    (r) => r.url().endsWith("/journal") && r.request().method() === "POST",
  );
  await page.getByTestId("paper-journal-submit").click();
  return saved;
}
async function refresh(page: Page) {
  await page.getByTestId("paper-reconciliation-ack").check();
  const saved = page.waitForResponse(
    (r) => r.url().endsWith("/valuation") && r.request().method() === "POST",
  );
  await page.getByTestId("paper-refresh").click();
  return saved;
}
async function shot(page: Page, name: string) {
  if (process.env.UPDATE_E2E_EVIDENCE !== "true") return;
  const directory = path.resolve("../docs/features/assets/idq-008-a");
  await mkdir(directory, { recursive: true });
  await page
    .getByTestId("paper-details")
    .evaluate((element) =>
      element.scrollIntoView({ block: "center", inline: "nearest" }),
    );
  await page
    .getByTestId("paper-details")
    .screenshot({ path: path.join(directory, name), animations: "disabled" });
}

test.describe("Manual offline PAPER @real-stack", () => {
  test.setTimeout(180000);
  test.beforeEach(async ({ request }) =>
    expect((await request.post(`${backend}/api/test/paper/reset`)).ok()).toBe(
      true,
    ),
  );
  test("manual buy/mark/sell/reload exports exact cash while real account and models stay untouched", async ({
    page,
    request,
  }) => {
    const before = (await (
      await request.get(`${backend}/api/test/paper/audit`)
    ).json()) as { market_requests: number; real: unknown };
    const made = await create(page);
    const afterCreate = (await (
      await request.get(`${backend}/api/test/paper/audit`)
    ).json()) as { market_requests: number };
    expect(afterCreate.market_requests).toBe(before.market_requests);
    const bought = await trade(page, "buy", "10", "100");
    expect(bought.status()).toBe(200);
    await expect(page.getByTestId("paper-cash")).toHaveText("8999.00");
    await expect(page.getByTestId("paper-nav")).toContainText("Not valued yet");
    const valued = await refresh(page);
    expect(valued.status()).toBe(200);
    await expect(page.getByTestId("paper-nav")).toContainText("9999.00");
    await shot(page, "01-manual-paper-nav.png");
    const calls = (await (
      await request.get(`${backend}/api/test/paper/audit`)
    ).json()) as { market_requests: number };
    const replay = await request.post(valued.url(), {
      headers: { ...headers, "Content-Type": "application/json" },
      data: valued.request().postData() ?? "",
    });
    expect(replay.status()).toBe(200);
    await page.reload();
    await page.getByTestId("nav-portfolio").click();
    await page.getByTestId("paper-open").click();
    await page
      .getByTestId("paper-account-select")
      .selectOption(made.experiment.experiment_id);
    await expect(page.getByTestId("paper-nav")).toContainText("9999.00");
    expect(
      (
        (await (
          await request.get(`${backend}/api/test/paper/audit`)
        ).json()) as { market_requests: number }
      ).market_requests,
    ).toBe(calls.market_requests);
    expect((await trade(page, "sell", "10", "110")).status()).toBe(200);
    await expect(page.getByTestId("paper-cash")).toHaveText("10097.90");
    await expect(page.getByTestId("paper-valuation")).toHaveAttribute(
      "data-stale",
      "true",
    );
    expect((await refresh(page)).status()).toBe(200);
    await expect(page.getByTestId("paper-nav")).toContainText("10097.90");
    await page.getByTestId("paper-export").click();
    await expect(page.getByTestId("paper-manifest")).toContainText(
      "manual_unverified_scenario",
    );
    const after = (await (
      await request.get(`${backend}/api/test/paper/audit`)
    ).json()) as { real: unknown };
    expect(after.real).toEqual(before.real);
  });
  test("missing mark and overdraft remain unavailable/rejected, never zero-priced holdings", async ({
    page,
    request,
  }) => {
    await create(page, "0");
    expect((await trade(page, "buy", "10", "100")).status()).toBe(200);
    expect((await trade(page, "buy", "5", "100", "MSFT")).status()).toBe(200);
    expect(
      (await request.post(`${backend}/api/test/paper/market/missing`)).ok(),
    ).toBe(true);
    expect((await refresh(page)).status()).toBe(200);
    await expect(page.getByTestId("paper-valuation")).toHaveAttribute(
      "data-status",
      "unavailable",
    );
    await expect(page.getByTestId("paper-nav")).toContainText("Unavailable");
    await expect(page.getByTestId("paper-valuation")).toContainText("1/2");
    const rejected = await trade(page, "buy", "100", "100");
    expect(rejected.status()).toBe(409);
    await expect(page.getByTestId("paper-journal-error")).toContainText(
      "PAPER_CASH_INSUFFICIENT",
    );
    await expect(page.getByTestId("paper-cash")).toHaveText("8500.00");
    await shot(page, "02-unavailable-paper-nav.png");
  });
  test("manual split/dividend reconciliation preserves basis and does not double count income", async ({
    page,
    request,
  }) => {
    await create(page, "0");
    expect((await trade(page, "buy", "10", "100")).status()).toBe(200);
    await page.getByTestId("paper-entry-kind").selectOption("split");
    await page.getByTestId("paper-entry-symbol").selectOption("AAPL");
    await page.getByTestId("paper-split-numerator").fill("2");
    await page.getByTestId("paper-split-denominator").fill("1");
    await page.getByTestId("paper-entry-ack").check();
    const split = page.waitForResponse(
      (r) => r.url().endsWith("/journal") && r.request().method() === "POST",
    );
    await page.getByTestId("paper-journal-submit").click();
    expect((await split).status()).toBe(200);
    await expect(page.getByTestId("paper-position-AAPL")).toContainText(
      "20 shares",
    );
    await expect(page.getByTestId("paper-position-AAPL")).toContainText(
      "1000.00",
    );
    await page.getByTestId("paper-entry-kind").selectOption("dividend");
    await page.getByTestId("paper-entry-symbol").selectOption("AAPL");
    await page.getByTestId("paper-dividend-gross").fill("1");
    await page.getByTestId("paper-dividend-tax").fill("0");
    await page.getByTestId("paper-entry-ack").check();
    const dividend = page.waitForResponse(
      (r) => r.url().endsWith("/journal") && r.request().method() === "POST",
    );
    await page.getByTestId("paper-journal-submit").click();
    expect((await dividend).status()).toBe(200);
    await expect(page.getByTestId("paper-cash")).toHaveText("9020.00");
    expect(
      (await request.post(`${backend}/api/test/paper/market/dividend`)).ok(),
    ).toBe(true);
    expect((await refresh(page)).status()).toBe(200);
    await expect(page.getByTestId("paper-nav")).toContainText("10000.00");
  });
  test("storage failure cannot claim a paper booking; recovery appends only once", async ({
    page,
    request,
  }) => {
    const made = await create(page, "0");
    const root = `${backend}/api/portfolio/paper/experiments/${made.experiment.experiment_id}`;
    expect(
      (await request.post(`${backend}/api/test/paper/fault/storage`)).ok(),
    ).toBe(true);
    await page.getByTestId("paper-entry-kind").selectOption("trade");
    await page.getByTestId("paper-entry-symbol").selectOption("AAPL");
    await page.getByTestId("paper-trade-side").selectOption("buy");
    await page.getByTestId("paper-trade-quantity").fill("10");
    await page.getByTestId("paper-trade-price").fill("100");
    await page.getByTestId("paper-entry-ack").check();
    const sent = page.waitForRequest(
      (r) => r.url().endsWith("/journal") && r.method() === "POST",
    );
    await page.getByTestId("paper-journal-submit").click();
    const failed = await sent;
    await expect(page.getByTestId("paper-journal-error")).toBeVisible();
    // Outer storage faults may hide the 500 behind CORS; verify both UI error
    // and real API status while leaving the tested application path unmocked.
    expect(
      (
        await request.post(failed.url(), {
          headers: { ...headers, "Content-Type": "application/json" },
          data: failed.postData() ?? "",
        })
      ).status(),
    ).toBe(500);
    expect(
      ((await (await request.get(root)).json()) as PaperView).experiment
        .sequence,
    ).toBe(1);
    await expect(page.getByTestId("paper-cash")).toHaveText("10000.00");
    expect(
      (await request.post(`${backend}/api/test/paper/fault/none`)).ok(),
    ).toBe(true);
    expect((await trade(page, "buy", "10", "100")).status()).toBe(200);
    const result = (await (await request.get(root)).json()) as PaperView;
    expect(result.experiment.events).toHaveLength(2);
    await expect(page.getByTestId("paper-cash")).toHaveText("9000.00");
  });
  test("concurrent cash spending and delayed Mongo expiry cannot commit fictitious events", async ({
    page,
    request,
  }) => {
    const made = await create(page, "0");
    const root = `${backend}/api/portfolio/paper/experiments/${made.experiment.experiment_id}`;
    const body = {
      expected_sequence: 1,
      confirm: true,
      acknowledgment: "manual-scenario-not-ai-approved-or-market-fill",
      entry: {
        kind: "trade",
        symbol: "AAPL",
        side: "buy",
        quantity: "60",
        reference_price: "100",
      },
    };
    const answers = await Promise.all(
      ["race-one", "race-two"].map((request_id) =>
        request.post(`${root}/journal`, {
          headers,
          data: { ...body, request_id },
        }),
      ),
    );
    expect(answers.map((a) => a.status()).sort()).toEqual([200, 409]);
    await page.getByTestId("paper-reload").click();
    await expect(page.getByTestId("paper-cash")).toHaveText("4000.00");
    expect(
      (await request.post(`${backend}/api/test/paper/fault/expiry`)).ok(),
    ).toBe(true);
    expect((await refresh(page)).status()).toBe(409);
    await expect(page.getByTestId("paper-valuation-error")).toContainText(
      "expired",
    );
    const stored = (await (await request.get(root)).json()) as PaperView;
    expect(stored.experiment.events).toHaveLength(2);
    expect(stored.valuation).toBeNull();
  });
});
