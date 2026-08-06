import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChatMessages } from "../ChatMessages";

vi.mock("../../../hooks/useTranslated", () => ({
  useTranslated: (text: string | null) => ({
    text: text ?? "",
    isLoading: false,
  }),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en" },
  }),
}));

describe("ChatMessages untrusted Markdown", () => {
  it("drops raw HTML while preserving safe GFM and isolated links", () => {
    const content = [
      "# Safe heading",
      "",
      "<script>window.__owned = true</script>",
      "",
      '<iframe src="https://attacker.invalid/embed"></iframe>',
      "",
      '<img src="https://attacker.invalid/pixel" onerror="alert(1)">',
      "",
      "| A | B |",
      "| - | - |",
      "| 1 | 2 |",
      "",
      "[Safe link](https://example.com/research)",
    ].join("\n");

    const { container } = render(
      <ChatMessages
        messages={[
          {
            _id: "assistant-security",
            role: "assistant",
            content,
            timestamp: "2026-08-06T00:00:00Z",
          },
        ]}
        isAnalysisPending={false}
        chatId={null}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Safe heading" }),
    ).not.toBeNull();
    expect(screen.getByRole("table")).not.toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("iframe")).toBeNull();
    expect(container.querySelector("img")).toBeNull();

    const link = screen.getByRole("link", { name: "Safe link" });
    expect(link.getAttribute("href")).toBe("https://example.com/research");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  });
});
