import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const updateEvidence = process.env.UPDATE_E2E_EVIDENCE === "true";

async function openEnglishApp(page: import("@playwright/test").Page) {
  await page.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  await page.goto("/", { waitUntil: "domcontentloaded" });
}

test("loopback-bound real stack remains healthy @project-hardening @real-stack", async ({
  page,
}) => {
  await openEnglishApp(page);
  await page.getByTestId("nav-health").click();
  await expect(page.getByText(/^v0\.51\.\d+$/, { exact: true })).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByText("HEALTHY", { exact: true })).toBeVisible();

  if (updateEvidence) {
    const dir = path.resolve(
      process.cwd(),
      "..",
      "docs",
      "features",
      "assets",
      "ph-001",
    );
    mkdirSync(dir, { recursive: true });
    await page.screenshot({
      path: path.join(dir, "01-loopback-stack-healthy.png"),
      fullPage: true,
    });
  }
});

test("untrusted assistant HTML stays inert @project-hardening", async ({
  page,
}) => {
  await page.route("**/api/chat/chats**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ chats: [], total: 0, page: 1, page_size: 20 }),
    }),
  );
  await page.route("**/api/chat/stream", (route) => {
    const content = [
      "# Sanitized research",
      "",
      '<iframe src="https://attacker.invalid/embed"></iframe>',
      "",
      '<img src="https://attacker.invalid/pixel" onerror="alert(1)">',
      "",
      "| Signal | Value |",
      "| --- | --- |",
      "| Safety | Pass |",
      "",
      "[Source](https://example.com/research)",
    ].join("\n");
    const events = [
      { type: "chat_created", chat_id: "chat_security" },
      { type: "tool_start", tool_name: 42, inputs: "malformed" },
      { type: "chunk", content },
      { type: "done", chat_id: "chat_security", message_count: 2 },
    ];
    return route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: events
        .map((event) => `data: ${JSON.stringify(event)}\n\n`)
        .join(""),
    });
  });

  const externalRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("attacker.invalid"))
      externalRequests.push(request.url());
  });

  await openEnglishApp(page);
  await page.getByTestId("nav-chat").click();
  await page.getByTestId("chat-composer").fill("Render security fixture");
  await page.getByTestId("chat-send").click();

  const chat = page.locator("[data-chat-scroll]");
  await expect(
    chat.getByRole("heading", { name: "Sanitized research" }),
  ).toBeVisible();
  await expect(chat.getByRole("table")).toBeVisible();
  await expect(
    chat.locator("iframe, script, img, form, object, embed"),
  ).toHaveCount(0);
  await expect(chat.getByRole("link", { name: "Source" })).toHaveAttribute(
    "rel",
    "noopener noreferrer",
  );
  expect(externalRequests).toEqual([]);

  if (updateEvidence) {
    const securityDir = path.resolve(
      process.cwd(),
      "..",
      "docs",
      "features",
      "assets",
      "ph-005",
    );
    const typedStreamDir = path.resolve(
      process.cwd(),
      "..",
      "docs",
      "features",
      "assets",
      "ph-006",
    );
    mkdirSync(securityDir, { recursive: true });
    mkdirSync(typedStreamDir, { recursive: true });
    await page.screenshot({
      path: path.join(securityDir, "01-sanitized-agent-markdown.png"),
    });
    await page.screenshot({
      path: path.join(typedStreamDir, "01-typed-stream-recovery.png"),
    });
  }
});

