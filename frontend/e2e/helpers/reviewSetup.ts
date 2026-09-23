import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { setupStrategy, analyzeHoldings } from "./researchSetup";
const backend = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:18096";

export async function setup(
  page: Page,
  request: APIRequestContext,
  mode = "normal",
  subset = false,
  model = false,
) {
  await setupStrategy(page, request, mode, {
    resetPath: "/api/test/review/reset",
    peers: "AAPL, MSFT",
    discount: "0",
    minCash: subset ? ".15" : "0",
  });
  if (subset) {
    expect(
      (
        await request.post(`${backend}/api/portfolio/holdings`, {
          data: { symbol: "MSFT", quantity: 10, avg_price: 90 },
        })
      ).status(),
    ).toBe(200);
    await page.reload();
    await page.getByTestId("nav-portfolio").click();
  }
  await page.getByTestId("configure-review-policy").click();
  await expect(page.getByTestId("review-policy-sigma")).toBeVisible({
    timeout: 15000,
  });
  await expect(page.getByTestId("review-policy-sigma")).toHaveValue("");
  await expect(page.getByTestId("review-policy-ack")).not.toBeChecked();
  await page.getByTestId("review-policy-symbols").fill("AAPL, MSFT");
  await page.getByTestId("review-policy-sigma").fill(".5");
  await page.getByTestId("review-policy-lifetime").fill("60");
  await page.getByTestId("review-instrument-ack").check();
  await page.getByTestId("review-evidence-ack").check();
  await page.getByTestId("review-policy-ack").check();
  if (model) {
    await page.getByTestId("review-model-enabled").check();
    await page.getByTestId("review-model-open-no").check();
    await page.getByTestId("review-model-exit-yes").check();
    await page.getByTestId("review-model-ack").check();
  } else await page.getByTestId("review-model-disabled").check();
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/review-policy") && r.request().method() === "POST",
  );
  await page.getByTestId("confirm-review-policy").click();
  expect((await response).status()).toBe(200);
  await expect(page.getByTestId("active-review-policy")).toContainText(
    "review_policy_",
  );
  await page.getByTestId("configure-review-policy").click();
  const audit = (await (
    await request.get(`${backend}/api/test/review/audit`)
  ).json()) as { model_requests: number };
  expect(audit.model_requests).toBe(0);
  await analyzeHoldings(page);
  const rows = (await (
    await request.get(`${backend}/api/portfolio/assessments`)
  ).json()) as { assessment_id: string; actionable: boolean }[];
  expect(rows).toHaveLength(1);
  expect(rows[0].actionable).toBe(false);
  await expect(page.getByTestId("review-source").locator("option")).toHaveCount(
    2,
  );
  await page.getByTestId("review-source").selectOption(rows[0].assessment_id);
}
