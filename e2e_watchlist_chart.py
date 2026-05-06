"""Playwright e2e — verify the recent additions:
  1. Portfolio chart renders with > 0 data points (canvas height non-zero)
  2. Watchlist rows display current price ($XXX.XX) next to symbol
  3. Watchlist rows have a per-row "Analyze Now" button
  4. "Last analyzed" relative time uses real values (not 1970-01-01 epoch bug)

Headless against the running dev stack. Screenshots in e2e_screens/.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SCREEN_DIR = Path(__file__).parent / "e2e_screens"
SCREEN_DIR.mkdir(exist_ok=True)
FRONTEND_URL = "http://localhost:3001"


def main() -> int:
    failures: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1600, "height": 900})
        page = ctx.new_page()

        page.on("pageerror", lambda exc: print(f"[browser-pageerror] {exc}"))
        page.on(
            "console",
            lambda m: (
                print(f"[browser-console:{m.type}] {m.text}")
                if m.type == "error"
                else None
            ),
        )

        page.goto(FRONTEND_URL, wait_until="networkidle", timeout=30000)
        page.evaluate("localStorage.setItem('i18nextLng', 'zh-CN')")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(8000)
        page.screenshot(
            path=SCREEN_DIR / "wl_chart_01_dashboard.png", full_page=True
        )

        # ---------- 1. portfolio chart has data points ----------
        # PortfolioChart uses lightweight-charts which renders into a <canvas>.
        chart_canvas = page.locator("canvas").first
        if chart_canvas.count() == 0:
            failures.append("no <canvas> on page")
        else:
            box = chart_canvas.bounding_box()
            if not box or box["width"] < 100 or box["height"] < 50:
                failures.append(
                    f"canvas too small to be a real chart: {box}"
                )
            else:
                print(
                    f"[chart] canvas={box['width']:.0f}x{box['height']:.0f}"
                )
                # Read N pixels from the middle and confirm not all-white
                # (i.e. the line was actually drawn).
                pixel_check = page.evaluate(
                    """() => {
                      const c = document.querySelector('canvas');
                      if (!c) return null;
                      const ctx = c.getContext('2d');
                      const w = c.width, h = c.height;
                      // Sample a horizontal strip in the middle
                      const data = ctx.getImageData(
                        Math.floor(w*0.1), Math.floor(h*0.3),
                        Math.floor(w*0.8), Math.floor(h*0.4)
                      ).data;
                      let nonBg = 0;
                      for (let i = 0; i < data.length; i += 4) {
                        const r=data[i], g=data[i+1], b=data[i+2], a=data[i+3];
                        if (a > 0 && (r < 240 || g < 240 || b < 240)) nonBg++;
                      }
                      return { nonBg, total: data.length / 4 };
                    }"""
                )
                if not pixel_check or pixel_check.get("nonBg", 0) < 50:
                    failures.append(
                        f"chart canvas appears blank: {pixel_check}"
                    )
                else:
                    print(
                        f"[chart] non-bg pixels = {pixel_check['nonBg']}/"
                        f"{pixel_check['total']}  PASS"
                    )

        # ---------- 2. watchlist rows show current price ----------
        # Watchlist panel header is "watchlist.title" — rendered as 关注列表
        # in zh-CN. Search for any element containing $\d+\.\d{2} that's
        # also near a ticker symbol.
        body_text = page.locator("body").text_content() or ""
        # Strip non-BMP for windows console safety
        safe = "".join(c if ord(c) < 0x10000 else "?" for c in body_text)
        # Find watchlist tickers we know exist
        wl_response = page.evaluate(
            "fetch('http://localhost:8001/api/watchlist').then(r=>r.json())"
        )
        wl_symbols = (
            [w["symbol"] for w in wl_response] if wl_response else []
        )
        print(f"[watchlist] backend rows = {len(wl_symbols)}: {wl_symbols}")

        # For each symbol, check the rendered DOM nearby has a $price
        priced_symbols: list[str] = []
        for sym in wl_symbols:
            # Find the row containing the symbol text
            row_loc = page.locator(
                f"div:has(span:text-is('{sym}'))"
            ).first
            if row_loc.count() == 0:
                continue
            row_text = row_loc.text_content() or ""
            if re.search(r"\$\d+\.\d{2}", row_text):
                priced_symbols.append(sym)

        print(
            f"[watchlist] symbols with $price rendered: "
            f"{len(priced_symbols)}/{len(wl_symbols)}: {priced_symbols}"
        )
        if wl_symbols and len(priced_symbols) < max(1, len(wl_symbols) // 2):
            failures.append(
                f"too few watchlist rows have prices: "
                f"{len(priced_symbols)}/{len(wl_symbols)}"
            )

        # ---------- 3. per-row "Analyze Now" button exists ----------
        # zh-CN button label per i18n: 立即分析 / 分析中 / portfolio:watchlistPanel.analyzeNow
        # The component renders the button text from t(), in zh-CN it's "立即分析"
        analyze_btns = page.locator(
            "button:text-matches('立即分析|Analyze')"
        )
        n_analyze = analyze_btns.count()
        # 1 batch button up top + 1 per row → expect >= len(wl)+1
        expected_min = len(wl_symbols) + 1 if wl_symbols else 1
        print(
            f"[watchlist] analyze buttons = {n_analyze} "
            f"(expected >= {expected_min})"
        )
        if n_analyze < expected_min:
            failures.append(
                f"per-row analyze buttons missing: got {n_analyze}, "
                f"expected >= {expected_min}"
            )

        # ---------- 4. last_analyzed timestamps not the 1970 bug ----------
        # If the UTC-suffix fix worked, the row text should NOT contain
        # things like "55y ago" / "1970"
        head = safe[:2000]
        if "1970" in head or re.search(r"\b\d{2,4}y ago", head):
            failures.append(
                "watchlist last_analyzed shows pre-fix epoch values "
                "(1970 / 50+y ago)"
            )
        else:
            print("[watchlist] last_analyzed timestamps look sane")

        page.screenshot(
            path=SCREEN_DIR / "wl_chart_02_final.png", full_page=True
        )

        # ---------- summary ----------
        if failures:
            print("\n[FAIL]")
            for f in failures:
                print(f"  - {f}")
        else:
            print("\n[ALL PASS]")

        ctx.close()
        browser.close()
        return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
