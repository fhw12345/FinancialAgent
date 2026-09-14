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

function renderHistory(content: string) {
  return render(
    <ChatMessages
      messages={[
        {
          _id: "historical-security",
          role: "assistant",
          content,
          timestamp: "2026-08-06T00:00:00Z",
        },
      ]}
      isAnalysisPending={false}
      chatId={null}
    />,
  );
}

describe("ChatMessages untrusted Markdown", () => {
  it("rejects Markdown tracking images in historical messages", () => {
    const { container } = renderHistory(
      "# 历史研究 / Historical research\n\n![tracker](https://attacker.invalid/pixel)",
    );
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByRole("heading").textContent).toContain("历史研究");
  });

  it.each([
    "[unsafe](javascript:alert%281%29)",
    "[unsafe](data:text/html;base64,PHNjcmlwdD4=)",
    "[unsafe](vbscript:msgbox%281%29)",
  ])("rejects unsafe link schemes: %s", (content) => {
    const { container } = renderHistory(content);
    const href = container.querySelector("a")?.getAttribute("href");
    expect(href == null || href === "").toBe(true);
  });

  it("keeps an active-HTML corpus inert without losing fenced code and GFM", () => {
    const { container } = renderHistory(
      [
        "<form action='https://attacker.invalid/'><input autofocus></form>",
        "<svg><a href='javascript:alert(1)'>svg</a></svg>",
        "<math><mtext><img src=x onerror='alert(1)'></mtext></math>",
        "<object data='https://attacker.invalid/'></object><embed src=x>",
        "<style>body{display:none}</style><meta http-equiv=refresh content=0>",
        "<a href='https://example.com' onclick='alert(1)'>raw link</a>",
        "\n## 安全研究 / Safe research\n\n- List item\n\n> Quote\n",
        "```python\nprint('safe code')\n```",
      ].join("\n\n"),
    );
    expect(
      container.querySelector(
        "form, input, svg, math, object, embed, style, meta, [onclick], [onerror]",
      ),
    ).toBeNull();
    expect(screen.getByRole("heading").textContent).toContain("Safe research");
    expect(screen.getByRole("listitem").textContent).toBe("List item");
    expect(container.querySelector("blockquote")?.textContent).toContain(
      "Quote",
    );
    expect(container.querySelector("code")?.textContent).toContain("safe code");
  });

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
