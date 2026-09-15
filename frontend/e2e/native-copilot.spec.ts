import { test, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const backend = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:18094";
const evidence = path.resolve("../docs/features/assets/ghc-001");

test.describe("@real-stack native Copilot", () => {
  test.beforeEach(async ({ page, request }) => {
    await request.post(`${backend}/api/test/copilot/reset`);
    await page.setViewportSize({ width: 1440, height: 1100 });
    await page.goto("/");
    await page.getByTestId("nav-health").click();
    await expect(page.getByTestId("copilot-connection")).toBeVisible();
  });

  test("device login, native inference, chat persistence and logout", async ({
    page,
    request,
  }) => {
    await page.getByTestId("copilot-login").click();
    await expect(page.getByTestId("copilot-user-code")).toHaveText("TEST-CODE");
    await expect(
      page.getByTestId("copilot-device").getByRole("link"),
    ).toHaveAttribute("href", "https://github.com/login/device");
    const pending = await request.get(`${backend}/api/llm/copilot/status`);
    const publicBody = await pending.text();
    for (const secret of ["fake-device", "fake-gh", "fake-cp"])
      expect(publicBody).not.toContain(secret);
    await request.post(`${backend}/api/test/copilot/approve`);
    await expect(page.getByTestId("copilot-models")).toBeVisible({
      timeout: 15000,
    });
    await page.getByTestId("copilot-models").click();
    await expect(
      page.getByTestId("copilot-model-select").locator("option"),
    ).toHaveCount(2);
    const rejected = await request.post(`${backend}/api/llm/copilot/model`, {
      headers: { "X-Financial-Agent-Local": "1" },
      data: { model_id: "gpt-5-disabled" },
    });
    expect(rejected.status()).toBe(422);
    await page.getByTestId("copilot-model-select").selectOption("gpt-6-astra");
    await page.getByTestId("copilot-save-model").click();
    await expect(page.getByTestId("copilot-test")).toBeEnabled();
    await page.getByTestId("copilot-test").click();
    await expect(page.getByTestId("copilot-test-result")).toContainText(
      "gpt-6-astra",
      { timeout: 15000 },
    );
    if (process.env.UPDATE_E2E_EVIDENCE === "true") {
      await mkdir(evidence, { recursive: true });
      await page.screenshot({
        path: path.join(evidence, "01-native-copilot-connected.png"),
        fullPage: true,
        animations: "disabled",
      });
    }
    await page.reload();
    await page.getByTestId("nav-health").click();
    await expect(page.getByTestId("copilot-model-select")).toHaveValue(
      "gpt-6-astra",
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
        .getByText("NATIVE_COPILOT_CHAT_OK", { exact: true }),
    ).toBeVisible();
    const runId = await page
      .getByTestId("run-state")
      .getAttribute("data-run-id");
    const run = await request.get(`${backend}/api/runs/${runId}`);
    const saved = (await run.json()) as { chat_id: string };
    await page.reload();
    await page.getByTestId("nav-chat").click();
    await page.getByTestId(`chat-item-${saved.chat_id}`).click();
    await expect(
      page
        .locator("[data-chat-scroll]")
        .getByText("NATIVE_COPILOT_CHAT_OK", { exact: true }),
    ).toBeVisible();
    await page.getByTestId("nav-health").click();
    await page.getByTestId("copilot-logout").click();
    await expect(page.getByTestId("copilot-login")).toBeVisible();
    const status = await request.get(`${backend}/api/llm/copilot/status`);
    expect(
      ((await status.json()) as { authenticated: boolean }).authenticated,
    ).toBe(false);
    const result = await request.get(`${backend}/api/test/copilot/evidence`);
    const paths = ((await result.json()) as { requests: string[] }).requests;
    expect(paths).toContain("/responses");
    expect(paths).not.toContain("/cc/v1/messages");
  });

  test("expired login and rate-limited inference remain explicit", async ({
    page,
    request,
  }) => {
    await request.post(`${backend}/api/test/copilot/mode/expired`);
    await page.getByTestId("copilot-login").click();
    await expect(page.getByTestId("copilot-login-ended")).toContainText(
      "expired",
      { timeout: 15000 },
    );
    await expect(page.getByTestId("copilot-test")).toHaveCount(0);
    await request.post(`${backend}/api/test/copilot/mode/normal`);
    await page.getByTestId("copilot-login").click();
    await expect(page.getByTestId("copilot-user-code")).toBeVisible();
    await request.post(`${backend}/api/test/copilot/approve`);
    await expect(page.getByTestId("copilot-models")).toBeVisible({
      timeout: 15000,
    });
    await page.getByTestId("copilot-models").click();
    await page.getByTestId("copilot-model-select").selectOption("gpt-6-astra");
    await page.getByTestId("copilot-save-model").click();
    await expect(page.getByTestId("copilot-test")).toBeEnabled();
    await request.post(`${backend}/api/test/copilot/mode/limited`);
    await page.getByTestId("copilot-test").click();
    await expect(page.getByRole("alert")).toContainText("rate_limited");
    await expect(page.getByTestId("copilot-test-result")).toHaveCount(0);
    await expect(page.getByTestId("copilot-test")).toBeEnabled();
    if (process.env.UPDATE_E2E_EVIDENCE === "true") {
      await mkdir(evidence, { recursive: true });
      await page.screenshot({
        path: path.join(evidence, "03-native-copilot-rate-limit.png"),
        fullPage: true,
        animations: "disabled",
      });
    }
  });

  test("denied authorization stays disconnected", async ({ page, request }) => {
    await request.post(`${backend}/api/test/copilot/mode/denied`);
    await page.getByTestId("copilot-login").click();
    await expect(page.getByTestId("copilot-login-ended")).toContainText(
      "denied",
      { timeout: 15000 },
    );
    await expect(page.getByTestId("copilot-test")).toHaveCount(0);
    if (process.env.UPDATE_E2E_EVIDENCE === "true") {
      await mkdir(evidence, { recursive: true });
      await page.screenshot({
        path: path.join(evidence, "02-native-copilot-denied.png"),
        fullPage: true,
        animations: "disabled",
      });
    }
  });
});
