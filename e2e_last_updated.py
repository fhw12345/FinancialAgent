"""Playwright e2e — verify the new "Last updated" header on PortfolioSummaryTable.

Loads the portfolio dashboard, screenshots the holdings table, and asserts
the "Last updated:" string is visible above the table.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SCREEN_DIR = Path(__file__).parent / "e2e_screens"
SCREEN_DIR.mkdir(exist_ok=True)
FRONTEND_URL = "http://localhost:3001"


def main() -> int:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1600, "height": 900})
        page = ctx.new_page()

        page.on("pageerror", lambda exc: print(f"[browser-pageerror] {exc}"))
        page.on(
            "console",
            lambda msg: (
                print(f"[browser-console:{msg.type}] {msg.text}")
                if msg.type == "error"
                else None
            ),
        )

        page.goto(FRONTEND_URL, wait_until="networkidle", timeout=30000)
        # Force zh-CN locale so the time formatter renders Beijing time.
        page.evaluate("localStorage.setItem('i18nextLng', 'zh-CN')")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(8000)
        page.screenshot(
            path=SCREEN_DIR / "last_updated_01_dashboard.png", full_page=True
        )
        body_text = (page.locator("body").text_content() or "")[:500]
        # Windows GBK terminal can't render emoji — strip non-BMP for logging
        safe = "".join(c if ord(c) < 0x10000 else "?" for c in body_text)
        print(f"[debug] body text head: {safe!r}")

        # Check "Last updated:" text on the page (only renders when at least one
        # holding has a non-null last_price_update).
        # Probe what locale is actually resolved at render time
        resolved_lang = page.evaluate(
            "() => (window.i18next && window.i18next.language) "
            "|| localStorage.getItem('i18nextLng') || 'unknown'"
        )
        ls_lang = page.evaluate("localStorage.getItem('i18nextLng')")
        print(f"[debug] i18n.language={resolved_lang!r} localStorage.i18nextLng={ls_lang!r}")
        # Sanity: format a known UTC instant via the browser's Intl in zh-CN/Asia/Shanghai
        sample = page.evaluate(
            "new Date('2026-05-06T03:17:57Z').toLocaleTimeString('zh-CN', "
            "{hour:'2-digit', minute:'2-digit', timeZone:'Asia/Shanghai'})"
        )
        print(f"[debug] zh-CN+Shanghai sample for 03:17:57Z → {sample!r} (expect 11:17)")
        # Sanity 2: same call WITHOUT timezone option (browser default = UTC in playwright)
        sample_no_tz = page.evaluate(
            "new Date('2026-05-06T03:17:57Z').toLocaleTimeString('zh-CN', "
            "{hour:'2-digit', minute:'2-digit'})"
        )
        print(f"[debug] zh-CN no-TZ sample → {sample_no_tz!r} (= browser local TZ)")

        last_updated = page.locator("text=Last updated:").first
        visible = last_updated.is_visible()
        print(f"[verify] 'Last updated:' visible → {'PASS' if visible else 'FAIL'}")
        if visible:
            box = last_updated.bounding_box()
            if box:
                page.screenshot(
                    path=SCREEN_DIR / "last_updated_02_header.png",
                    clip={
                        "x": max(0, box["x"] - 20),
                        "y": max(0, box["y"] - 40),
                        "width": min(900, box["width"] + 800),
                        "height": min(120, box["height"] + 80),
                    },
                )
            text = last_updated.text_content() or ""
            print(f"  rendered text: {text!r}")

        ctx.close()
        browser.close()
        return 0 if visible else 1


if __name__ == "__main__":
    sys.exit(main())
