import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

const evidenceDir = path.resolve(
  process.cwd(),
  "..",
  "docs",
  "features",
  "assets",
  "uaw-002",
);
const updateEvidence = process.env.UPDATE_E2E_EVIDENCE === "true";

async function openChat(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("i18nextLng", "en");
  });
  await page.goto("/");
  await page.getByTestId("nav-chat").click();
  await expect(page.getByTestId("chat-composer")).toBeVisible();
}

async function send(page: Page, message: string) {
  await page.getByTestId("chat-composer").fill(message);
  await page.getByTestId("chat-send").click();
}

function chatText(page: Page, text: string) {
  return page.locator("[data-chat-scroll]").getByText(text, { exact: true });
}

test("Mongo history survives reload @uaw002-seed", async ({
  page,
  request,
}) => {
  await request.delete("http://host.docker.internal:18082/requests");
  await openChat(page);

  const remember = "Explain and remember the exact codeword ORBIT-742.";
  await send(page, remember);
  await expect(chatText(page, "Acknowledged ORBIT-742.")).toBeVisible({
    timeout: 15_000,
  });

  await send(page, "What is the exact codeword I gave you?");
  await expect(
    chatText(page, "The exact codeword is ORBIT-742."),
  ).toBeVisible();

  const captured = await (
    await request.get("http://host.docker.internal:18082/requests")
  ).json();
  const chatRequests = captured.requests.filter(
    (capturedRequest: { stream?: boolean }) => capturedRequest.stream === true,
  );
  const followUpRequest = chatRequests.at(-1);
  const userMessages = followUpRequest.messages.filter(
    (message: { role: string }) => message.role === "user",
  );
  expect(
    userMessages.filter((message: { content: string }) =>
      message.content.includes("ORBIT-742"),
    ),
  ).toHaveLength(1);

  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "01-multi-turn-context-once.png"),
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
    chatText(page, "The exact codeword is ORBIT-742."),
  ).toBeVisible();
  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "02-chat-restored-after-reload.png"),
      fullPage: false,
    });
  }

  await send(page, remember);
  await expect(chatText(page, "Acknowledged ORBIT-742.")).toHaveCount(2);
  const capturedAfterRepeat = await (
    await request.get("http://host.docker.internal:18082/requests")
  ).json();
  const repeatedChatRequests = capturedAfterRepeat.requests.filter(
    (capturedRequest: { stream?: boolean }) => capturedRequest.stream === true,
  );
  const repeatedRequest = repeatedChatRequests.at(-1);
  const repeatedUsers = repeatedRequest.messages.filter(
    (message: { role: string; content: string }) =>
      message.role === "user" && message.content.includes(remember),
  );
  expect(repeatedUsers).toHaveLength(2);
  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "04-identical-user-turns-not-dropped.png"),
      fullPage: false,
    });
  }
});

test("Mongo history survives backend restart @uaw002-resume", async ({
  page,
  request,
}) => {
  const chatList = await (
    await request.get(
      "http://host.docker.internal:18081/api/chat/chats?page=1&page_size=20&include_archived=false",
    )
  ).json();
  const persistedChat = chatList.chats.find((chat: { title: string }) =>
    chat.title.includes("ORBIT"),
  );
  expect(persistedChat).toBeTruthy();

  await openChat(page);
  await page.getByTestId(`chat-item-${persistedChat.chat_id}`).click();

  await send(page, "What is the codeword after backend restart?");
  await expect(
    chatText(page, "After restart, the codeword is still ORBIT-742."),
  ).toBeVisible();
  if (updateEvidence) {
    await page.screenshot({
      path: path.join(evidenceDir, "03-context-survives-backend-restart.png"),
      fullPage: false,
    });
  }
});
