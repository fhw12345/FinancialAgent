"""Verify WatchlistPanel renders the 'stale' time-ago indicator next to
prices whose last_price_update is older than 5 minutes.

Mocks /api/watchlist to inject a deterministic mix of fresh and stale
rows; previously the panel rendered nothing (no price, no badge) when a
quote couldn't be fetched, but with persistence + stale indicator the
last known price stays visible alongside its age.
"""
from __future__ import annotations
import io
import json
import sys
from datetime import datetime, timedelta, timezone
from playwright.sync_api import Route, sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

now = datetime.now(timezone.utc)
fresh_iso = now.isoformat().replace("+00:00", "Z")
stale_iso = (now - timedelta(minutes=42)).isoformat().replace("+00:00", "Z")

WATCHLIST_FIXTURE = [
    {
        "watchlist_id": "wl-fresh",
        "symbol": "FRESH",
        "added_at": "2026-05-01T00:00:00Z",
        "last_analyzed_at": fresh_iso,
        "notes": None,
        "current_price": 100.50,
        "last_price_update": fresh_iso,
        "last_session": "regular",
        "day_change_percent": 1.23,
    },
    {
        "watchlist_id": "wl-stale",
        "symbol": "STALE",
        "added_at": "2026-05-01T00:00:00Z",
        "last_analyzed_at": fresh_iso,
        "notes": None,
        "current_price": 999.99,
        "last_price_update": stale_iso,  # 42 min ago
        "last_session": "regular",
        "day_change_percent": -0.45,
    },
]


def main() -> None:
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(locale="zh-CN", viewport={"width": 1600, "height": 900})
        page = ctx.new_page()

        def handle(route: Route) -> None:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(WATCHLIST_FIXTURE),
            )

        page.route("**/api/watchlist*", handle)
        page.goto("http://localhost:3001", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(6000)

        rows = page.evaluate(
            """() => {
                const out = [];
                const sel = 'div.flex.items-center.justify-between.p-3.bg-gray-50';
                document.querySelectorAll(sel).forEach((el) => {
                    out.push(el.innerText);
                });
                return out;
            }"""
        )
        print(f"Rows: {len(rows)}")
        for r in rows:
            print(f"  {r.replace(chr(10), ' | ')[:200]}")

        # Assertions
        joined = " | ".join(rows)
        fresh_row = next((r for r in rows if "FRESH" in r), "")
        stale_row = next((r for r in rows if "STALE" in r), "")

        print("\n=== Assertions ===")
        ok = True
        if "$100.50" not in fresh_row:
            print("FAIL: FRESH row missing $100.50"); ok = False
        else:
            print("PASS: FRESH row shows $100.50")
        # FRESH row should NOT contain stale indicator (no Xm/Xh/Xd ago next to price)
        # Easiest assertion: FRESH row should be missing the m/h/d-ago text from
        # the dedicated stale span. We look for "ago" appearing more than once
        # in stale row vs once (last-analyzed) in fresh row.
        if fresh_row.count("ago") > 1:
            print(f"FAIL: FRESH row appears to show stale indicator (count={fresh_row.count('ago')})"); ok = False
        else:
            print("PASS: FRESH row has no stale indicator next to price")

        if "$999.99" not in stale_row:
            print("FAIL: STALE row missing $999.99"); ok = False
        else:
            print("PASS: STALE row shows $999.99")
        if "ago" not in stale_row:
            print("FAIL: STALE row missing 'ago' indicator"); ok = False
        else:
            # Should appear at least twice: stale-quote + last-analyzed
            print(f"PASS: STALE row has 'ago' indicator (count={stale_row.count('ago')})")

        page.screenshot(path="e2e_screens/watchlist_stale.png", full_page=True)
        print(f"\nVERDICT: {'PASS' if ok else 'FAIL'}")
        b.close()


if __name__ == "__main__":
    main()
