import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

const evidenceDir = path.resolve(
  process.cwd(),
  "..",
  "docs",
  "features",
  "assets",
  "uaw-003",
);
const updateEvidence = process.env.UPDATE_E2E_EVIDENCE === "true";

async function installMarketMocks(page: Page) {
  await page.route("**/api/market/search?q=SKHY", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        query: "SKHY",
        results: [
          {
            symbol: "SKHY",
            name: "SK hynix Inc.",
            exchange: "NASDAQ",
            type: "Equity",
            match_type: "exact_symbol",
            confidence: 1,
          },
        ],
      }),
    });
  });
  await page.route("**/api/market/price/SKHY**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        symbol: "SKHY",
        interval: "1d",
        last_updated: "2026-07-16T09:00:00Z",
        data: [
          {
            time: "2026-07-15",
            open: 170,
            high: 180,
            low: 168,
            close: 176,
            volume: 100000,
          },
          {
            time: "2026-07-16",
            open: 176,
            high: 179,
            low: 172,
            close: 175,
            volume: 90000,
          },
        ],
      }),
    });
  });
}

async function openChat(page: Page) {
  await page.goto("/");
  await page.getByTestId("nav-chat").click();
  await expect(page.getByTestId("chat-composer")).toBeVisible();
}

async function selectSkhy(page: Page) {
  const search = page.getByTestId("symbol-search-input");
  await search.fill("SKHY");
  await search.press("Enter");
  await expect(search).toHaveValue("SKHY - SK hynix Inc.");
}

async function send(page: Page, message: string) {
  await page.getByTestId("chat-composer").fill(message);
  await page.getByTestId("chat-send").click();
}

function chatText(page: Page, text: string | RegExp) {
  return page.locator("[data-chat-scroll]").getByText(text);
}

async function scrollChatToBottom(page: Page) {
  await page.locator("[data-chat-scroll]").evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  await page.waitForTimeout(300);
}

test("Deep follow-up receives prior thesis and constraints @uaw003", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await installMarketMocks(page);
  await openChat(page);
  await selectSkhy(page);

  await send(
    page,
    "Deep analysis of SKHY over a 6 month horizon with moderate risk; focus on valuation.",
  );
  await expect(chatText(page, /Baseline Deep Research for SKHY/)).toBeVisible({
    timeout: 20_000,
  });
  await expect(chatText(page, /Horizon: 6 months/)).toBeVisible();
  await expect(chatText(page, /Risk tolerance: moderate/)).toBeVisible();

  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "02-horizon-preserved.png"),
      fullPage: false,
    });
  }

  await send(
    page,
    "Deep analysis: analyze this stock by challenging that thesis more aggressively and focus on downside risk.",
  );
  await expect(chatText(page, /Follow-up Deep Research for SKHY/)).toBeVisible({
    timeout: 20_000,
  });
  await expect(
    chatText(page, /Previous thesis retained: Baseline/),
  ).toBeVisible();
  await expect(
    chatText(page, /valuation_focus, downside_focus, adversarial_review/),
  ).toBeVisible();

  if (updateEvidence) {
    await scrollChatToBottom(page);
    await page.screenshot({
      path: path.join(evidenceDir, "01-prior-thesis-challenged.png"),
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
  await expect(page.getByTestId("chat-composer")).toBeEnabled();
  const followUpResponses = chatText(page, /Follow-up Deep Research for SKHY/);
  await expect(followUpResponses).toHaveCount(1);
  await send(
    page,
    "Deep analysis: analyze this stock using the same constraints and continue the downside risk review.",
  );
  await expect(followUpResponses).toHaveCount(2, { timeout: 20_000 });
  await expect(page.getByTestId("chat-composer")).toBeEnabled({
    timeout: 20_000,
  });
  await expect(chatText(page, /Risk tolerance: moderate/).last()).toBeVisible({
    timeout: 20_000,
  });
  await expect(
    chatText(page, /valuation_focus, downside_focus/).last(),
  ).toBeVisible();

  if (updateEvidence) {
    await scrollChatToBottom(page);
    await page.screenshot({
      path: path.join(evidenceDir, "03-constraints-restored-after-reload.png"),
      fullPage: false,
    });
    await chatText(page, /Context metadata: turns=/)
      .last()
      .screenshot({
        path: path.join(
          evidenceDir,
          "04-context-metadata-visible-in-history.png",
        ),
      });
  }
});
