"""Final verification: open the previously-broken holdings analysis chat
modal in browser and confirm the rendered text is now Chinese (not English).

Flow:
1. Visit dashboard (zh-CN locale)
2. Click the sidebar item for the broken chat (5/7 13:33 holdings analysis)
3. Wait for ChatMessagesModal to open
4. Scrape the modal text; assert Chinese markers present, English markers absent
"""

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
            page.goto(URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

            # Find the sidebar item for the broken chat. Title format:
            # "持仓分析 · CRWV, AAPL, NVDA +1 · HH:MM"  (latest 13:33 row)
            # The h3 elements rendered via Translated. Click the parent button.
            print("Searching for the broken-chat sidebar entry...")
            target = page.locator("h3", has_text="持仓分析").nth(0)
            print(f"Target h3 text: {target.text_content()!r}")
            # Click the surrounding clickable parent (role=button)
            target.locator("xpath=ancestor::*[@role='button'][1]").click(timeout=8000)
            page.wait_for_timeout(25000)  # long markdown ~12s, give buffer

            # Scrape page text now
            page_text = page.evaluate("() => document.body.innerText")

            # Markers from the previously-broken English content
            english_markers = [
                "Portfolio Trading Decisions",
                "Symbols Analyzed:",
                "Portfolio Assessment",
                "Portfolio is heavily concentrated",
            ]
            chinese_markers = [
                "投资组合交易决策",
                "投资组合评估",
                "投资组合高度集中",
                "AI/半导体板块",
            ]
            en_hits = [m for m in english_markers if m in page_text]
            zh_hits = [m for m in chinese_markers if m in page_text]
            print(f"\nEnglish markers in modal page: {en_hits}")
            print(f"Chinese markers in modal page: {zh_hits}")
            page.screenshot(path=str(SCREEN_DIR / "modal_after_fix.png"), full_page=True)
            print(f"Screenshot: {SCREEN_DIR / 'modal_after_fix.png'}")

            if zh_hits and not en_hits:
                print("\nVERDICT: PASS — modal renders Chinese, no English leakage.")
            elif zh_hits and en_hits:
                print(f"\nVERDICT: PARTIAL — both languages present (en={en_hits}, zh={zh_hits})")
            else:
                print(f"\nVERDICT: FAIL — Chinese not found")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
