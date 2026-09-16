import {
  expect,
  test,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const backend = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:18096";
const assets = path.resolve("../docs/features/assets/idq-001-a");
async function setup(page: Page, request: APIRequestContext, mode: string) {
  expect(
    (await request.post(`${backend}/api/test/idq/reset/${mode}`)).ok(),
  ).toBe(true);
  await page.setViewportSize({ width: 1800, height: 1300 });
  await page.addInitScript(() => {
    localStorage.setItem("portfolio:leftWidth", "700");
    localStorage.setItem("portfolio:rightWidth", "240");
  });
  await page.goto("/");
  await page.getByTestId("nav-portfolio").click();
  await expect(page.getByTestId("analyze-holdings")).toBeEnabled();
}
async function start(page: Page): Promise<string> {
  const response = page.waitForResponse(
    (r) =>
      r.url().includes("/trigger-analysis") && r.request().method() === "POST",
  );
  await page.getByTestId("analyze-holdings").click();
  const body = (await (await response).json()) as { agent_run_id: string };
  return body.agent_run_id;
}
async function shot(page: Page, name: string) {
  if (process.env.UPDATE_E2E_EVIDENCE !== "true") return;
  await mkdir(assets, { recursive: true });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: path.join(assets, name),
    fullPage: true,
    animations: "disabled",
  });
}

