import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const evidenceDir = path.resolve(
  process.cwd(),
  "..",
  "docs",
  "features",
  "assets",
  "uaw-008",
);
const updateEvidence = process.env.UPDATE_E2E_EVIDENCE === "true";

async function openChat(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("i18nextLng", "en");
  });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByTestId("nav-chat").click();
  await expect(page.getByTestId("chat-composer")).toBeVisible();
}

async function currentChatId(page: Page) {
  const value = (
    await page.locator("[data-chat-scroll] .font-mono").first().textContent()
  )?.trim();
  expect(value).toBeTruthy();
  return value as string;
}

test("shared lifecycle preserves completion, clarification, and reload @uaw008", async ({
  page,
}) => {
  test.setTimeout(180_000);
  mkdirSync(evidenceDir, { recursive: true });
  await openChat(page);

  await page.getByTestId("chat-composer").fill("Explain lifecycle ownership.");
  await page.getByTestId("chat-send").click();
  await expect(
    page.locator("[data-chat-scroll]").getByText("LIFECYCLE_DIRECT_COMPLETE"),
  ).toBeVisible({ timeout: 20_000 });
  const directRun = page.getByTestId("run-state");
  await expect(directRun).toHaveAttribute("data-run-status", "completed");
  const directRunId = await directRun.getAttribute("data-run-id");
  const directChatId = await currentChatId(page);

  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByTestId("nav-chat").click();
  await page.getByTestId(`chat-item-${directChatId}`).click();
  await expect(page.getByTestId("run-state")).toHaveAttribute(
    "data-run-id",
    directRunId as string,
  );
  await expect(page.getByTestId("run-state")).toHaveAttribute(
    "data-run-status",
    "completed",
  );

  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "01-direct-lifecycle-restored.png"),
      fullPage: false,
    });
  }

  await page.getByRole("button", { name: /New Chat|新对话/ }).click();
  await page.getByTestId("chat-composer").fill("Deeply analyze Alpha.");
  await page.getByTestId("chat-send").click();

  await expect(page.getByTestId("symbol-clarification")).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByTestId("symbol-candidate-AAA")).toContainText(
    "Alpha A",
  );
  await expect(page.getByTestId("run-state")).toHaveAttribute(
    "data-run-status",
    "waiting_for_input",
  );
  const clarificationRunId = await page
    .getByTestId("run-state")
    .getAttribute("data-run-id");
  const clarificationChatId = await currentChatId(page);

  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByTestId("nav-chat").click();
  await page.getByTestId(`chat-item-${clarificationChatId}`).click();
  await expect(page.getByTestId("symbol-clarification")).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByTestId("run-state")).toHaveAttribute(
    "data-run-id",
    clarificationRunId as string,
  );
  await expect(page.getByTestId("run-state")).toHaveAttribute(
    "data-run-status",
    "waiting_for_input",
  );

  if (updateEvidence) {
    await page.screenshot({
      path: path.join(
        evidenceDir,
        "02-deep-clarification-lifecycle-restored.png",
      ),
      fullPage: false,
    });
  }
});
