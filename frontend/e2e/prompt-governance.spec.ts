import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const evidenceDir = path.resolve(
  process.cwd(),
  "..",
  "docs",
  "features",
  "assets",
  "prompt-governance",
);
const updateEvidence = process.env.UPDATE_E2E_EVIDENCE === "true";
const backendUrl = "http://host.docker.internal:18089";

async function fetchRun(page: Page, runId: string) {
  return page.evaluate(
    async ({ url, id }) => (await fetch(`${url}/api/runs/${id}`)).json(),
    { url: backendUrl, id: runId },
  );
}

async function sendChat(page: Page, message: string) {
  await page.getByTestId("chat-composer").fill(message);
  await page.getByTestId("chat-send").click();
  await expect(page.getByTestId("run-state")).toHaveAttribute(
    "data-run-status",
    "completed",
    { timeout: 20_000 },
  );
  return (await page
    .getByTestId("run-state")
    .getAttribute("data-run-id")) as string;
}

test("prompt governance versions survive chat and Portfolio UI flows", async ({
  page,
}) => {
  test.setTimeout(120_000);
  mkdirSync(evidenceDir, { recursive: true });
  await page.addInitScript(() =>
    window.localStorage.setItem("i18nextLng", "en"),
  );
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByTestId("nav-chat").click();

  const directRunId = await sendChat(page, "DIRECT governed prompt");
  const directRun = await fetchRun(page, directRunId);
  expect(directRun.prompt_versions["financial-system"]).toBe(
    "financial-system@3",
  );

  await page.getByRole("button", { name: /New Chat|新对话/ }).click();
  const deepRunId = await sendChat(page, "DEEP AAPL governed prompt");
  const deepRun = await fetchRun(page, deepRunId);
  expect(deepRun.prompt_versions["deep-debater"]).toBe("deep-debater@2");
  expect(deepRun.prompt_versions["deep-verdict"]).toBe("deep-verdict@1");

  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "01-chat-prompt-versions.png"),
    });
  }

  await page.getByTestId("nav-portfolio").click();
  await page.getByRole("button", { name: "Analyze My Holdings" }).click();
  await expect(page.getByText("PROMPT_GOVERNANCE_PORTFOLIO_OK")).toBeVisible({
    timeout: 20_000,
  });
  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "02-portfolio-flow-completed.png"),
    });
  }
});
