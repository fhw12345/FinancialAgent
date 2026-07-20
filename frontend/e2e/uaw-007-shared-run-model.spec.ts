import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const evidenceDir = path.resolve(
  process.cwd(),
  "..",
  "docs",
  "features",
  "assets",
  "uaw-007",
);
const updateEvidence = process.env.UPDATE_E2E_EVIDENCE === "true";
const backendUrl = "http://host.docker.internal:18087";

async function fetchRun(page: Page, runId: string) {
  return page.evaluate(
    async ({ url, id }) => {
      const response = await fetch(`${url}/api/runs/${id}`);
      if (!response.ok) {
        throw new Error(`Run lookup failed: ${response.status}`);
      }
      return response.json();
    },
    { url: backendUrl, id: runId },
  );
}

test("One durable run spans routing, execution, and reload @uaw007", async ({
  page,
}) => {
  test.setTimeout(90_000);
  mkdirSync(evidenceDir, { recursive: true });

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByTestId("nav-chat").click();
  await page.getByTestId("chat-composer").fill("Explain this concept.");
  await page.getByTestId("chat-send").click();

  const runBadge = page.getByTestId("run-state");
  await expect(runBadge).toHaveAttribute("data-run-status", "running", {
    timeout: 20_000,
  });
  const runId = await runBadge.getAttribute("data-run-id");
  expect(runId).toBeTruthy();
  await expect(
    page.locator("[data-chat-scroll]").getByText(/RUN_STARTED/),
  ).toBeVisible({ timeout: 20_000 });
  await expect(
    page.locator("[data-chat-scroll]").getByText(/RUN_COMPLETED/),
  ).toHaveCount(0);

  const runningRun = (await fetchRun(page, runId as string)) as {
    status: string;
    execution_mode: string;
    selected_policy: string;
    policy_version: string;
    prompt_versions: Record<string, string>;
    model_routes: Record<string, string>;
  };
  expect(runningRun.status).toBe("running");
  expect(runningRun.execution_mode).toBe("instant");
  expect(runningRun.selected_policy).toBe("v2");
  expect(runningRun.policy_version).toBe("auto-router-v1");
  expect(runningRun.prompt_versions.simple_chat).toBe("simple-chat-v1");
  expect(runningRun.model_routes.simple_chat).toBeTruthy();

  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "01-durable-run-running.png"),
      fullPage: false,
    });
  }

  await expect(
    page.locator("[data-chat-scroll]").getByText(/RUN_COMPLETED/),
  ).toBeVisible({ timeout: 10_000 });
  await expect(runBadge).toHaveAttribute("data-run-status", "completed");
  const completedRun = (await fetchRun(page, runId as string)) as {
    status: string;
    chat_id: string;
    input_tokens: number;
    output_tokens: number;
    tool_calls: number;
  };
  expect(completedRun.status).toBe("completed");
  expect(completedRun.chat_id).toBeTruthy();
  expect(completedRun.input_tokens).toBe(2);
  expect(completedRun.output_tokens).toBe(1);
  expect(completedRun.tool_calls).toBe(0);

  const chatId = (
    await page.locator("[data-chat-scroll] .font-mono").first().textContent()
  )?.trim();
  expect(chatId).toBeTruthy();
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByTestId("nav-chat").click();
  await page.getByTestId(`chat-item-${chatId}`).click();
  await expect(page.getByTestId("run-state")).toHaveAttribute(
    "data-run-id",
    runId as string,
  );
  await expect(page.getByTestId("run-state")).toHaveAttribute(
    "data-run-status",
    "completed",
  );

  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "02-durable-run-restored.png"),
      fullPage: false,
    });
  }
});
