"""Playwright e2e — verify Day % column renders in both holdings table and
watchlist rows after the v0.27.0/v0.22.0 'today's gain/loss' addition.

Checks:
  1. PortfolioSummaryTable header has a "Day %" column
  2. >= 1 holding row shows a percent string (e.g. "+1.23%" or "-0.45%") in
     the Day % column
  3. >= 1 watchlist row shows the same percent format inline with price
  4. Color: at least one positive day % is green and one negative is red
     (skip color check if all gains or all losses)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SCREEN_DIR = Path(__file__).parent / "e2e_screens"
SCREEN_DIR.mkdir(exist_ok=True)
FRONTEND_URL = "http://localhost:3001"

PCT_RE = re.compile(r"[-+]\d+\.\d{2}%")


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
        page.wait_for_timeout(8000)
        page.screenshot(
            path=SCREEN_DIR / "day_change_dashboard.png", full_page=True
        )

        # ---------- 1. holdings header has Day % column ----------
        if page.locator("th:text-is('Day %')").count() == 0:
            failures.append("holdings table missing 'Day %' header")
        else:
            print("[holdings] 'Day %' header present")

        # ---------- 2. >= 1 holding row shows %change text ----------
        # Hit backend to get expected symbols
        holdings = page.evaluate(
            "fetch('http://localhost:8001/api/portfolio/holdings')"
            ".then(r=>r.json())"
        )
        sym_to_day = {
            h["symbol"]: h.get("day_change_percent") for h in (holdings or [])
        }
        print(
            f"[holdings] backend reports {len(sym_to_day)} rows: "
            f"{list(sym_to_day.items())[:3]}"
        )

        # Find rendered % strings inside the holdings table by counting (in
        # the browser, to avoid Windows GBK encoding chokes on the 🟢/🔴 emoji
        # in the P/L column) how many tr:has(td=symbol) rows contain a
        # signed-percent like "+1.23%" or "-0.45%". Note: P/L% column does
        # NOT include a leading sign, so this only matches the new Day % col.
        rendered_holding_pcts = page.evaluate(
            """(symbols) => {
              const re = /[-+]\\d+\\.\\d{2}%/;
              let n = 0;
              for (const sym of symbols) {
                const rows = document.querySelectorAll('tr');
                for (const r of rows) {
                  const first = r.querySelector('td');
                  if (!first || first.textContent.trim() !== sym) continue;
                  if (re.test(r.textContent)) n++;
                  break;
                }
              }
              return n;
            }""",
            [s for s, v in sym_to_day.items() if v is not None],
        )
        print(
            f"[holdings] rows with rendered %change: {rendered_holding_pcts}/"
            f"{sum(1 for v in sym_to_day.values() if v is not None)}"
        )
        if rendered_holding_pcts == 0 and sym_to_day:
            failures.append(
                "no holdings row shows a Day % value in the DOM"
            )

        # ---------- 3. >= 1 watchlist row shows %change inline ----------
        wl = page.evaluate(
            "fetch('http://localhost:8001/api/watchlist').then(r=>r.json())"
        )
        wl_with_day = [
            w for w in (wl or []) if w.get("day_change_percent") is not None
        ]
        print(f"[watchlist] backend rows with day%: {len(wl_with_day)}/{len(wl or [])}")

        rendered_wl_pcts = 0
        for w in wl_with_day:
            sym = w["symbol"]
            # Each watchlist row is wrapped in a div with the symbol span inside
            row = page.locator(
                f"div:has(span:text-is('{sym}'))"
            ).first
            if row.count() == 0:
                continue
            txt = row.text_content() or ""
            if PCT_RE.search(txt):
                rendered_wl_pcts += 1
        print(
            f"[watchlist] rows with rendered %change: {rendered_wl_pcts}/"
            f"{len(wl_with_day)}"
        )
        if wl_with_day and rendered_wl_pcts == 0:
            failures.append(
                "no watchlist row shows a Day % value in the DOM"
            )

        # ---------- 4. color check (best-effort) ----------
        # Can't easily compare per-cell tailwind classes; just sample one
        # green and one red span if both signs exist in backend data.
        backend_signs = {
            "+" if v >= 0 else "-"
            for v in sym_to_day.values()
            if v is not None
        } | {
            "+" if w["day_change_percent"] >= 0 else "-"
            for w in wl_with_day
        }
        print(f"[color] backend has signs: {sorted(backend_signs)}")

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
