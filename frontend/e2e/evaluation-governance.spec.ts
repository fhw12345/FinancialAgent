import { mkdirSync } from "fs";
import path from "path";
import { expect, test } from "@playwright/test";

const evidenceDir = path.join(
  process.cwd(),
  "..",
  "docs",
  "features",
  "assets",
  "evaluation-governance",
);
const updateEvidence = process.env.UPDATE_E2E_EVIDENCE === "true";

test.beforeEach(async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1440, height: 1100 });
  mkdirSync(evidenceDir, { recursive: true });

  await page.goto("/?evalFake=1", { waitUntil: "domcontentloaded" });
  await page.getByTestId("nav-evaluation").click();
});

test("deterministic evaluation renders executable governance gates", async ({
  page,
}) => {
  await page.getByTestId("run-evaluation").click();

  const status = page.getByTestId("evaluation-status");
  await expect(status).toHaveAttribute("data-status", "pass");
  await expect(status).toContainText("2.0");
  await expect(status).toContainText("80 / 80");
  await expect(page.getByTestId("metric-quality")).toContainText("100.0%");
  await expect(page.getByTestId("metric-injection")).toContainText("100.0%");
  await expect(page.getByTestId("metric-live-model-calls")).toContainText("0");

  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "01-deterministic-governance.png"),
      fullPage: true,
    });
  }
});

test("fake live replay renders tools quality tokens and cost", async ({
  page,
}) => {
  await page.getByTestId("evaluation-mode-live").check();
  await page.getByTestId("live-evaluation-lane").selectOption("fake_live");
  await page.getByTestId("live-evaluation-budget").fill("1");
  await page.getByTestId("live-evaluation-consent").check();
  await page.getByTestId("run-evaluation").click();

  await expect(page.getByTestId("live-evaluation-status")).toHaveAttribute(
    "data-status",
    "completed",
    { timeout: 60_000 },
  );
  await expect(page.getByTestId("live-case-pass-rate")).toContainText("100.0%");
  await expect(page.getByTestId("live-tool-recall")).toContainText("100.0%");
  await expect(page.getByTestId("live-judge-quality")).toContainText("100.0%");
  await expect(page.getByTestId("live-estimated-cost")).not.toContainText(
    "$0.000000",
  );
  await expect(page.getByTestId("live-case-live_quote_en")).toHaveAttribute(
    "data-status",
    "completed",
  );
  await page.getByTestId("live-case-live_quote_en").locator("summary").click();
  await expect(
    page
      .getByTestId("live-case-live_quote_en")
      .getByTestId("live-tool-source"),
  ).toContainText("REPLAY-Q-AAPL-2026-08-01");
  await expect(
    page
      .getByTestId("live-case-live_quote_en")
      .getByTestId("live-model-usage")
      .filter({ hasText: "eval_judge" }),
  ).toBeVisible();
  await expect(page.getByTestId("live-pricing-catalog")).toContainText(
    "2026-08-04",
  );
  await expect(page.getByTestId("live-history-run").first()).toBeVisible();

  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "02-live-replay-quality-and-cost.png"),
      fullPage: true,
    });
  }
});

test("insufficient budget stops live evaluation without a green gate", async ({
  page,
}) => {
  await page.getByTestId("evaluation-mode-live").check();
  await page.getByTestId("live-evaluation-lane").selectOption("fake_live");
  await page.getByTestId("live-evaluation-budget").fill("0.000001");
  await page.getByTestId("live-evaluation-case-limit").fill("3");
  await page.getByTestId("live-evaluation-consent").check();
  await page.getByTestId("run-evaluation").click();

  await expect(page.getByTestId("live-evaluation-status")).toHaveAttribute(
    "data-status",
    "budget_exhausted",
    { timeout: 60_000 },
  );
  await expect(page.getByTestId("live-case-pass-rate")).toContainText("0.0%");
  await expect(page.getByTestId("live-case-live_concept_zh")).toHaveAttribute(
    "data-status",
    "skipped",
  );

  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "03-budget-exhaustion.png"),
      fullPage: true,
    });
  }
});
