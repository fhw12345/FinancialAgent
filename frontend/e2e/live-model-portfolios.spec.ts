import { expect, test } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
const backend = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:18096";
const headers = { "X-Financial-Agent-Local": "1" };
const cases = [
  "cash-rich",
  "concentrated",
  "cash-poor",
  "bearish",
  "fractional-costs",
  "injection",
  "disabled",
  "missing-evidence",
  "inactive-strategy",
];
type Result = {
  case_id: string;
  negative_source: string | null;
  attempts: number;
  native_output_completed: boolean;
  engineering_containment_pass: boolean;
  model_contract_quality: string;
  model_contract_findings: string[];
  ledger_unchanged: boolean;
  review: { approvable: boolean } | null;
};
type Report = {
  run_id: string;
  mode: "replay" | "live";
  inference_attempt_count: number;
  results: Result[];
  attempts: { case_id: string }[];
};
const collected: Result[] = [];
let mode = "replay";

test.describe("Synthetic portfolios with live/replay model @real-stack", () => {
  test.setTimeout(120000);
  test.beforeAll(async ({ request }) => {
    const registered = await request.post(
      `${backend}/api/test/model-portfolios/register`,
      { headers },
    );
    expect(registered.status()).toBe(200);
    const run = (await registered.json()) as {
      mode: string;
      manifest: {
        max_calls: number;
        max_output_tokens: number;
        max_seconds: number;
      };
    };
    mode = run.mode;
    expect(run.manifest).toMatchObject({
      max_calls: 6,
      max_output_tokens: 4096,
      max_seconds: 600,
    });
    expect(mode).toBe(process.env.MODEL_PORTFOLIO_MODE ?? "replay");
  });
  test.afterAll(async ({ request }) => {
    const result = await request.get(
      `${backend}/api/test/model-portfolios/report`,
    );
    expect(result.ok()).toBe(true);
    const report = (await result.json()) as Report;
    const directory = path.resolve(
      `../backend/artifacts/model-portfolios/${mode}`,
    );
    await mkdir(directory, { recursive: true });
    await writeFile(
      path.join(directory, "report.json"),
      JSON.stringify(report, null, 2) + "\n",
    );
    expect(report.inference_attempt_count).toBeLessThanOrEqual(6);
    expect(report.inference_attempt_count).toBe(6);
    expect(new Set(report.attempts.map((a) => a.case_id)).size).toBe(
      report.attempts.length,
    );
    expect(report.results.map((r) => r.case_id).sort()).toEqual(
      [...cases].sort(),
    );
    // Preserve every result first, then assert containment and actual completion.
    // Model-quality findings are separately reported, never relabeled as quality pass.
    expect(collected.every((r) => r.engineering_containment_pass)).toBe(true);
    expect(
      collected
        .filter((r) => !r.negative_source)
        .every((r) => r.native_output_completed),
    ).toBe(true);
  });
  for (const identifier of cases) {
    test(`${identifier}: real decision path and independent contract/containment results`, async ({
      page,
      request,
    }) => {
      const seeded = await request.post(
        `${backend}/api/test/model-portfolios/seed/${identifier}`,
        { headers },
      );
      expect(seeded.status()).toBe(200);
      const source = (await seeded.json()) as {
        assessment_id: string;
        source_origin: string;
      };
      expect(source.source_origin).toBe(
        "precomputed_synthetic_source_not_live_research",
      );
      await page.setViewportSize({ width: 1800, height: 1300 });
      await page.addInitScript(() =>
        localStorage.setItem("portfolio:leftWidth", "700"),
      );
      await page.goto("/");
      await page.getByTestId("nav-portfolio").click();
      await expect(
        page.getByTestId("review-source").locator("option"),
      ).toHaveCount(2);
      await page
        .getByTestId("review-source")
        .selectOption(source.assessment_id);
      const negative = [
        "disabled",
        "missing-evidence",
        "inactive-strategy",
      ].includes(identifier);
      let responseStatus = 0;
      if (negative) {
        const current = (await (
          await request.get(`${backend}/api/portfolio/review-policy`)
        ).json()) as { revision: number; generation: number };
        const rejected = await request.post(
          `${backend}/api/portfolio/model-decisions`,
          {
            headers,
            data: {
              assessment_id: source.assessment_id,
              expected_revision: current.revision,
              expected_generation: current.generation,
              request_id: `acceptance-negative-${identifier}`,
              confirm: true,
              acknowledgment:
                "uses-model-allowance-recommendation-only-no-trade",
            },
          },
        );
        responseStatus = rejected.status();
      } else {
        await page.getByTestId("model-decision-ack").check();
        const sent = page.waitForRequest(
          (r) => r.url().endsWith("/model-decisions") && r.method() === "POST",
        );
        await page.getByTestId("request-model-decision").click();
        const original = await sent;
        // A provider/schema error may surface as CORS failure; wait on durable
        // attempt/model state rather than issuing a second paid inference request.
        try {
          await expect
            .poll(
              async () => {
                const rows = (await (
                  await request.get(`${backend}/api/portfolio/model-decisions`)
                ).json()) as { record: { status: string } }[];
                return rows[0]?.record.status;
              },
              { timeout: 100000 },
            )
            .toMatch(/completed|failed/);
        } catch {
          // The aggregate assertion still fails incomplete live runs, but only
          // after the report has retained this failure instead of dropping it.
          responseStatus = 504;
        }
        const completedResponse = await original.response();
        const terminal = completedResponse?.ok()
          ? ((await completedResponse.json()) as {
              record: { status: string };
              review: { approvable: boolean } | null;
            })
          : (
              (await (
                await request.get(`${backend}/api/portfolio/model-decisions`)
              ).json()) as {
                record: { status: string };
                review: { approvable: boolean } | null;
              }[]
            )[0];
        responseStatus = terminal.record.status === "completed" ? 200 : 500;
        if (mode === "replay" && identifier === "cash-rich") {
          expect(terminal.review?.approvable).toBe(true);
        }
        if (responseStatus === 200) {
          await expect(page.getByTestId("model-decision")).toHaveAttribute(
            "data-status",
            "completed",
            { timeout: 15000 },
          );
          // Replay executes the same real route, not a substituted recorded answer.
          const replay = await request.post(original.url(), {
            headers: { ...headers, "Content-Type": "application/json" },
            data: original.postData() ?? "",
          });
          expect(replay.status()).toBe(200);
          if (terminal.review?.approvable) {
            await page.getByTestId("approve-review-ack").check();
            const approved = page.waitForResponse(
              (r) =>
                r.url().endsWith("/approve") && r.request().method() === "POST",
            );
            await page.getByTestId("approve-review").click();
            expect((await approved).status()).toBe(200);
          }
          if (identifier === "cash-rich" || identifier === "injection") {
            await page.setViewportSize({ width: 1800, height: 3200 });
            await page
              .getByTestId("model-decision-panel")
              .evaluate((panel, runMode) => {
                const label = document.createElement("p");
                label.textContent = `ACCEPTANCE: synthetic portfolios/research inputs · ${runMode.toUpperCase()} model decision only`;
                label.style.background = "#e0e7ff";
                label.style.padding = "8px";
                panel.prepend(label);
                panel.scrollIntoView({ block: "center" });
              }, mode);
            const evidence = path.resolve(
              `../docs/features/assets/idq-009-a/${mode}`,
            );
            if (process.env.UPDATE_E2E_EVIDENCE === "true") {
              await mkdir(evidence, { recursive: true });
              await page.getByTestId("model-decision-panel").screenshot({
                path: path.join(evidence, `${identifier}.png`),
                animations: "disabled",
              });
            }
          }
        }
      }
      const observed = await request.post(
        `${backend}/api/test/model-portfolios/observe/${identifier}`,
        { headers },
      );
      expect(observed.status()).toBe(200);
      const result = (await observed.json()) as Result;
      collected.push(result);
      expect(result.ledger_unchanged).toBe(true);
      expect(result.engineering_containment_pass).toBe(true);
      if (negative) {
        expect(responseStatus).toBe(409);
        expect(result.attempts).toBe(0);
      } else {
        expect(result.attempts).toBe(1);
        if (!result.native_output_completed)
          console.log(`Recorded failed ${mode} case: ${identifier}`);
      }
    });
  }
});