test.describe("IDQ Stage A @real-stack", () => {
  test.setTimeout(120000);
  test("missing evidence is not HOLD and cannot be approved", async ({
    page,
    request,
  }) => {
    await setup(page, request, "missing");
    await start(page);
    await expect(page.getByTestId("holdings-analysis-status")).toHaveAttribute(
      "data-run-status",
      "done",
      { timeout: 60000 },
    );
    await expect(page.getByTestId("assessment-batch")).toHaveAttribute(
      "data-readiness",
      "insufficient_evidence",
      { timeout: 15000 },
    );
    await expect(page.getByTestId("assessment-symbol-AAPL")).toContainText(
      "QUOTE_UNAVAILABLE",
    );
    const batches = (await (
      await request.get(`${backend}/api/portfolio/assessments`)
    ).json()) as { assessment_id: string; actionable: boolean; action: null }[];
    expect(batches[0].actionable).toBe(false);
    expect(batches[0].action).toBeNull();
    expect(
      (
        await request.post(
          `${backend}/api/portfolio/assessments/${batches[0].assessment_id}/approve`,
          { data: { readiness: "ready" } },
        )
      ).status(),
    ).toBe(409);
    await shot(page, "01-insufficient-evidence.png");
    await page.reload();
    await page.getByTestId("nav-portfolio").click();
    await expect(page.getByTestId("assessment-batch")).toHaveAttribute(
      "data-readiness",
      "insufficient_evidence",
    );
    const evidence = (await (
      await request.get(`${backend}/api/test/idq/evidence`)
    ).json()) as { orders: number; transactions: number };
    expect(evidence.orders).toBe(1);
    expect(evidence.transactions).toBe(0);
  });

  test("complete research remains research-only and legacy is read-only", async ({
    page,
    request,
  }) => {
    await setup(page, request, "good");
    await start(page);
    await expect(page.getByTestId("holdings-analysis-status")).toHaveAttribute(
      "data-run-status",
      "done",
      { timeout: 60000 },
    );
    await expect(page.getByTestId("assessment-batch")).toHaveAttribute(
      "data-readiness",
      "research_only",
      { timeout: 15000 },
    );
    await expect(page.getByTestId("assessment-symbol-AAPL")).toContainText(
      "STAGE_A_ONLY",
    );
    await expect(
      page.getByRole("button", { name: "Mark Executed" }),
    ).toHaveCount(0);
    await expect(page.getByTestId("legacy-decision-readonly")).toBeVisible();
    expect(
      (
        await request.post(
          `${backend}/api/portfolio/orders/legacy_order/mark-executed`,
          { data: { filled_qty: 1, filled_avg_price: 100 } },
        )
      ).status(),
    ).toBe(409);
    const replays = await Promise.all(
      Array.from({ length: 8 }, () =>
        request.post(`${backend}/api/test/idq/replay/false`),
      ),
    );
    expect(replays.every((response) => response.ok())).toBe(true);
    expect(
      (await request.post(`${backend}/api/test/idq/replay/true`)).status(),
    ).toBe(409);
    const replayEvidence = (await (
      await request.get(`${backend}/api/test/idq/evidence`)
    ).json()) as { assessments: number };
    expect(replayEvidence.assessments).toBe(1);
    await shot(page, "02-research-only.png");
    await page
      .getByRole("button", { name: "Add Transaction", exact: true })
      .first()
      .click();
    const dialog = page.getByRole("dialog");
    await dialog.getByPlaceholder("AAPL — Apple Inc.").fill("AAPL");
    await dialog.getByPlaceholder("AAPL — Apple Inc.").press("Enter");
    await expect(dialog.locator("#transaction-symbol")).toHaveValue("AAPL");
    await dialog.getByLabel("Quantity", { exact: true }).fill("1");
    await dialog.getByLabel("Execution Price ($)", { exact: true }).fill("100");
    await dialog
      .getByRole("button", { name: "Add Transaction", exact: true })
      .click();
    await expect(dialog).toHaveCount(0);
    const evidence = (await (
      await request.get(`${backend}/api/test/idq/evidence`)
    ).json()) as { orders: number; transactions: number };
    expect(evidence.orders).toBe(1);
    expect(evidence.transactions).toBe(1);
    await page.getByTestId("legacy-decision-readonly").scrollIntoViewIfNeeded();
    await shot(page, "03-legacy-readonly.png");
  });

  test("unavailable checks and missing agent do not create actions", async ({
    page,
    request,
  }) => {
    await setup(page, request, "check_unavailable");
    await start(page);
    await expect(page.getByTestId("holdings-analysis-status")).toHaveAttribute(
      "data-run-status",
      "done",
      { timeout: 60000 },
    );
    await expect(page.getByTestId("assessment-symbol-AAPL")).toContainText(
      "CHECK_UNAVAILABLE",
      { timeout: 15000 },
    );
    await setup(page, request, "no_agent");
    await start(page);
    await expect(page.getByTestId("holdings-analysis-status")).toHaveAttribute(
      "data-run-status",
      "done",
      { timeout: 30000 },
    );
    const evidence = (await (
      await request.get(`${backend}/api/test/idq/evidence`)
    ).json()) as { model_calls: number; assessments: number };
    expect(evidence.model_calls).toBe(0);
    expect(evidence.assessments).toBe(1);
  });

  test("a model cannot replace the authorized research symbol", async ({
    page,
    request,
  }) => {
    await setup(page, request, "rogue");
    await start(page);
    await expect(page.getByTestId("holdings-analysis-status")).toHaveAttribute(
      "data-run-status",
      "done",
      { timeout: 60000 },
    );
    await expect(page.getByTestId("assessment-batch")).toHaveAttribute(
      "data-readiness",
      "blocked",
      { timeout: 15000 },
    );
    await expect(page.getByTestId("assessment-symbol-MSFT")).toContainText(
      "SYMBOL_NOT_AUTHORIZED",
    );
    await expect(page.getByTestId("assessment-symbol-AAPL")).toBeVisible();
    const evidence = (await (
      await request.get(`${backend}/api/test/idq/evidence`)
    ).json()) as { orders: number; transactions: number };
    expect(evidence.orders).toBe(1);
    expect(evidence.transactions).toBe(0);
  });

  test("persistence failure is not successful assessment", async ({
    page,
    request,
  }) => {
    await setup(page, request, "storage_fail");
    await start(page);
    await expect(page.getByTestId("holdings-analysis-status")).toHaveAttribute(
      "data-run-status",
      "error",
      { timeout: 60000 },
    );
    await expect(page.getByTestId("assessment-batch")).toHaveCount(0);
    const evidence = (await (
      await request.get(`${backend}/api/test/idq/evidence`)
    ).json()) as { orders: number; assessments: number };
    expect(evidence.assessments).toBe(0);
    expect(evidence.orders).toBe(1);
  });

  test("cancelled run cannot publish a completed actionable result", async ({
    page,
    request,
  }) => {
    await setup(page, request, "paused");
    const run = await start(page);
    await expect(page.getByTestId("holdings-analysis-status")).toHaveAttribute(
      "data-run-status",
      "running",
      { timeout: 15000 },
    );
    await request.post(`${backend}/api/test/idq/cancel/${run}`);
    await expect(page.getByTestId("holdings-analysis-status")).toHaveAttribute(
      "data-run-status",
      "error",
      { timeout: 15000 },
    );
    await expect(page.getByTestId("assessment-batch")).toHaveAttribute(
      "data-actionable",
      "false",
      { timeout: 60000 },
    );
    const batches = (await (
      await request.get(`${backend}/api/portfolio/assessments`)
    ).json()) as { run_status: string; readiness: string }[];
    expect(batches[0].run_status).toBe("cancelled");
    expect(batches[0].readiness).toBe("needs_review");
  });
});
