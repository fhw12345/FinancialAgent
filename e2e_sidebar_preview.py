"""Verify sidebar preview now uses content_zh directly (no /api/translate
network round-trip for previews)."""

from __future__ import annotations
import io
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SCREEN_DIR = Path(__file__).parent / "e2e_screens"
SCREEN_DIR.mkdir(exist_ok=True)
URL = "http://localhost:3001"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(locale="zh-CN", viewport={"width": 1600, "height": 900})
            page = ctx.new_page()

            translate_calls: list[str] = []
            page.on(
                "response",
                lambda r: translate_calls.append(r.url)
                if "/api/translate" in r.url and r.request.method == "POST"
                else None,
            )

            page.goto(URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(8000)

            page_text = page.evaluate("() => document.body.innerText")
            # Markers: previously English preview leaked into sidebar
            english_in_preview = [
                "Portfolio Trading Decisions",
                "Symbols Analyzed:",
            ]
            chinese_in_preview = [
                "投资组合交易决策",
                "AI 智能体分析",
                "AI 代理分析",
                "AI 智能代理分析",
            ]
            en_hits = [m for m in english_in_preview if m in page_text]
            zh_hits = [m for m in chinese_in_preview if m in page_text]
            print(f"English preview markers: {en_hits}")
            print(f"Chinese preview markers: {zh_hits}")
            print(f"\n/api/translate POST calls during initial render: {len(translate_calls)}")
            for u in translate_calls[:5]:
                print(f"  {u}")
            page.screenshot(path=str(SCREEN_DIR / "sidebar_preview_zh.png"), full_page=True)
            if zh_hits and not en_hits:
                print("\nVERDICT: PASS — sidebar preview is Chinese, no English leak.")
            else:
                print(f"\nVERDICT: REVIEW — en={en_hits} zh={zh_hits}")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
