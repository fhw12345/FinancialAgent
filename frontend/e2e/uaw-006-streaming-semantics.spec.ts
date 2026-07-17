import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const evidenceDir = path.resolve(
  process.cwd(),
  "..",
  "docs",
  "features",
  "assets",
  "uaw-006",
);
const updateEvidence = process.env.UPDATE_E2E_EVIDENCE === "true";

async function openChat(page: Page) {
  await page.goto("/", {
    waitUntil: "domcontentloaded",
    timeout: 30_000,
  });
  await page.getByTestId("nav-chat").click();
  await expect(page.getByTestId("chat-composer")).toBeVisible();
}

async function send(page: Page, message: string) {
  await page.getByTestId("chat-composer").fill(message);
  await page.getByTestId("chat-send").click();
}

test("Streaming mode labels match actual delivery @uaw006", async ({
  page,
}) => {
  test.setTimeout(120_000);
  mkdirSync(evidenceDir, { recursive: true });
  await openChat(page);

  await send(page, "Explain this concept using a live stream.");
  await expect(page.getByTestId("response-stream-mode")).toHaveAttribute(
    "data-stream-mode",
    "model_tokens",
    { timeout: 30_000 },
  );
  await expect(
    page.locator("[data-chat-scroll]").getByText(/FIRST_TOKEN/),
  ).toBeVisible({ timeout: 30_000 });
  await expect(
    page.locator("[data-chat-scroll]").getByText(/SECOND_TOKEN/),
  ).toHaveCount(0);

  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "01-live-model-token-stream.png"),
      fullPage: false,
    });
  }

  await expect(
    page.locator("[data-chat-scroll]").getByText(/SECOND_TOKEN/),
  ).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("chat-composer")).toBeEnabled();

  await page.getByRole("button", { name: /New Chat|新对话/ }).click();
  await expect(page.getByTestId("response-stream-mode")).toHaveCount(0);
  await send(page, "What is the current AAPL price?");
  await expect(page.getByTestId("response-stream-mode")).toHaveAttribute(
    "data-stream-mode",
    "buffered",
    { timeout: 30_000 },
  );
  await expect(page.getByText("Buffered Progress")).toBeVisible({
    timeout: 30_000,
  });
  await expect(
    page.locator("[data-chat-scroll]").getByText("BUFFERED_RESPONSE_COMPLETE"),
  ).toHaveCount(0);

  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "02-buffered-response-labelled.png"),
      fullPage: false,
    });
  }

  await expect(
    page.locator("[data-chat-scroll]").getByText("BUFFERED_RESPONSE_COMPLETE"),
  ).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("chat-composer")).toBeEnabled();
});
