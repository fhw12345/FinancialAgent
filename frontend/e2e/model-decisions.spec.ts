import { expect, test, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { setup } from "./helpers/reviewSetup";
const backend = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:18096";
const headers = {
  "X-Financial-Agent-Local": "1",
  "Content-Type": "application/json",
};
type Audit = {
  model_requests: number;
  holdings: unknown;
  cash: unknown;
  counts: unknown;
};

async function requestDecision(page: Page) {
  await page.getByTestId("model-decision-ack").check();
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/portfolio/model-decisions") &&
      r.request().method() === "POST",
  );
  await page.getByTestId("request-model-decision").click();
  return response;
}
async function shot(page: Page, name: string) {
  if (process.env.UPDATE_E2E_EVIDENCE !== "true") return;
  const dir = path.resolve("../docs/features/assets/idq-001-c");
  await mkdir(dir, { recursive: true });
  await page
    .getByTestId("model-decision-panel")
    .screenshot({ path: path.join(dir, name), animations: "disabled" });
}

test.describe("Model investment decisions @real-stack", () => {
  test.setTimeout(180000);
  test("model decides ADD/HOLD, code validates, human approves; nothing trades", async ({
    page,
    request,
  }) => {
    await setup(page, request, "normal", false, true);
    const before = (await (
      await request.get(`${backend}/api/test/review/audit`)
    ).json()) as Audit;
    const response = await requestDecision(page);
    expect(response.status()).toBe(200);
    const view = (await response.json()) as {
      record: {
        decision_id: string;
        status: string;
        provenance: {
          provider: string;
          model: string;
          routing_revision: number;
        };
        output: { decisions: { symbol: string; action: string }[] };
      };
      review: { readiness: string; reasons: unknown[] } | null;
    };
    expect(view.record.status).toBe("completed");
    // Actual routed role/model recorded from the frozen Copilot routing snapshot.
    expect(view.record.provenance).toMatchObject({
      provider: "github_copilot",
      model: "gpt-6-astra",
    });
    expect(view.review?.reasons).toEqual([]);
    expect(view.review?.readiness).toBe("ready");
    await expect(page.getByTestId("model-decision-AAPL")).toHaveAttribute(
      "data-action",
      "ADD",
    );
    // Holdings research covers only AAPL; researched ∩ attested universe is the scope.
    expect(view.record.output.decisions.map((d) => d.symbol)).toEqual(["AAPL"]);
    const batch = page.getByTestId("review-batch").first();
    await expect(batch).toHaveAttribute("data-readiness", "ready");
    await expect(batch.getByTestId("batch-model-decision")).toContainText(
      view.record.decision_id,
    );
    await expect(batch.getByTestId("review-trade-AAPL")).toContainText(
      "Δ 12 shares", // 20% × (10,000 cash + 10 × $100) ÷ $100 − 10 held
    );
    await shot(page, "01-model-decision-ready.png");
    const after = (await (
      await request.get(`${backend}/api/test/review/audit`)
    ).json()) as Audit;
    expect(after.model_requests).toBe(before.model_requests + 1);
    // Replay of the same request returns the stored decision with no second paid call.
    const replay = await request.post(response.url(), {
      headers,
      data: response.request().postData() ?? "",
    });
    expect(replay.status()).toBe(200);
    const replayed = (await (
      await request.get(`${backend}/api/test/review/audit`)
    ).json()) as Audit;
    expect(replayed.model_requests).toBe(after.model_requests);
    await batch.getByTestId("approve-review-ack").check();
    const approved = page.waitForResponse(
      (r) => r.url().endsWith("/approve") && r.request().method() === "POST",
    );
    await batch.getByTestId("approve-review").click();
    expect((await approved).status()).toBe(200);
    await expect(batch.getByTestId("review-approved")).toHaveAttribute(
      "data-current",
      "true",
    );
    const final = (await (
      await request.get(`${backend}/api/test/review/audit`)
    ).json()) as Audit;
    expect({ ...final, model_requests: 0 }).toEqual({
      ...before,
      model_requests: 0,
    });
    await page.reload();
    await page.getByTestId("nav-portfolio").click();
    await expect(page.getByTestId("model-decision-AAPL")).toHaveAttribute(
      "data-action",
      "ADD",
    );
    await expect(page.getByTestId("review-approved").first()).toHaveAttribute(
      "data-current",
      "true",
    );
  });
  test("an invalid model decision is shown with its blocking reason, never rewritten", async ({
    page,
    request,
  }) => {
    await setup(page, request, "normal", false, true);
    expect(
      (
        await request.post(`${backend}/api/test/review/model-mode/exposure`)
      ).ok(),
    ).toBe(true);
    expect((await requestDecision(page)).status()).toBe(200);
    await expect(page.getByTestId("model-decision-AAPL")).toHaveAttribute(
      "data-action",
      "BUY",
    );
    const batch = page.getByTestId("review-batch").first();
    await expect(batch).toHaveAttribute("data-readiness", "blocked");
    await expect(batch).toContainText("MODEL_ACTION_EXPOSURE_CONFLICT");
    await expect(batch.getByTestId("approve-review")).toHaveCount(0);
    await expect(page.getByTestId("model-decision-review-state")).toContainText(
      "MODEL_ACTION_EXPOSURE_CONFLICT",
    );
    await shot(page, "02-model-decision-blocked.png");
  });
  test("with model decisions disabled there is no paid call path", async ({
    page,
    request,
  }) => {
    await setup(page, request);
    await expect(page.getByTestId("request-model-decision")).toHaveCount(0);
    await expect(page.getByTestId("model-decision-panel")).toContainText(
      "Enable model decisions",
    );
    const before = (await (
      await request.get(`${backend}/api/test/review/audit`)
    ).json()) as Audit;
    const state = (await (
      await request.get(`${backend}/api/portfolio/review-policy`)
    ).json()) as { revision: number; generation: number };
    const rows = (await (
      await request.get(`${backend}/api/portfolio/assessments`)
    ).json()) as { assessment_id: string }[];
    const forced = await request.post(
      `${backend}/api/portfolio/model-decisions`,
      {
        headers,
        data: {
          expected_revision: state.revision,
          expected_generation: state.generation,
          request_id: "forced-model-call",
          assessment_id: rows[0].assessment_id,
          confirm: true,
          acknowledgment: "uses-model-allowance-recommendation-only-no-trade",
        },
      },
    );
    expect(forced.status()).toBe(409);
    const after = (await (
      await request.get(`${backend}/api/test/review/audit`)
    ).json()) as Audit;
    expect(after.model_requests).toBe(before.model_requests);
  });
});
