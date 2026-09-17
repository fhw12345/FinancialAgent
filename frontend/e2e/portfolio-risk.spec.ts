import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";
const backend = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:18096";
const headers = { "X-Financial-Agent-Local": "1" };
async function setup(page: Page, request: APIRequestContext) {
  expect((await request.post(`${backend}/api/test/risk/reset`)).ok()).toBe(
    true,
  );
  await page.setViewportSize({ width: 1800, height: 1300 });
  await page.addInitScript(() => {
    localStorage.setItem("portfolio:leftWidth", "700");
    localStorage.setItem("portfolio:rightWidth", "240");
  });
  await page.goto("/");
  await page.getByTestId("nav-portfolio").click();
}
async function shot(page: Page, name: string) {
  if (process.env.UPDATE_E2E_EVIDENCE !== "true") return;
  const directory = path.resolve("../docs/features/assets/idq-002");
  await mkdir(directory, { recursive: true });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: path.join(directory, name),
    fullPage: true,
    animations: "disabled",
  });
}
async function confirm(page: Page) {
  const panel = page.getByTestId("portfolio-risk-panel");
  await panel
    .getByRole("button", {
      name: "Risk preview policy / 预览限额",
      exact: true,
    })
    .click();
  for (const [key, value] of Object.entries({
    max_position_weight: ".1",
    max_sector_weight: ".15",
    min_cash_weight: ".1",
    max_turnover: "1",
    risk_per_trade_weight: ".01",
    lot_size: ".1",
    fee_bps: "0",
    slippage_bps: "0",
  }))
    await panel.getByTestId(`risk-policy-${key}`).fill(value);
  await panel.getByRole("checkbox").check();
  const response = page.waitForResponse(
    (r) => r.url().endsWith("/risk-policy") && r.request().method() === "PUT",
  );
  await panel
    .getByRole("button", { name: "Confirm risk policy", exact: true })
    .click();
  expect((await response).status()).toBe(200);
  await panel
    .getByRole("button", {
      name: "Risk preview policy / 预览限额",
      exact: true,
    })
    .click();
}
test.describe("Portfolio risk @real-stack", () => {
  test.setTimeout(120000);
  test("cash and fractional positions have separate reproducible account/invested sigma", async ({
    page,
    request,
  }) => {
    await setup(page, request);
    const panel = page.getByTestId("portfolio-risk-panel");
    await panel.getByTestId("refresh-portfolio-risk").click();
    await expect(panel.getByTestId("risk-availability")).toHaveText(
      "complete",
      { timeout: 45000 },
    );
    await expect(panel.getByTestId("risk-equity")).toHaveText("$500.00");
    await expect(panel.getByTestId("account-sigma")).toHaveText("3.2017%");
    await expect(panel.getByTestId("invested-sigma")).toHaveText("32.0169%");
    await expect(panel.getByTestId("invested-hhi")).toHaveText("1.0000");
    const holdings = (await (
      await request.get(`${backend}/api/portfolio/holdings`)
    ).json()) as { quantity: number }[];
    expect(holdings[0].quantity).toBe(0.5);
    await panel.scrollIntoViewIfNeeded();
    await shot(page, "01-account-risk.png");
    await page.reload();
    await page.getByTestId("nav-portfolio").click();
    await expect(panel.getByTestId("account-sigma")).toHaveText("3.2017%");
    await panel.getByTestId("refresh-portfolio-risk").click();
    await expect(panel.getByTestId("account-sigma")).toHaveText("3.2017%");
  });
  test("explicit policy rejects whole posttrade exposure without changing holdings", async ({
    page,
    request,
  }) => {
    await setup(page, request);
    await confirm(page);
    await page.getByTestId("analyze-holdings").click();
    await expect(page.getByTestId("holdings-analysis-status")).toHaveAttribute(
      "data-run-status",
      "done",
      { timeout: 60000 },
    );
    const batch = page.getByTestId("assessment-batch");
    await expect(batch).toHaveAttribute("data-readiness", "blocked", {
      timeout: 15000,
    });
    await expect(batch.getByTestId("allocation-receipt")).toContainText(
      "POSITION_LIMIT:AAPL",
    );
    await expect(batch.getByTestId("risk-policy-limits")).toContainText(
      "Max position: 10.0000%",
    );
    await expect(batch.getByTestId("risk-policy-limits")).toContainText(
      "max sector: 15.0000%",
    );
    await expect(batch.getByTestId("allocation-receipt")).toContainText(
      "SECTOR_LIMIT:Technology",
    );
    await expect(batch.getByTestId("allocation-receipt")).toContainText(
      "0.5 → 0.9",
    );
    await batch.scrollIntoViewIfNeeded();
    await shot(page, "02-posttrade-blocked.png");
    const rows = (await (
      await request.get(`${backend}/api/portfolio/assessments`)
    ).json()) as { assessment_id: string; actionable: boolean }[];
    expect(rows[0].actionable).toBe(false);
    expect(
      (
        await request.post(
          `${backend}/api/portfolio/assessments/${rows[0].assessment_id}/approve`,
        )
      ).status(),
    ).toBe(409);
    const holdings = (await (
      await request.get(`${backend}/api/portfolio/holdings`)
    ).json()) as { quantity: number }[];
    expect(holdings[0].quantity).toBe(0.5);
    await page.reload();
    await page.getByTestId("nav-portfolio").click();
    await expect(batch).toHaveAttribute("data-readiness", "blocked");
  });
  test("policy CAS and account changes cannot refresh old receipts silently", async ({
    page,
    request,
  }) => {
    await setup(page, request);
    await confirm(page);
    const state = (await (
      await request.get(`${backend}/api/portfolio/risk-policy`)
    ).json()) as { revision: number; policy: Record<string, number> };
    expect(
      (
        await request.put(`${backend}/api/portfolio/risk-policy`, {
          headers,
          data: { expected_revision: 0, confirm: true, policy: state.policy },
        })
      ).status(),
    ).toBe(409);
    await page.getByTestId("refresh-portfolio-risk").click();
    await expect(
      page.getByTestId("portfolio-risk-panel").getByTestId("risk-availability"),
    ).toHaveText("complete", { timeout: 45000 });
    const holdings = (await (
      await request.get(`${backend}/api/portfolio/holdings`)
    ).json()) as { holding_id: string }[];
    expect(
      (
        await request.patch(
          `${backend}/api/portfolio/holdings/${holdings[0].holding_id}`,
          { data: { quantity: 0.75 } },
        )
      ).ok(),
    ).toBe(true);
    await page.reload();
    await page.getByTestId("nav-portfolio").click();
    await expect(page.getByTestId("portfolio-risk-panel")).toContainText(
      "ACCOUNT_CHANGED",
    );
  });
});
