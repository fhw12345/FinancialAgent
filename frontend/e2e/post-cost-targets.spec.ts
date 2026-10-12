import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { setup } from "./helpers/reviewSetup";
import type { ReviewView } from "../src/services/decisionReviews";
const backend = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:18096";
async function decision(page: import("@playwright/test").Page) {
  await page.getByTestId("model-decision-ack").check();
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/model-decisions") && r.request().method() === "POST",
  );
  await page.getByTestId("request-model-decision").click();
  return response;
}
test.describe("Post-cost targets @real-stack", () => {
  test.setTimeout(180000);
  test("30% captured recommendation geometry uses confirmed after-cost sizing without rewriting or trading", async ({
    page,
    request,
  }) => {
    await setup(page, request, "normal", false, true, true);
    const before = (await (
      await request.get(`${backend}/api/test/review/audit`)
    ).json()) as unknown;
    expect(
      (
        await request.post(
          `${backend}/api/test/review/model-mode/post-cost-reduction`,
        )
      ).ok(),
    ).toBe(true);
    const response = await decision(page);
    expect(response.status()).toBe(200);
    const body = (await response.json()) as { review: ReviewView };
    expect(body.review.readiness).toBe("ready");
    expect(body.review.batch.policy?.allocation_calculator).toBe(
      "post-cost-targets@1",
    );
    expect(
      body.review.batch.risk?.allocation?.changes[0].requested_target_weight,
    ).toBe(0.3);
    expect(
      body.review.batch.risk?.allocation?.changes[0].proposed_quantity,
    ).toBe(29.9);
    expect(
      body.review.batch.risk?.allocation?.proposed?.position_weights.AAPL,
    ).toBeLessThanOrEqual(0.3);
    const batch = page.getByTestId("review-batch").first();
    await expect(batch).toHaveAttribute("data-readiness", "ready");
    await batch
      .getByText("Account/constraint receipt / 账户与限制回执", { exact: true })
      .click();
    await expect(batch.getByTestId("allocation-target-basis")).toContainText(
      "post-cost-targets@1",
    );
    await expect(batch.getByTestId("post-cost-sizing-receipt")).toContainText(
      "30.0000%",
    );
    await page.getByTestId("approve-review-ack").check();
    const approved = page.waitForResponse(
      (r) => r.url().endsWith("/approve") && r.request().method() === "POST",
    );
    await page.getByTestId("approve-review").click();
    expect((await approved).status()).toBe(200);
    await expect(page.getByTestId("review-approved")).toHaveAttribute(
      "data-current",
      "true",
    );
    const after = (await (
      await request.get(`${backend}/api/test/review/audit`)
    ).json()) as { model_requests: number };
    const baseline = before as { model_requests: number };
    expect({ ...after, model_requests: 0 }).toEqual({
      ...baseline,
      model_requests: 0,
    });
    expect(after.model_requests).toBe(baseline.model_requests + 1); // recorded outer provider, not live allowance
    if (process.env.UPDATE_E2E_EVIDENCE === "true") {
      const directory = path.resolve("../docs/features/assets/idq-001-d");
      await mkdir(directory, { recursive: true });
      await page.setViewportSize({ width: 1800, height: 2400 });
      await batch.evaluate((node) => node.scrollIntoView({ block: "center" }));
      await batch.screenshot({
        path: path.join(directory, "01-post-cost-approved.png"),
        animations: "disabled",
      });
    }
    const identifier = body.review.batch.batch_id;
    await page.reload();
    await page.getByTestId("nav-portfolio").click();
    await expect(page.getByTestId("review-approved")).toHaveAttribute(
      "data-current",
      "true",
    );
    const reloaded = (await (
      await request.get(`${backend}/api/portfolio/review-batches/${identifier}`)
    ).json()) as ReviewView;
    expect(reloaded.batch.receipt_hash).toBe(body.review.batch.receipt_hash);
  });
  test("a 40% target remains blocked by a 30% policy, not resized into eligibility", async ({
    page,
    request,
  }) => {
    await setup(page, request, "normal", false, true, true);
    expect(
      (
        await request.post(`${backend}/api/test/review/model-mode/above-limit`)
      ).ok(),
    ).toBe(true);
    const response = await decision(page);
    expect(response.status()).toBe(200);
    const body = (await response.json()) as { review: ReviewView };
    expect(body.review.readiness).toBe("blocked");
    expect(
      body.review.batch.risk?.allocation?.changes[0].requested_target_weight,
    ).toBe(0.4);
    expect(body.review.reasons.map((r) => r.code)).toContain(
      "POSITION_LIMIT:AAPL",
    );
    await expect(page.getByTestId("model-decision-AAPL")).toContainText(
      "40.00%",
    );
    await expect(page.getByTestId("approve-review")).toHaveCount(0);
  });
});
