"""Playwright e2e — verify Refresh Prices captures pre-market session.

Drives the real backend (no route mocks). Run during US pre-market window
(04:00-09:30 ET) so yfinance returns prepost bars whose timestamp falls in
the pre session. Steps:

  1. baseline: GET /api/portfolio/holdings, capture each symbol's last_session
  2. open dashboard, click [Refresh Prices], wait for the call to complete
  3. assert that at least one holding's last_session flipped to "pre" in the
     reloaded API response (proof the fix at holdings.py:323 persists session)
  4. assert that a SessionBadge with data-session="pre" renders for at least
     one row in the holdings table (proof the UI reflects the persisted value)

Screenshots in e2e_screens/.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

SCREEN_DIR = Path(__file__).parent / "e2e_screens"
SCREEN_DIR.mkdir(exist_ok=True)
FRONTEND_URL = "http://localhost:3001"
BACKEND_URL = "http://localhost:8001"


def _get_holdings() -> list[dict]:
    with urllib.request.urlopen(f"{BACKEND_URL}/api/portfolio/holdings", timeout=15) as r:
        return json.loads(r.read().decode())


def main() -> int:
    failures: list[str] = []

    # Sanity: are we actually in US pre-market?
    et_now = datetime.now(ZoneInfo("America/New_York"))
    et_minutes = et_now.hour * 60 + et_now.minute
    in_pre = 4 * 60 <= et_minutes < 9 * 60 + 30
    print(f"[time] ET now: {et_now:%Y-%m-%d %H:%M %Z} -- in_pre_market={in_pre}")
    if not in_pre:
        print("[warn] not in pre-market window; test will likely fail naturally")

    # 1. baseline
    before = _get_holdings()
    print(f"[baseline] {len(before)} holdings")
    for h in before:
        print(f"  {h.get('symbol'):<6} price={h.get('current_price')} last_session={h.get('last_session')}")
    if not before:
        print("[FAIL] no holdings to test against — add at least one US stock first")
        return 2

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

        # Set zh-CN so the badge text is "盘前" (matches existing test pattern)
        page.goto(FRONTEND_URL, wait_until="networkidle", timeout=30000)
        page.evaluate("localStorage.setItem('i18nextLng', 'zh-CN')")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(3000)
        page.screenshot(path=SCREEN_DIR / "refresh_premarket_01_loaded.png", full_page=True)

        # 2. click Refresh Prices and wait for the POST to complete
        btn = page.locator('button:has-text("Refresh Prices")').first
        if btn.count() == 0:
            print("[FAIL] Refresh Prices button not found")
            ctx.close(); browser.close()
            return 3

        with page.expect_response(
            lambda r: "/api/portfolio/holdings/refresh-prices" in r.url and r.request.method == "POST",
            timeout=60000,
        ) as resp_info:
            btn.click()
        resp = resp_info.value
        print(f"[refresh] POST status={resp.status}")
        if resp.status != 200:
            failures.append(f"refresh-prices returned {resp.status}")

        # Frontend re-fetches holdings via react-query invalidation; give it a moment
        page.wait_for_timeout(4000)
        page.screenshot(path=SCREEN_DIR / "refresh_premarket_02_after_click.png", full_page=True)

        # 3. backend assertion — at least one holding now has last_session=="pre"
        after = _get_holdings()
        print("[after-refresh]")
        flipped = []
        for h in after:
            sym = h.get("symbol")
            sess = h.get("last_session")
            print(f"  {sym:<6} price={h.get('current_price')} last_session={sess}")
            if sess == "pre":
                flipped.append(sym)
        if flipped:
            print(f"[PASS] {len(flipped)} holding(s) now have last_session=='pre': {flipped}")
        else:
            failures.append(
                "no holding has last_session=='pre' after Refresh — "
                "the holdings.py:323 fix may not be working, OR yfinance "
                "returned regular-session bars only"
            )

        # 4. UI assertion — at least one rendered SessionBadge with data-session="pre"
        pre_badges = page.locator('[data-testid="session-badge"][data-session="pre"]').count()
        print(f"[ui] SessionBadge[data-session='pre'] count={pre_badges}")
        if pre_badges == 0:
            failures.append("no '盘前' SessionBadge rendered in the UI after Refresh")

        # 5. text assertion — '盘前' literal present somewhere on the page
        if "盘前" not in page.content():
            failures.append("'盘前' text not present anywhere on the rendered page")
        else:
            print("[ui] '盘前' text found on page")

        page.screenshot(path=SCREEN_DIR / "refresh_premarket_03_final.png", full_page=True)
        ctx.close(); browser.close()

    if failures:
        print("\n[FAIL]")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\n[ALL PASS]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
