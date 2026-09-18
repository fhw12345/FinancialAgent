import { test, expect, type Page } from "@playwright/test";
import {
  setupStrategy as setup,
  analyzeHoldings as analyze,
} from "./helpers/researchSetup";
import { mkdir } from "node:fs/promises";
import path from "node:path";
const backend = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:18096";
const headers = { "X-Financial-Agent-Local": "1" };
async function shot(page: Page, name: string) {
  if (process.env.UPDATE_E2E_EVIDENCE !== "true") return;
  const dir = path.resolve("../docs/features/assets/idq-005");
  await mkdir(dir, { recursive: true });
  await page.getByTestId("strategy-receipt").scrollIntoViewIfNeeded();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: path.join(dir, name),
    fullPage: true,
    animations: "disabled",
  });
}
test.describe("Confirmed strategy @real-stack", () => {
  test.setTimeout(150000);
  test("Deep uses the confirmed fundamental contract, not a forced trading verdict", async ({
    page,
    request,
  }) => {
    await setup(page, request, "normal");
    await page.getByTestId("nav-chat").click();
    await page
      .getByTestId("chat-composer")
      .fill("Deep analysis of AAPL fundamentals and valuation.");
    await page.getByTestId("chat-send").click();
    await expect(page.getByTestId("run-state")).toHaveAttribute(
      "data-run-status",
      "completed",
      { timeout: 120000 },
    );
    await page.reload();
    await expect(page.getByTestId("strategy-receipt")).toBeVisible({
      timeout: 15000,
    });
    await expect(page.getByTestId("strategy-horizon")).toContainText(
      "252 XNYS_sessions",
    );
    await expect(page.getByTestId("strategy-conclusion")).toContainText(
      "Portfolio action: none",
    );
  });
  test("explicit mandate produces reproducible method receipts, not execution prices", async ({
    page,
    request,
  }) => {
    await setup(page, request, "normal");
    await analyze(page);
    const receipt = page.getByTestId("strategy-receipt");
    await expect(receipt.getByTestId("strategy-horizon")).toContainText(
      "252 XNYS_sessions · SPY_total_return@1",
    );
    await expect(
      receipt.getByTestId("strategy-valuation").first(),
    ).toContainText("100.00 USD/share");
    await expect(receipt.getByTestId("strategy-conclusion")).toContainText(
      "Investment stance: bullish",
    );
    await expect(receipt.getByTestId("strategy-conclusion")).toContainText(
      "Portfolio action: none",
    );
    const version = await receipt.getByTestId("strategy-version").innerText();
    await shot(page, "01-strategy-contract.png");
    await page.reload();
    await page.getByTestId("nav-portfolio").click();
    await expect(receipt.getByTestId("strategy-version")).toHaveText(version);
    const rows = (await (
      await request.get(`${backend}/api/portfolio/assessments`)
    ).json()) as {
      actionable: boolean;
      strategy: {
        reviews: { valuations: { per_share_usd: number | null }[] }[];
      };
    }[];
    expect(rows[0].actionable).toBe(false);
    expect(rows[0].strategy.reviews[0].valuations[0].per_share_usd).toBe(100);
  });
  test("missing earnings or diluted shares stays unavailable, not fabricated fair value", async ({
    page,
    request,
  }) => {
    await setup(page, request, "missing");
    await analyze(page);
    await expect(page.getByTestId("strategy-value").first()).toContainText(
      "Unavailable",
    );
    await expect(page.getByTestId("strategy-receipt")).toContainText(
      "INPUT_UNAVAILABLE:eps",
    );
    await expect(page.getByTestId("strategy-conclusion")).toContainText(
      "Investment stance: unknown",
    );
    await shot(page, "02-missing-valuation.png");
    const before = await page.getByTestId("strategy-value").allTextContents();
    await page.reload();
    await page.getByTestId("nav-portfolio").click();
    await expect(page.getByTestId("strategy-receipt")).toBeVisible();
    expect(await page.getByTestId("strategy-value").allTextContents()).toEqual(
      before,
    );
  });
  test("stale version writes fail and deactivation does not rewrite historical receipts", async ({
    page,
    request,
  }) => {
    await setup(page, request, "normal");
    await analyze(page);
    const version = await page.getByTestId("strategy-version").innerText();
    const state = (await (
      await request.get(`${backend}/api/portfolio/research-strategy`)
    ).json()) as {
      revision: number;
      versions: {
        parameters: Record<string, unknown>;
        cost_policy_revision: number;
      }[];
    };
    expect(
      (
        await request.post(`${backend}/api/portfolio/research-strategy`, {
          headers,
          data: {
            confirm: true,
            expected_revision: 0,
            request_id: "stale",
            cost_policy_revision: state.versions[0].cost_policy_revision,
            parameters: state.versions[0].parameters,
          },
        })
      ).status(),
    ).toBe(409);
    await page
      .getByRole("button", {
        name: "Deactivate for future research",
        exact: true,
      })
      .click();
    await expect(page.getByTestId("active-research-strategy")).toContainText(
      "Not enabled",
    );
    await page.reload();
    await page.getByTestId("nav-portfolio").click();
    await expect(page.getByTestId("strategy-version")).toHaveText(version);
    await expect(page.getByTestId("strategy-receipt")).toContainText(
      "Stale contract/costs",
    );
  });
});
