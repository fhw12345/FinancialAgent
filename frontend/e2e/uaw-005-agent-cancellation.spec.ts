import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const evidenceDir = path.resolve(
  process.cwd(),
  "..",
  "docs",
  "features",
  "assets",
  "uaw-005",
);
const updateEvidence = process.env.UPDATE_E2E_EVIDENCE === "true";
const backendUrl = "http://host.docker.internal:18085";

async function cancellationStatus(page: Page) {
  const response = await page.request.get(
    `${backendUrl}/api/e2e/cancellation-status`,
  );
  expect(response.ok()).toBe(true);
  return (await response.json()) as {
    agent_started: boolean;
    agent_cancelled: boolean;
    child_cancelled: boolean;
    agent_completed: boolean;
    late_event_emitted: boolean;
    cancellation_persisted: boolean;
  };
}

test("Stop cancels backend agent work and persists status @uaw005", async ({
  page,
}) => {
  test.setTimeout(90_000);
  mkdirSync(evidenceDir, { recursive: true });

  await page.goto("/");
  await page.getByTestId("nav-chat").click();
  await expect(page.getByTestId("chat-composer")).toBeVisible();

  await page
    .getByTestId("chat-composer")
    .fill("What is the current AAPL price? Use tools.");
  await page.getByTestId("chat-send").click();
  await expect(page.getByTestId("chat-stop")).toBeVisible();
  await expect(page.getByText("Cancellation Probe")).toBeVisible({
    timeout: 20_000,
  });

  const stopClicked = await page.evaluate(() => {
    const button = document.querySelector<HTMLButtonElement>(
      '[data-testid="chat-stop"]',
    );
    if (!button) return false;
    button.click();
    return true;
  });
  expect(stopClicked).toBe(true);
  await expect(page.getByTestId("chat-composer")).toBeEnabled();
  await expect(
    page
      .locator("[data-chat-scroll]")
      .getByText(/Request cancelled|请求已取消/)
      .last(),
  ).toBeVisible();

  await expect
    .poll(async () => {
      const status = await cancellationStatus(page);
      return {
        agent_cancelled: status.agent_cancelled,
        child_cancelled: status.child_cancelled,
        agent_completed: status.agent_completed,
        cancellation_persisted: status.cancellation_persisted,
      };
    })
    .toEqual({
      agent_cancelled: true,
      child_cancelled: true,
      agent_completed: false,
      cancellation_persisted: true,
    });

  await page.waitForTimeout(1_800);
  expect((await cancellationStatus(page)).late_event_emitted).toBe(false);

  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "01-stop-cancels-active-run.png"),
      fullPage: false,
    });
  }

  const chatId = (
    await page.locator("[data-chat-scroll] .font-mono").first().textContent()
  )?.trim();
  expect(chatId).toBeTruthy();

  await page.reload();
  await page.getByTestId("nav-chat").click();
  await page.getByTestId(`chat-item-${chatId}`).click();
  await expect(
    page
      .locator("[data-chat-scroll]")
      .getByText(/Request cancelled|请求已取消/)
      .last(),
  ).toBeVisible();

  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "02-cancelled-status-after-reload.png"),
      fullPage: false,
    });
  }
});
