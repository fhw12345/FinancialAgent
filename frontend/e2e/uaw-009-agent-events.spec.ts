import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const evidenceDir = path.resolve(
  process.cwd(),
  "..",
  "docs",
  "features",
  "assets",
  "uaw-009",
);
const updateEvidence = process.env.UPDATE_E2E_EVIDENCE === "true";

interface Envelope {
  schema_version: string;
  run_id: string;
  sequence: number;
  type: string;
  payload: Record<string, unknown>;
}

function streamResponse(page: Page, marker: string) {
  return page
    .waitForResponse(
      (response) =>
        response.url().includes("/api/chat/stream") &&
        (response.request().postData() ?? "").includes(marker),
    )
    .then((response) => response.text())
    .then((body) =>
      body
        .split("\n\n")
        .filter((block) => block.startsWith("data: "))
        .map((block) => JSON.parse(block.slice(6)) as Envelope),
    );
}

function assertEnvelopeOrder(events: Envelope[]) {
  expect(events.length).toBeGreaterThan(3);
  expect(events.every((event) => event.schema_version === "1.0")).toBe(true);
  expect(events.map((event) => event.sequence)).toEqual(
    events.map((_, index) => index + 1),
  );
  expect(new Set(events.map((event) => event.run_id)).size).toBe(1);
}

async function send(page: Page, message: string) {
  const response = streamResponse(page, message);
  await page.getByTestId("chat-composer").fill(message);
  await page.getByTestId("chat-send").click();
  return response;
}

test("Direct, ReAct, and Deep use one ordered event envelope @uaw009", async ({
  page,
}) => {
  test.setTimeout(180_000);
  mkdirSync(evidenceDir, { recursive: true });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByTestId("nav-chat").click();

  const directResponse = await send(page, "DIRECT event envelope");
  await expect(
    page.locator("[data-chat-scroll]").getByText("DIRECT_ENVELOPE_OK"),
  ).toBeVisible();
  const directEvents = await directResponse;
  assertEnvelopeOrder(directEvents);
  expect(directEvents.map((event) => event.type)).toEqual(
    expect.arrayContaining([
      "run_started",
      "policy_selected",
      "response_chunk",
      "run_completed",
      "stream_completed",
    ]),
  );
  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "01-direct-envelope-completed.png"),
    });
  }

  await page.getByRole("button", { name: /New Chat|新对话/ }).click();
  const reactResponse = await send(page, "REACT event envelope");
  await expect(
    page.locator("[data-chat-scroll]").getByText("REACT_ENVELOPE_OK"),
  ).toBeVisible();
  const reactEvents = await reactResponse;
  assertEnvelopeOrder(reactEvents);
  expect(reactEvents.map((event) => event.type)).toEqual(
    expect.arrayContaining(["tool_started", "tool_completed"]),
  );
  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "02-react-tool-envelope.png"),
    });
  }

  await page.getByRole("button", { name: /New Chat|新对话/ }).click();
  const deepResponse = await send(page, "DEEP AAPL event envelope");
  await expect(
    page.locator("[data-chat-scroll]").getByText("DEEP_ENVELOPE_OK"),
  ).toBeVisible();
  const deepEvents = await deepResponse;
  assertEnvelopeOrder(deepEvents);
  expect(deepEvents.map((event) => event.type)).toEqual(
    expect.arrayContaining([
      "research_stage_started",
      "research_stage_completed",
    ]),
  );
  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "03-deep-envelope-restored.png"),
    });
  }
});
