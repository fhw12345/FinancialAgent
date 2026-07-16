import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

const evidenceDir = path.resolve(
  process.cwd(),
  "..",
  "docs",
  "features",
  "assets",
  "uaw-001",
);
const updateEvidence = process.env.UPDATE_E2E_EVIDENCE === "true";

const candidates = [
  {
    symbol: "AAA",
    name: "Alpha A",
    exchange: "NYSE",
    confidence: 0.9,
  },
  {
    symbol: "AAB",
    name: "Alpha B",
    exchange: "NASDAQ",
    confidence: 0.85,
  },
];

async function openChat(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("i18nextLng", "en");
  });
  await page.goto("/");
  await page.getByTestId("nav-chat").click();
  await expect(page.getByTestId("chat-composer")).toBeVisible();
}

async function installMockChatApi(page: Page) {
  await page.route("**/api/market/price/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        symbol: "AAA",
        interval: "1d",
        last_updated: "2026-07-15T09:00:00Z",
        data: [
          {
            time: "2026-07-14",
            open: 99,
            high: 102,
            low: 98,
            close: 101,
            volume: 100000,
          },
          {
            time: "2026-07-15",
            open: 101,
            high: 104,
            low: 100,
            close: 103,
            volume: 120000,
          },
        ],
      }),
    });
  });
  await page.route("**/api/chat/chats**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        chats: [],
        total: 0,
        page: 1,
        page_size: 20,
      }),
    });
  });
  await page.route("**/api/chat/stream", async (route) => {
    const events = [
      {
        type: "route_selected",
        flow: "v4-deep",
        source: "rule",
        reason_code: "deep_financial_request",
      },
      { type: "chat_created", chat_id: "chat_mock" },
      {
        type: "clarification_required",
        clarification_type: "symbol",
        reason_code: "ambiguous_symbol",
        message: "Please select the company you want to analyze.",
        original_request: "Deeply analyze Alpha",
        candidates,
      },
      {
        type: "done",
        chat_id: "chat_mock",
        clarification_required: true,
      },
    ];
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: events
        .map((event) => `data: ${JSON.stringify(event)}\n\n`)
        .join(""),
    });
  });
}

test("ambiguous symbols render validated candidates", async ({ page }) => {
  await installMockChatApi(page);
  await openChat(page);

  await page.getByTestId("chat-composer").fill("Deeply analyze Alpha");
  await page.getByTestId("chat-send").click();

  const card = page.getByTestId("symbol-clarification");
  await expect(card).toBeVisible();
  await expect(page.getByTestId("symbol-candidate-AAA")).toContainText(
    "Alpha A",
  );
  await expect(page.getByTestId("symbol-candidate-AAB")).toContainText(
    "Alpha B",
  );
  await expect(page.getByTestId("deep-agent-accordion")).toHaveCount(0);
  await expect(page.getByTestId("chat-error")).toHaveCount(0);

  if (updateEvidence) {
    await card.screenshot({
      path: path.join(evidenceDir, "01-ambiguous-symbol-candidates.png"),
    });
  }
});

test("candidate selection updates context without auto-submitting", async ({
  page,
}) => {
  await installMockChatApi(page);
  await openChat(page);

  let streamRequests = 0;
  page.on("request", (request) => {
    if (request.url().includes("/api/chat/stream")) {
      streamRequests += 1;
    }
  });

  await page.getByTestId("chat-composer").fill("Deeply analyze Alpha");
  await page.getByTestId("chat-send").click();
  await page.getByTestId("symbol-candidate-AAA").click();

  await expect(page.getByTestId("chat-composer")).toHaveValue(/AAA/);
  await expect(page.getByTestId("symbol-search-input")).toHaveValue(
    "AAA - Alpha A",
  );
  expect(streamRequests).toBe(1);

  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "03-candidate-selected-follow-up-ready.png"),
      fullPage: false,
    });
  }
});

test("unresolved request stops before research and restores @real-stack", async ({
  page,
}) => {
  await openChat(page);

  await page.route("**/api/chat/stream", async (route) => {
    const request = route.request();
    const body = JSON.parse(request.postData() ?? "{}");
    await route.continue({
      postData: JSON.stringify({
        ...body,
        agent_version: "v4-deep",
      }),
      headers: {
        ...request.headers(),
        "content-type": "application/json",
      },
    });
  });

  await page
    .getByTestId("chat-composer")
    .fill("请完整分析我昨天看到的那家公司");
  await page.getByTestId("chat-send").click();

  const card = page.getByTestId("symbol-clarification");
  await expect(card).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("deep-agent-accordion")).toHaveCount(0);
  await expect(page.getByTestId("chat-error")).toHaveCount(0);

  if (updateEvidence) {
    await card.screenshot({
      path: path.join(evidenceDir, "02-unresolved-symbol-real-stack.png"),
    });
  }

  const chatIdText = await page
    .locator("[data-chat-scroll] .font-mono")
    .first()
    .textContent();
  expect(chatIdText).toBeTruthy();
  const chatId = chatIdText?.trim() ?? "";

  await page.reload();
  await page.getByTestId("nav-chat").click();
  await page.getByTestId(`chat-item-${chatId}`).click();
  await expect(page.getByTestId("symbol-clarification")).toBeVisible({
    timeout: 15_000,
  });

  if (updateEvidence) {
    await page.getByTestId("symbol-clarification").screenshot({
      path: path.join(evidenceDir, "04-restored-clarification.png"),
    });
  }
});
