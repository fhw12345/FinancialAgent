import { expect, test, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import type { ReviewView } from "../src/services/decisionReviews";
import { setup } from "./helpers/reviewSetup";
const backend = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:18096";
const headers = {
  "X-Financial-Agent-Local": "1",
  "Content-Type": "application/json",
};

async function propose(page: Page, targets: Record<string, string>) {
  for (const [symbol, value] of Object.entries(targets))
    await page.getByTestId(`review-target-${symbol}`).fill(value);
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/review-batches") && r.request().method() === "POST",
  );
  await page.getByTestId("prepare-review").click();
  const result = await response;
  expect(result.status()).toBe(200);
  return (await result.json()) as ReviewView;
}
async function approve(page: Page) {
  await page.getByTestId("approve-review-ack").check();
  const response = page.waitForResponse(
    (r) =>
      r.url().includes("/review-batches/") &&
      r.url().endsWith("/approve") &&
      r.request().method() === "POST",
  );
  await page.getByTestId("approve-review").click();
  return response;
}
async function screenshot(page: Page, name: string) {
  if (process.env.UPDATE_E2E_EVIDENCE !== "true") return;
  const dir = path.resolve("../docs/features/assets/idq-001-b");
  await mkdir(dir, { recursive: true });
  await page
    .getByTestId("review-batch")
    .screenshot({ path: path.join(dir, name), animations: "disabled" });
}

