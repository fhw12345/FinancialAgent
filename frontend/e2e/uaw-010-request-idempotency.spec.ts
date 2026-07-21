import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const evidenceDir = path.resolve(
  process.cwd(),
  "..",
  "docs",
  "features",
  "assets",
  "uaw-010",
);
const updateEvidence = process.env.UPDATE_E2E_EVIDENCE === "true";
const requestId = "uaw010_fixed_request";

function envelopes(body: string) {
  return body
    .split("\n\n")
    .filter((block) => block.startsWith("data: "))
    .map((block) => JSON.parse(block.slice(6)));
}

test("duplicate request ID replays one completed run @uaw010", async ({
  page,
}) => {
  test.setTimeout(120_000);
  mkdirSync(evidenceDir, { recursive: true });
  await page.route("**/api/chat/stream", async (route) => {
    const body = JSON.parse(route.request().postData() ?? "{}");
    await route.continue({
      postData: JSON.stringify({ ...body, request_id: requestId }),
      headers: {
        ...route.request().headers(),
        "content-type": "application/json",
      },
    });
  });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByTestId("nav-chat").click();

  const firstResponse = page
    .waitForResponse((response) => response.url().includes("/api/chat/stream"))
    .then((response) => response.text());
  await page.getByTestId("chat-composer").fill("DIRECT idempotent request");
  await page.getByTestId("chat-send").click();
  await expect(
    page.locator("[data-chat-scroll]").getByText("DIRECT_ENVELOPE_OK"),
  ).toBeVisible();
  const firstEvents = envelopes(await firstResponse);

  const secondBody = await page.evaluate(
    async ({ id }) => {
      const response = await fetch(
        "http://host.docker.internal:18089/api/chat/stream",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: "DIRECT idempotent request",
            request_id: id,
            agent_version: "auto",
            language: "en",
          }),
        },
      );
      return response.text();
    },
    { id: requestId },
  );
  const secondEvents = envelopes(secondBody);

  expect(secondEvents[0].run_id).toBe(firstEvents[0].run_id);
  expect(secondEvents[0].stream_id).not.toBe(firstEvents[0].stream_id);
  expect(
    secondEvents.some((event) => event.payload?.request_reused === true),
  ).toBe(true);
  const count = await page.evaluate(async () =>
    (
      await fetch(
        "http://host.docker.internal:18089/api/test/idempotency-count",
      )
    ).json(),
  );
  expect(count.execution_count).toBe(1);

  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "01-idempotent-run-replayed.png"),
    });
  }
});
