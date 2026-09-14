/** CI/local smoke uses the same events fixture with real API, Mongo and Redis. */
import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

test("routing, buffered output, replay and visible prompt governance @ci-hardening @real-stack", async ({
  page,
  request,
}) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1440, height: 1100 });
  const backend = process.env.E2E_BACKEND_URL;
  expect(
    backend,
    "An explicit deterministic fixture backend is required",
  ).toBeTruthy();
  const id = `ci-${Date.now()}-${test.info().workerIndex}`;
  let originalBody: Record<string, unknown> = {};
  await page.route("**/api/chat/stream", async (route) => {
    const body = JSON.parse(route.request().postData() ?? "{}") as Record<
      string,
      unknown
    >;
    originalBody = { ...body, request_id: id };
    await route.continue({ postData: JSON.stringify(originalBody) });
  });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByTestId("nav-chat").click();
  await page.getByTestId("chat-composer").fill("DIRECT CI replay proof");
  await page.getByTestId("chat-send").click();
  await expect(page.getByTestId("run-state")).toHaveAttribute(
    "data-run-status",
    "completed",
  );
  const directId = await page
    .getByTestId("run-state")
    .getAttribute("data-run-id");
  const directResponse = await request.get(`${backend}/api/runs/${directId}`);
  expect(directResponse.ok()).toBe(true);
  const direct = (await directResponse.json()) as {
    selected_policy: string;
    prompt_versions: Record<string, string>;
  };
  expect(direct.selected_policy).toBe("v2");
  expect(direct.prompt_versions["financial-system"]).toBeTruthy();
  const beforeResponse = await request.get(
    `${backend}/api/test/idempotency-count`,
  );
  const before = (await beforeResponse.json()) as { execution_count: number };
  const replay = await request.post(`${backend}/api/chat/stream`, {
    data: originalBody,
  });
  expect(replay.ok()).toBe(true);
  const replayBody = await replay.text();
  expect(replayBody).toContain(directId);
  expect(replayBody).toMatch(/"request_reused"\s*:\s*true/);
  const afterResponse = await request.get(
    `${backend}/api/test/idempotency-count`,
  );
  const after = (await afterResponse.json()) as { execution_count: number };
  expect(after.execution_count).toBe(before.execution_count);
  await expect(
    page
      .locator("[data-chat-scroll]")
      .getByText("DIRECT_ENVELOPE_OK", { exact: true }),
  ).toHaveCount(1);

  await page.unroute("**/api/chat/stream");
  await page.getByRole("button", { name: /New Chat|新对话/ }).click();
  await page.getByTestId("chat-composer").fill("REACT CI buffered proof");
  await page.getByTestId("chat-send").click();
  await expect(page.getByTestId("run-state")).toHaveAttribute(
    "data-run-status",
    "completed",
  );
  await expect(page.getByTestId("response-stream-mode")).toHaveAttribute(
    "data-stream-mode",
    "buffered",
  );
  await expect(
    page
      .locator("[data-chat-scroll]")
      .getByText("REACT_ENVELOPE_OK", { exact: true }),
  ).toBeVisible();
  const reactId = await page
    .getByTestId("run-state")
    .getAttribute("data-run-id");
  const reactResponse = await request.get(`${backend}/api/runs/${reactId}`);
  const react = (await reactResponse.json()) as { selected_policy: string };
  expect(react.selected_policy).toBe("v3");

  // This is a real deterministic evaluation API call, not the evalFake UI hook.
  await page.getByTestId("nav-evaluation").click();
  const evaluationResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().includes("/api/admin/evaluations/run"),
  );
  await page.getByTestId("run-evaluation").click();
  const evaluation = await evaluationResponse;
  expect(evaluation.ok()).toBe(true);
  const report = (await evaluation.json()) as {
    configured_prompt_versions: Record<string, string>;
    provenance: {
      backend_version: string;
      git_commit: string | null;
      source: string;
    };
  };
  const healthResponse = await request.get(`${backend}/api/health`);
  const health = (await healthResponse.json()) as { version: string };
  expect(report.provenance.backend_version).toBe(health.version);
  if (report.provenance.git_commit !== null) {
    expect(report.provenance.git_commit).toMatch(/^[0-9a-f]{40}$/);
  }
  const configuredPrompt =
    report.configured_prompt_versions["financial-system"];
  expect(configuredPrompt).toMatch(/^financial-system@\d+$/);
  await expect(page.getByTestId("evaluation-status")).toHaveAttribute(
    "data-status",
    "pass",
  );
  await expect(page.getByTestId("metric-live-model-calls")).toContainText("0");
  await expect(
    page.getByText(configuredPrompt, { exact: true }).first(),
  ).toBeVisible();
  if (process.env.UPDATE_E2E_EVIDENCE === "true") {
    const dir = path.resolve("..", "docs", "features", "assets", "ph-004");
    mkdirSync(dir, { recursive: true });
    await page.screenshot({
      path: path.join(dir, "01-ci-e2e-smoke-pass.png"),
      fullPage: true,
      animations: "disabled",
    });
  }
});