test.describe("Human paper review @real-stack", () => {
  test.setTimeout(180000);
  test("ready and approval are durable but do not trade; independent bookkeeping makes approval stale", async ({
    page,
    request,
  }) => {
    await setup(page, request);
    const before = (await (
      await request.get(`${backend}/api/test/review/audit`)
    ).json()) as unknown;
    const view = await propose(page, { AAPL: ".2" });
    expect(view.reasons).toEqual([]);
    expect(view.readiness).toBe("ready");
    await expect(page.getByTestId("review-batch")).toHaveAttribute(
      "data-readiness",
      "ready",
    );
    await expect(page.getByTestId("approve-review")).toBeDisabled();
    const response = await approve(page);
    expect(response.status()).toBe(200);
    const approved = (await response.json()) as ReviewView;
    expect(approved.approval_current).toBe(true);
    expect(approved.executable).toBe(false);
    await expect(page.getByTestId("review-approved")).toHaveAttribute(
      "data-current",
      "true",
    );
    expect(
      await (await request.get(`${backend}/api/test/review/audit`)).json(),
    ).toEqual(before);
    const replay = await request.post(response.url(), {
      headers,
      data: response.request().postData() ?? "",
    });
    expect(replay.status()).toBe(200);
    expect(((await replay.json()) as ReviewView).approval?.approval_id).toBe(
      approved.approval?.approval_id,
    );
    await screenshot(page, "01-approved-review.png");
    await page.reload();
    await page.getByTestId("nav-portfolio").click();
    await expect(page.getByTestId("review-approved")).toHaveAttribute(
      "data-current",
      "true",
    );
    expect(
      (
        await request.post(`${backend}/api/portfolio/user-transactions`, {
          data: { symbol: "AAPL", side: "buy", quantity: 0.5, price: 100 },
        })
      ).status(),
    ).toBe(201);
    await expect(page.getByTestId("review-approved")).toHaveAttribute(
      "data-current",
      "false",
      { timeout: 15000 },
    );
    await expect(page.getByTestId("review-batch")).toContainText(
      "INPUT_REVISION_CHANGED",
    );
    await screenshot(page, "02-stale-approval.png");
    const stale = (await (
      await request.get(
        `${backend}/api/portfolio/review-batches/${view.batch.batch_id}`,
      )
    ).json()) as ReviewView;
    expect(stale.approval?.approval_id).toBe(approved.approval?.approval_id);
    expect(stale.approval_current).toBe(false);
  });
  test("missing financial evidence cannot be promoted or force-approved", async ({
    page,
    request,
  }) => {
    await setup(page, request, "missing");
    const view = await propose(page, { AAPL: ".2" });
    expect(view.readiness).not.toBe("ready");
    expect(view.approvable).toBe(false);
    await expect(page.getByTestId("approve-review")).toHaveCount(0);
    expect(
      (
        await request.post(
          `${backend}/api/portfolio/review-batches/${view.batch.batch_id}/approve`,
          {
            headers,
            data: {
              expected_revision: view.control_revision,
              expected_generation: view.control_generation,
              request_id: "forced-approval",
              symbols: ["AAPL"],
              confirm: true,
              acknowledgment: "review-only-no-real-or-paper-fill",
            },
          },
        )
      ).status(),
    ).toBe(409);
  });
  test("actual approved subset is checked without omitted-sale headroom", async ({
    page,
    request,
  }) => {
    await setup(page, request, "normal", true);
    const view = await propose(page, { AAPL: "0", MSFT: ".8" });
    expect(view.reasons).toEqual([]);
    await expect(page.getByTestId("approve-symbol-AAPL")).toBeVisible();
    await page.getByTestId("approve-symbol-AAPL").uncheck();
    const rejected = await approve(page);
    expect(rejected.status()).toBe(409);
    await expect(page.getByTestId("review-approval-error")).toContainText(
      "CASH_FLOOR",
    );
    const unchanged = (await (
      await request.get(
        `${backend}/api/portfolio/review-batches/${view.batch.batch_id}`,
      )
    ).json()) as ReviewView;
    expect(unchanged.approval).toBeNull();
    await screenshot(page, "03-rejected-subset.png");
    await page.getByTestId("approve-symbol-AAPL").check();
    expect((await approve(page)).status()).toBe(200);
  });
  test("account mutation wins a race after validation but before approval publication", async ({
    page,
    request,
  }) => {
    await setup(page, request);
    const view = await propose(page, { AAPL: ".2" });
    expect(view.reasons).toEqual([]);
    expect(
      (
        await request.post(`${backend}/api/test/review/fault/approve_pause`)
      ).ok(),
    ).toBe(true);
    await page.getByTestId("approve-review-ack").check();
    const response = page.waitForResponse((r) =>
      r.url().endsWith(`/review-batches/${view.batch.batch_id}/approve`),
    );
    await page.getByTestId("approve-review").click();
    await expect
      .poll(
        async () =>
          (
            (await (
              await request.get(`${backend}/api/test/review/reached`)
            ).json()) as { paused: boolean }
          ).paused,
      )
      .toBe(true);
    expect(
      (
        await request.put(`${backend}/api/admin/portfolio/settings`, {
          data: {
            cash_balance: 11000,
            risk_tolerance: "moderate",
            max_position_pct: 10,
          },
        })
      ).status(),
    ).toBe(200);
    expect(
      (await request.post(`${backend}/api/test/review/release`)).ok(),
    ).toBe(true);
    expect((await response).status()).toBe(409);
    const latest = (await (
      await request.get(
        `${backend}/api/portfolio/review-batches/${view.batch.batch_id}`,
      )
    ).json()) as ReviewView;
    expect(latest.approval).toBeNull();
    expect(latest.approvable).toBe(false);
    await expect(page.getByTestId("review-batch")).toContainText(
      "INPUT_REVISION_CHANGED",
    );
  });
  test("Mongo deadline rejects expiry after validation even when the application clock lags", async ({
    page,
    request,
  }) => {
    await setup(page, request);
    const view = await propose(page, { AAPL: ".2" });
    expect(view.reasons).toEqual([]);
    expect(
      (
        await request.post(`${backend}/api/test/review/fault/approve_pause`)
      ).ok(),
    ).toBe(true);
    await page.getByTestId("approve-review-ack").check();
    const response = page.waitForResponse((r) =>
      r.url().endsWith(`/review-batches/${view.batch.batch_id}/approve`),
    );
    await page.getByTestId("approve-review").click();
    await expect
      .poll(
        async () =>
          (
            (await (
              await request.get(`${backend}/api/test/review/reached`)
            ).json()) as { paused: boolean }
          ).paused,
      )
      .toBe(true);
    expect(
      (
        await request.post(`${backend}/api/test/review/expire-storage-clock`)
      ).ok(),
    ).toBe(true);
    expect(
      (await request.post(`${backend}/api/test/review/release`)).ok(),
    ).toBe(true);
    expect((await response).status()).toBe(409);
    const latest = (await (
      await request.get(
        `${backend}/api/portfolio/review-batches/${view.batch.batch_id}`,
      )
    ).json()) as ReviewView;
    expect(latest.approval).toBeNull();
    await expect(page.getByTestId("review-approval-error")).toContainText(
      "expired lifetime",
    );
  });
  test("failed durable preparation never publishes ready and retry uses the same actual gates", async ({
    page,
    request,
  }) => {
    await setup(page, request);
    expect(
      (
        await request.post(`${backend}/api/test/review/fault/prepare_fail`)
      ).ok(),
    ).toBe(true);
    await page.getByTestId("review-target-AAPL").fill(".2");
    const sent = page.waitForRequest(
      (r) => r.url().endsWith("/review-batches") && r.method() === "POST",
    );
    await page.getByTestId("prepare-review").click();
    const failedRequest = await sent;
    // Unhandled outer storage faults may surface as a CORS network failure in
    // the browser. Assert its error state AND the real API's 500, not a success toast.
    await expect(
      page.getByTestId("review-target-form").getByRole("alert"),
    ).toBeVisible();
    expect(
      (
        await request.post(failedRequest.url(), {
          headers,
          data: failedRequest.postData() ?? "",
        })
      ).status(),
    ).toBe(500);
    expect(
      await (
        await request.get(`${backend}/api/portfolio/review-batches`)
      ).json(),
    ).toEqual([]);
    await expect(page.getByTestId("review-batch")).toHaveCount(0);
    expect(
      (await request.post(`${backend}/api/test/review/fault/none`)).ok(),
    ).toBe(true);
    expect((await propose(page, { AAPL: ".2" })).readiness).toBe("ready");
  });
});
