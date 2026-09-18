import { expect, type Page, type APIRequestContext } from "@playwright/test";
const backend = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:18096";
export async function setupStrategy(
  page: Page,
  request: APIRequestContext,
  mode: string,
  options: {
    resetPath?: string;
    peers?: string;
    discount?: string;
    minCash?: string;
  } = {},
) {
  expect(
    (
      await request.post(
        `${backend}${options.resetPath ?? "/api/test/strategy/reset"}/${mode}`,
      )
    ).ok(),
  ).toBe(true);
  await page.setViewportSize({ width: 1800, height: 1300 });
  await page.addInitScript(() => {
    localStorage.setItem("portfolio:leftWidth", "700");
    localStorage.setItem("portfolio:rightWidth", "240");
  });
  await page.goto("/");
  await page.getByTestId("nav-portfolio").click();
  await expect(page.getByTestId("active-research-strategy")).toContainText(
    "Not enabled",
  );
  // Explicit synthetic values, never production/user defaults.
  const risk = page.getByTestId("portfolio-risk-panel");
  await risk
    .getByRole("button", {
      name: "Risk preview policy / 预览限额",
      exact: true,
    })
    .click();
  for (const [key, value] of Object.entries({
    max_position_weight: "1",
    max_sector_weight: "1",
    min_cash_weight: options.minCash ?? "0",
    max_turnover: "2",
    risk_per_trade_weight: ".01",
    lot_size: ".1",
    fee_bps: "0",
    slippage_bps: "0",
  }))
    await risk.getByTestId(`risk-policy-${key}`).fill(value);
  await risk.getByRole("checkbox").check();
  const saved = page.waitForResponse(
    (r) => r.url().endsWith("/risk-policy") && r.request().method() === "PUT",
  );
  await risk
    .getByRole("button", { name: "Confirm risk policy", exact: true })
    .click();
  expect((await saved).status()).toBe(200);
  await risk
    .getByRole("button", {
      name: "Risk preview policy / 预览限额",
      exact: true,
    })
    .click();
  await page.getByTestId("edit-research-strategy").click();
  const panel = page.getByTestId("research-strategy-panel");
  await panel.getByLabel("Annual peer PE / 年度同行市盈率").check();
  await panel.getByLabel("FCFF proxy DCF / 代理现金流 DCF").check();
  await panel.getByTestId("strategy-peers").fill(options.peers ?? "MSFT");
  await panel
    .getByTestId("strategy-peer-rationale")
    .fill("Recorded same-industry peer declared before fetching");
  for (const [key, value] of Object.entries({
    discount_rate: ".1",
    growth_rate: ".03",
    terminal_growth: ".02",
    tax_rate: ".2",
    projection_years: "5",
    valuation_discount: options.discount ?? ".2",
    earnings_decline_fraction: ".2",
    debt_to_fcf_limit: "3",
    max_financial_age_days: "400",
    max_price_lag_sessions: "0",
  }))
    await panel.getByTestId(`strategy-${key}`).fill(value);
  await panel.getByTestId("strategy-proxy-ack").check();
  await panel.getByTestId("strategy-confirm-ack").check();
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/research-strategy") && r.request().method() === "POST",
  );
  await panel.getByTestId("confirm-research-strategy").click();
  expect((await response).status()).toBe(200);
  await expect(page.getByTestId("active-research-strategy")).toContainText(
    "strategy_",
  );
  await page.getByTestId("edit-research-strategy").click();
  const evidence = (await (
    await request.get(`${backend}/api/test/idq/evidence`)
  ).json()) as { model_calls: number };
  expect(evidence.model_calls).toBe(0);
}

export async function analyzeHoldings(page: Page) {
  await page.getByTestId("analyze-holdings").click();
  await expect(page.getByTestId("holdings-analysis-status")).toHaveAttribute(
    "data-run-status",
    "done",
    { timeout: 90000 },
  );
  await expect(page.getByTestId("strategy-receipt")).toBeVisible({
    timeout: 15000,
  });
}
