"""Playwright e2e — verify SessionBadge renders correct labels for each
trading session in both holdings table and watchlist rows.

Strategy: intercept `/api/portfolio/holdings` and `/api/watchlist` with
page.route to inject deterministic fixtures covering all four sessions:
  - pre     -> 盘前  (badge visible)
  - regular -> no badge
  - post    -> 盘后  (badge visible)
  - closed  -> 已收盘 (badge visible)

Runs against the dev server at http://localhost:3001 (frontend talks to
backend through /api/* on the same origin via nginx in compose, but tests
mock at the route level so backend is not contacted).

Headless. Screenshots in e2e_screens/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import Route, sync_playwright

SCREEN_DIR = Path(__file__).parent / "e2e_screens"
SCREEN_DIR.mkdir(exist_ok=True)
FRONTEND_URL = "http://localhost:3001"

HOLDINGS_FIXTURE = [
    {
        "holding_id": "h-pre",
        "symbol": "PRE",
        "quantity": 10,
        "avg_price": 100.0,
        "current_price": 105.0,
        "cost_basis": 1000.0,
        "market_value": 1050.0,
        "unrealized_pl": 50.0,
        "unrealized_pl_pct": 5.0,
        "created_at": "2026-05-01T00:00:00Z",
        "updated_at": "2026-05-07T08:00:00Z",
        "last_price_update": "2026-05-07T08:00:00Z",
        "last_session": "pre",
        "day_change_percent": 1.23,
    },
    {
        "holding_id": "h-reg",
        "symbol": "REG",
        "quantity": 5,
        "avg_price": 200.0,
        "current_price": 210.0,
        "cost_basis": 1000.0,
        "market_value": 1050.0,
        "unrealized_pl": 50.0,
        "unrealized_pl_pct": 5.0,
        "created_at": "2026-05-01T00:00:00Z",
        "updated_at": "2026-05-07T15:00:00Z",
        "last_price_update": "2026-05-07T15:00:00Z",
        "last_session": "regular",
        "day_change_percent": 0.5,
    },
    {
        "holding_id": "h-post",
        "symbol": "POST",
        "quantity": 1,
        "avg_price": 50.0,
        "current_price": 55.0,
        "cost_basis": 50.0,
        "market_value": 55.0,
        "unrealized_pl": 5.0,
        "unrealized_pl_pct": 10.0,
        "created_at": "2026-05-01T00:00:00Z",
        "updated_at": "2026-05-07T22:00:00Z",
        "last_price_update": "2026-05-07T22:00:00Z",
        "last_session": "post",
        "day_change_percent": 2.5,
    },
    {
        "holding_id": "h-closed",
        "symbol": "CLSD",
        "quantity": 2,
        "avg_price": 75.0,
        "current_price": 70.0,
        "cost_basis": 150.0,
        "market_value": 140.0,
        "unrealized_pl": -10.0,
        "unrealized_pl_pct": -6.67,
        "created_at": "2026-05-01T00:00:00Z",
        "updated_at": "2026-05-04T20:00:00Z",
        "last_price_update": "2026-05-04T20:00:00Z",
        "last_session": "closed",
        "day_change_percent": -1.1,
    },
]

WATCHLIST_FIXTURE = [
    {
        "watchlist_id": "w-pre",
        "symbol": "PREW",
        "added_at": "2026-05-01T00:00:00Z",
        "last_analyzed_at": "2026-05-07T08:00:00Z",
        "notes": None,
        "current_price": 11.11,
        "last_price_update": "2026-05-07T08:00:00Z",
        "last_session": "pre",
        "day_change_percent": 1.0,
    },
    {
        "watchlist_id": "w-reg",
        "symbol": "REGW",
        "added_at": "2026-05-01T00:00:00Z",
        "last_analyzed_at": "2026-05-07T15:00:00Z",
        "notes": None,
        "current_price": 22.22,
        "last_price_update": "2026-05-07T15:00:00Z",
        "last_session": "regular",
        "day_change_percent": 0.2,
    },
    {
        "watchlist_id": "w-post",
        "symbol": "POSTW",
        "added_at": "2026-05-01T00:00:00Z",
        "last_analyzed_at": "2026-05-07T22:00:00Z",
        "notes": None,
        "current_price": 33.33,
        "last_price_update": "2026-05-07T22:00:00Z",
        "last_session": "post",
        "day_change_percent": -0.5,
    },
    {
        "watchlist_id": "w-closed",
        "symbol": "CLSDW",
        "added_at": "2026-05-01T00:00:00Z",
        "last_analyzed_at": "2026-05-04T20:00:00Z",
        "notes": None,
        "current_price": 44.44,
        "last_price_update": "2026-05-04T20:00:00Z",
        "last_session": "closed",
        "day_change_percent": -2.0,
    },
]

SUMMARY_FIXTURE = {
    "holdings_count": len(HOLDINGS_FIXTURE),
    "total_cost_basis": 2200.0,
    "total_market_value": 2295.0,
    "total_unrealized_pl": 95.0,
    "total_unrealized_pl_pct": 4.32,
}


def _json_route(payload: object):
    def handler(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload),
        )

    return handler


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

        # Mock both relative (/api/...) and absolute (http://localhost:8001)
        # variants so the test is robust to whichever the dev build hits.
        for pattern in (
            "**/api/portfolio/holdings",
            "**/api/portfolio/holdings/refresh-prices",
        ):
            page.route(pattern, _json_route(HOLDINGS_FIXTURE))
        page.route(
            "**/api/portfolio/summary", _json_route(SUMMARY_FIXTURE)
        )
        page.route("**/api/watchlist", _json_route(WATCHLIST_FIXTURE))

        page.goto(FRONTEND_URL, wait_until="networkidle", timeout=30000)
        page.evaluate("localStorage.setItem('i18nextLng', 'zh-CN')")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(5000)
        page.screenshot(
            path=SCREEN_DIR / "session_badge_dashboard.png", full_page=True
        )

        # ---------- 1. badges by data-testid + data-session ----------
        # SessionBadge renders <span data-testid="session-badge"
        # data-session="pre|post|closed">. regular/null render nothing.
        for sess in ("pre", "post", "closed"):
            count = page.locator(
                f'[data-testid="session-badge"][data-session="{sess}"]'
            ).count()
            if count == 0:
                failures.append(
                    f"no SessionBadge with data-session={sess} in DOM"
                )
            else:
                print(f"[badge] data-session={sess}: {count} element(s)")

        # regular session must NOT render a badge
        regular_count = page.locator(
            '[data-testid="session-badge"][data-session="regular"]'
        ).count()
        if regular_count != 0:
            failures.append(
                f"SessionBadge wrongly rendered for regular session "
                f"({regular_count} elements)"
            )
        else:
            print("[badge] data-session=regular: 0 element(s) (expected)")

        # ---------- 2. localized text per session (zh-CN) ----------
        # Holdings row text: each row should contain the right zh-CN label.
        page_html = page.content()
        for sess, label in (
            ("pre", "盘前"),
            ("post", "盘后"),
            ("closed", "已收盘"),
        ):
            if label not in page_html:
                failures.append(
                    f"label '{label}' for session={sess} not found on page"
                )
            else:
                print(f"[label] {sess} -> '{label}' present")

        # ---------- 3. watchlist row REGW (regular) shows no badge ----------
        # Locate the watchlist row by symbol and assert no session-badge inside
        regw_row = page.locator(
            "div:has(> div > span:text-is('REGW'))"
        ).first
        if regw_row.count() > 0:
            inner_badges = regw_row.locator(
                '[data-testid="session-badge"]'
            ).count()
            if inner_badges != 0:
                failures.append(
                    f"REGW (regular) watchlist row has "
                    f"{inner_badges} badge(s); expected 0"
                )
            else:
                print("[watchlist] REGW row has no badge (expected)")
        else:
            failures.append("watchlist row for REGW not found")

        # ---------- 4. holdings row REG (regular) shows no badge ----------
        reg_row = page.locator("tr:has(td:text-is('REG'))").first
        if reg_row.count() > 0:
            inner_badges = reg_row.locator(
                '[data-testid="session-badge"]'
            ).count()
            if inner_badges != 0:
                failures.append(
                    f"REG (regular) holdings row has "
                    f"{inner_badges} badge(s); expected 0"
                )
            else:
                print("[holdings] REG row has no badge (expected)")
        else:
            failures.append("holdings row for REG not found")

        page.screenshot(
            path=SCREEN_DIR / "session_badge_final.png", full_page=True
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
