import { test, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const backend = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:18094";
const headers = { "X-Financial-Agent-Local": "1" };

test("multi-vendor role routing persists, drives real Chat, and rejects stale writes @real-stack", async ({
  page,
  request,
}) => {
  test.setTimeout(90000);
  await request.post(`${backend}/api/test/copilot/reset`);
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto("/");
  await page.getByTestId("nav-health").click();
  await page.getByTestId("copilot-login").click();
  await expect(page.getByTestId("copilot-user-code")).toBeVisible();
  await request.post(`${backend}/api/test/copilot/approve`);
  await expect(page.getByTestId("copilot-models")).toBeVisible({
    timeout: 15000,
  });
  await page.getByTestId("copilot-models").click();
  await expect(
    page.getByTestId("copilot-model-select").locator("option"),
  ).toHaveCount(7);
  await expect(page.getByTestId("copilot-model-select")).not.toContainText(
    "mai-code",
  );
  const rejected = await request.post(`${backend}/api/llm/copilot/model`, {
    headers,
    data: { model_id: "mai-code-1.1-flash" },
  });
  expect(rejected.status()).toBe(422);
  await page.getByTestId("copilot-model-select").selectOption("gpt-6-astra");
  await page.getByTestId("copilot-save-model").click();
  await expect(page.getByTestId("copilot-test")).toBeEnabled();
  await page.getByTestId("copilot-role-settings").click();
  await page.getByTestId("copilot-preset").click();
  await page
    .getByTestId("copilot-role-simple_chat")
    .selectOption("gemini-3.8-flash");
  const before = await request.get(`${backend}/api/llm/copilot/status`);
  const beforeState = (await before.json()) as {
    role_models: Record<string, string>;
    routing_revision: number;
  };
  expect(beforeState.role_models).toEqual({});
  await page.getByTestId("copilot-save-routing").click();
  await expect(page.getByTestId("copilot-role-settings")).toContainText(
    `v${beforeState.routing_revision + 1}`,
  );
  await expect(page.getByTestId("copilot-save-routing")).toBeDisabled();
  await page.getByTestId("copilot-role-settings").click();
  await expect(page.getByTestId("copilot-role-sub_debater")).toHaveValue(
    "grok-4.6",
  );
  await page.getByTestId("copilot-test-role-sub_debater").click();
  await expect(page.getByTestId("copilot-role-test-result")).toContainText(
    "grok-4.6",
    { timeout: 15000 },
  );
  await page.getByTestId("copilot-test-role-sub_news").click();
  await expect(page.getByTestId("copilot-role-test-result")).toContainText(
    "gemini-3.8-flash",
    { timeout: 15000 },
  );
  if (process.env.UPDATE_E2E_EVIDENCE === "true") {
    const dir = path.resolve("../docs/features/assets/ghc-002");
    await mkdir(dir, { recursive: true });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: path.join(dir, "01-multivendor-roles.png"),
      fullPage: true,
      animations: "disabled",
    });
  }
  await page.reload();
  await page.getByTestId("nav-health").click();
  await page.getByTestId("copilot-role-settings").click();
  await expect(page.getByTestId("copilot-role-simple_chat")).toHaveValue(
    "gemini-3.8-flash",
  );
  await page.getByTestId("nav-chat").click();
  await page.getByTestId("chat-composer").fill("Explain compound interest");
  await page.getByTestId("chat-send").click();
  await expect(page.getByTestId("run-state")).toHaveAttribute(
    "data-run-status",
    "completed",
    { timeout: 30000 },
  );
  await expect(
    page
      .locator("[data-chat-scroll]")
      .getByText("NATIVE_GEMINI_CHAT_OK", { exact: true }),
  ).toBeVisible();
  const runId = await page.getByTestId("run-state").getAttribute("data-run-id");
  const run = (await (
    await request.get(`${backend}/api/runs/${runId}`)
  ).json()) as {
    model_routes: Record<string, string>;
    model_protocols: Record<string, string>;
    model_routing_revision: number;
  };
  expect(run.model_routes.simple_chat).toBe("gemini-3.8-flash");
  expect(run.model_protocols.simple_chat).toBe("openai-completions");
  expect(run.model_routing_revision).toBeGreaterThan(0);
  await page.getByTestId("nav-health").click();
  await page.getByTestId("copilot-role-settings").click();
  await page.getByTestId("copilot-role-summary").selectOption("gpt-6-astra");
  const current = (await (
    await request.get(`${backend}/api/llm/copilot/status`)
  ).json()) as { routing_revision: number };
  const external = await request.post(`${backend}/api/llm/copilot/routing`, {
    headers,
    data: {
      expected_revision: current.routing_revision,
      role_models: { simple_chat: "gpt-5.4-mini" },
    },
  });
  expect(external.ok()).toBe(true);
  await page.getByTestId("copilot-save-routing").click();
  await expect(page.getByRole("alert")).toContainText("routing_changed_reload");
  const after = (await (
    await request.get(`${backend}/api/llm/copilot/status`)
  ).json()) as { role_models: Record<string, string> };
  expect(after.role_models).toEqual({ simple_chat: "gpt-5.4-mini" });
  if (process.env.UPDATE_E2E_EVIDENCE === "true") {
    const dir = path.resolve("../docs/features/assets/ghc-002");
    await mkdir(dir, { recursive: true });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: path.join(dir, "02-stale-routing-rejected.png"),
      fullPage: true,
      animations: "disabled",
    });
  }
});
