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

test("deterministic evaluation renders executable governance gates", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1440, height: 1100 });
  mkdirSync(evidenceDir, { recursive: true });

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByTestId("nav-evaluation").click();
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
      path: path.join(evidenceDir, "01-evaluation-governance-pass.png"),
      fullPage: true,
    });
  }
});
