"""Playwright e2e — verify the chart was removed and core surfaces still work.

After v0.26.0:
  1. No <canvas> on the dashboard (chart gone)
  2. No 1D/1M/1Y/All period buttons
  3. Portfolio value header still shows ($XX,XXX.XX format)
  4. Portfolio Holdings table is still rendered
  5. Watchlist panel is still rendered
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
            lambda m: print(f"[browser-console:{m.type}] {m.text}")
            if m.type == "error"
            else None,
        )

        page.goto(FRONTEND_URL, wait_until="networkidle", timeout=30000)
        page.evaluate("localStorage.setItem('i18nextLng', 'zh-CN')")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(6000)
        page.screenshot(
            path=SCREEN_DIR / "chart_removed_dashboard.png", full_page=True
        )

        # ---------- 1. no canvas (chart gone) ----------
        n_canvas = page.locator("canvas").count()
        print(f"[chart-gone] canvas count = {n_canvas}")
        if n_canvas != 0:
            failures.append(f"expected 0 canvas, got {n_canvas}")

        # ---------- 2. no period buttons ----------
        # Note: skip "All" — DecisionTracker has its own "All" filter button.
        for label in ("1D", "1M", "1Y"):
            btn = page.locator(f"button:text-is('{label}')").count()
            if btn > 0:
                failures.append(
                    f"period button '{label}' should be gone, found {btn}"
                )
        print("[chart-gone] period buttons check done")

        # ---------- 3. portfolio value header survives ----------
        body = page.locator("body").text_content() or ""
        # Header has $XX[,XXX].XX format somewhere near the top
        head = body[:1500]
        if not re.search(r"\$\d", head):
            failures.append("no $-prefixed portfolio value visible at top")
        else:
            m = re.search(r"\$[\d,]+\.\d{2}", head)
            print(f"[header] portfolio value visible: {m.group(0) if m else '?'}")

        # ---------- 4. holdings table still rendered ----------
        # Look for "Portfolio Holdings" title or any of the table column headers
        holdings_present = (
            page.locator("text=Portfolio Holdings").count() > 0
            or page.locator("text=Symbol").count() > 0
        )
        if not holdings_present:
            failures.append("Portfolio Holdings table missing")
        else:
            print("[holdings] table present")

        # ---------- 5. watchlist still rendered ----------
        # Backend rows
        wl = page.evaluate(
            "fetch('http://localhost:8001/api/watchlist').then(r=>r.json())"
        )
        wl_count = len(wl) if wl else 0
        print(f"[watchlist] backend rows = {wl_count}")
        if wl_count > 0:
            # confirm at least one symbol from backend appears in DOM
            sym = wl[0]["symbol"]
            if page.get_by_text(sym, exact=True).count() == 0:
                failures.append(f"watchlist row for {sym} not rendered")
            else:
                print(f"[watchlist] row {sym} rendered")

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