test("insights refresh completes through the visible UI @project-hardening", async ({
  page,
}) => {
  const category = {
    id: "ai_sector_risk",
    name: "AI Sector Risk",
    icon: "🤖",
    description: "Deterministic shared-prefetch fixture",
    metrics: [
      {
        id: "valuation",
        name: "Valuation Risk",
        score: 62,
        status: "elevated",
        explanation: {
          summary: "Elevated",
          detail: "Fixture detail",
          methodology: "Fixture methodology",
          formula: null,
          historical_context: "Fixture context",
          actionable_insight: "Review concentration",
        },
        data_sources: ["deterministic-prefetch"],
        last_updated: "2026-08-06T00:00:00Z",
        raw_data: {},
      },
    ],
    composite: {
      score: 62,
      status: "elevated",
      weights: { valuation: 1 },
      breakdown: { valuation: 62 },
      interpretation: "Elevated fixture risk",
    },
    last_updated: "2026-08-06T00:00:00Z",
  };
  await page.route("**/api/insights/categories", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        categories: [
          {
            id: category.id,
            name: category.name,
            icon: category.icon,
            description: category.description,
            metric_count: 1,
            last_updated: category.last_updated,
          },
        ],
        count: 1,
      }),
    }),
  );
  await page.route("**/api/insights/ai_sector_risk/trend**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        category_id: category.id,
        days: 30,
        trend: [],
        metrics: {},
      }),
    }),
  );
  await page.route("**/api/insights/ai_sector_risk/refresh", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        category_id: category.id,
        message: "Shared prefetch completed",
        last_updated: category.last_updated,
      }),
    }),
  );
  await page.route("**/api/insights/ai_sector_risk?**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(category),
    }),
  );

  await openEnglishApp(page);
  await page.getByTestId("nav-insights").click();
  await page.getByRole("button", { name: /AI Sector Risk/ }).click();
  await expect(page.getByText("Valuation Risk")).toBeVisible();
  const refreshResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/insights/ai_sector_risk/refresh"),
  );
  await page.getByTestId("refresh-insight-category").click();
  expect((await refreshResponse).ok()).toBe(true);
  await expect(page.getByText("Elevated fixture risk")).toBeVisible();

  if (updateEvidence) {
    const dir = path.resolve(
      process.cwd(),
      "..",
      "docs",
      "features",
      "assets",
      "ph-002",
    );
    mkdirSync(dir, { recursive: true });
    await page.screenshot({
      path: path.join(dir, "01-shared-prefetch-refresh.png"),
      fullPage: true,
    });
  }
});

test("clean rebuilt images serve health and deterministic chat @project-hardening @ph008 @real-stack", async ({
  page,
  request,
}) => {
  const backendUrl =
    process.env.PH008_BACKEND_URL ??
    process.env.E2E_BACKEND_URL ??
    "http://host.docker.internal:18081";
  const health = await request.get(`${backendUrl}/api/health`);
  expect(health.ok()).toBe(true);

  await openEnglishApp(page);
  await page.getByTestId("nav-health").click();
  await expect(page.getByText("HEALTHY", { exact: true })).toBeVisible({
    timeout: 15_000,
  });

  await page.getByTestId("nav-chat").click();
  await page
    .getByTestId("chat-composer")
    .fill("Remember CLEAN-008 for the clean build smoke.");
  await page.getByTestId("chat-send").click();
  await expect(
    page.locator("[data-chat-scroll]").getByText("Acknowledged CLEAN-008."),
  ).toBeVisible({ timeout: 30_000 });

  if (updateEvidence) {
    const dir = path.resolve(
      process.cwd(),
      "..",
      "docs",
      "features",
      "assets",
      "ph-008",
    );
    mkdirSync(dir, { recursive: true });
    await page.screenshot({
      path: path.join(dir, "01-clean-build-runtime.png"),
      fullPage: true,
    });
  }
});

test("health diagnostics show matching component versions @project-hardening", async ({
  page,
}) => {
  await page.route("**/api/admin/health", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        timestamp: "2026-08-06T00:00:00Z",
        database: [],
        health_status: "healthy",
      }),
    }),
  );
  await page.route("**/api/health", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok", version: "0.51.4" }),
    }),
  );

  await openEnglishApp(page);
  await page.getByTestId("nav-health").click();
  await expect(page.getByText("v0.32.4", { exact: true })).toBeVisible();
  await expect(page.getByText("v0.51.4", { exact: true })).toBeVisible();

  if (updateEvidence) {
    const dir = path.resolve(
      process.cwd(),
      "..",
      "docs",
      "features",
      "assets",
      "ph-010",
    );
    mkdirSync(dir, { recursive: true });
    await page.screenshot({
      path: path.join(dir, "01-version-diagnostics.png"),
    });
  }
});
