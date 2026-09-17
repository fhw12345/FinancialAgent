import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";
const backend = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:18096";
async function setup(page: Page, request: APIRequestContext, mode: string) {
  expect(
    (await request.post(`${backend}/api/test/evidence/reset/${mode}`)).ok(),
  ).toBe(true);
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.addInitScript(() => {
    localStorage.setItem("portfolio:leftWidth", "600");
    localStorage.setItem("portfolio:rightWidth", "240");
  });
  await page.goto("/");
  await page.getByTestId("nav-portfolio").click();
  await page.getByTestId("analyze-holdings").click();
  await expect(page.getByTestId("holdings-analysis-status")).toHaveAttribute(
    "data-run-status",
    "done",
    { timeout: 90000 },
  );
  await page.getByTestId("open-evidence-dossier").click();
  await expect(page.getByTestId("research-claim")).toBeVisible();
  await page.getByTestId("view-claim-evidence").click();
  await expect(page.getByTestId("evidence-record").first()).toBeVisible();
}
async function shot(page: Page, name: string) {
  if (process.env.UPDATE_E2E_EVIDENCE !== "true") return;
  const dir = path.resolve("../docs/features/assets/idq-004");
  await mkdir(dir, { recursive: true });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: path.join(dir, name),
    fullPage: true,
    animations: "disabled",
  });
}
test.describe("Sealed evidence @real-stack", () => {
  test.setTimeout(150000);
  test("Deep research persists a canonical dossier before completed chat reload", async ({
    page,
    request,
  }) => {
    expect(
      (await request.post(`${backend}/api/test/evidence/reset/normal`)).ok(),
    ).toBe(true);
    await page.goto("/");
    await page.getByTestId("nav-chat").click();
    await page
      .getByTestId("chat-composer")
      .fill("Deep analysis of AAPL using fundamentals and evidence.");
    await page.getByTestId("chat-send").click();
    await expect(page.getByTestId("run-state")).toHaveAttribute(
      "data-run-status",
      "completed",
      { timeout: 120000 },
    );
    await page.reload();
    await page.getByTestId("open-evidence-dossier").first().click();
    await expect(page.getByTestId("research-claim")).toBeVisible();
    await expect(page.getByTestId("claim-verification")).toContainText(
      /Fields match|字段匹配/,
    );
    await page.getByTestId("view-claim-evidence").click();
    await expect(page.getByTestId("evidence-id").first()).toBeVisible();
  });
  test("trace a canonical number and preserve the sealed record across reload/provider changes", async ({
    page,
    request,
  }) => {
    await setup(page, request, "normal");
    await expect(page.getByTestId("claim-verification")).toContainText(
      /Fields match|字段匹配/,
    );
    await expect(page.getByTestId("claim-value")).toHaveText("100 USD");
    const id = await page.getByTestId("evidence-id").first().innerText();
    const snapshot = await page.getByTestId("evidence-snapshot-id").innerText();
    const response = await request.get(
      `${backend}/api/portfolio/evidence/records/${id}?snapshot_id=${snapshot}`,
    );
    expect(response.ok()).toBe(true);
    const record = (await response.json()) as {
      value: number;
      unit: string;
      period_end: string;
      published_at: string | null;
      point_in_time_status: string;
      payload_hash: string;
    };
    expect(record.value).toBe(100);
    expect(record.unit).toBe("USD");
    expect(record.period_end).toBe("2026-09-16");
    expect(record.published_at).toBeNull();
    expect(record.point_in_time_status).not.toBe("verified");
    await shot(page, "01-claim-evidence.png");
    await request.post(`${backend}/api/test/evidence/change-provider`);
    await page.reload();
    await page.getByTestId("nav-portfolio").click();
    await page.getByTestId("open-evidence-dossier").click();
    await page.getByTestId("view-claim-evidence").click();
    await expect(page.getByTestId("evidence-id").first()).toHaveText(id);
    const after = (await (
      await request.get(
        `${backend}/api/portfolio/evidence/records/${id}?snapshot_id=${snapshot}`,
      )
    ).json()) as { payload_hash: string };
    expect(after.payload_hash).toBe(record.payload_hash);
    expect(
      (
        await request.get(
          `${backend}/api/portfolio/evidence/records/${id}?snapshot_id=snapshot_other`,
        )
      ).status(),
    ).toBe(409);
  });
  test("two provider closing references conflict; translation cannot erase numeric IDs or rejection", async ({
    page,
    request,
  }) => {
    await setup(page, request, "conflict");
    await expect(page.getByTestId("claim-verification")).toContainText(
      "CONFLICTING_EVIDENCE",
    );
    await expect(page.getByTestId("evidence-record")).toHaveCount(2);
    const text = await page.getByRole("dialog").innerText();
    expect(text).toContain("finnhub");
    expect(text).toContain("yfinance");
    expect(text).toContain("100 USD");
    expect(text).toContain("101 USD");
    const ids = await page.getByTestId("evidence-id").allTextContents();
    await shot(page, "02-conflicting-evidence.png");
    await page
      .getByRole("dialog")
      .getByRole("button", { name: /^(关闭|Close)$/ })
      .click();
    await page
      .locator('button[title="语言"], button[title="Language"]')
      .click();
    await page.getByTestId("open-evidence-dossier").click();
    await page.getByTestId("view-claim-evidence").click();
    await expect(page.getByTestId("evidence-record")).toHaveCount(2);
    expect(await page.getByTestId("evidence-id").allTextContents()).toEqual(
      ids,
    );
    await expect(page.getByTestId("claim-verification")).toContainText(
      "CONFLICTING_EVIDENCE",
    );
    const rows = (await (
      await request.get(`${backend}/api/portfolio/assessments`)
    ).json()) as { actionable: boolean; readiness: string }[];
    expect(rows[0].actionable).toBe(false);
    expect(rows[0].readiness).not.toBe("ready");
  });
});
