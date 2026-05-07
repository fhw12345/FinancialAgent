"""W1-E1 e2e: OrderPreview / DecisionTracker intent badge rendering.

Verifies that DecisionTracker rows render the IntentBadge next to
SideBadge so a SELL is visibly disambiguated:
  - close_long  -> "平多" gray badge
  - open_short  -> "做空" red badge
And that legacy_short_geometry docs (the CRWV-style migrated rows) show
a "⚠ 几何" warning chip.

Strategy: page.route intercepts /api/portfolio/decisions and returns a
deterministic 3-row fixture covering the cases. Headless. Screenshot in
e2e_screens/.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from playwright.sync_api import Route, sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SCREEN_DIR = Path(__file__).parent / "e2e_screens"
SCREEN_DIR.mkdir(exist_ok=True)
URL = "http://localhost:3001"

NOW = "2026-05-08T03:00:00Z"

DECISIONS_FIXTURE = {
    "decisions": [
        {
            "order_id": "test-close-long",
            "symbol": "TSTL",
            "side": "sell",
            "intent": "close_long",
            "decision_type": "order",
            "decision_price": 110.0,
            "quantity": 0.0,
            "status": "suggested",
            "filled_qty": 0,
            "filled_avg_price": None,
            "filled_at": None,
            "user_transaction_id": None,
            "created_at": NOW,
            "analysis_id": "test-cl",
            "chat_id": "test-chat",
            "recommendation_source": "holdings",
            "pnl_snapshots": {},
            "metadata": {
                "confidence": 7,
                "entry_price": 110.0,
                "stop_loss": 95.0,
                "take_profit": 120.0,
                "reasoning": "test close_long",
            },
        },
        {
            "order_id": "test-open-short",
            "symbol": "TSTS",
            "side": "sell",
            "intent": "open_short",
            "decision_type": "order",
            "decision_price": 100.0,
            "quantity": 0.0,
            "status": "suggested",
            "filled_qty": 0,
            "filled_avg_price": None,
            "filled_at": None,
            "user_transaction_id": None,
            "created_at": NOW,
            "analysis_id": "test-os",
            "chat_id": "test-chat",
            "recommendation_source": "picks",
            "pnl_snapshots": {},
            "metadata": {
                "confidence": 6,
                "entry_price": 100.0,
                "stop_loss": 110.0,
                "take_profit": 85.0,
                "reasoning": "test open_short",
            },
        },
        {
            "order_id": "test-legacy",
            "symbol": "TSTLG",
            "side": "sell",
            "intent": "close_long",
            "decision_type": "order",
            "decision_price": 138.0,
            "quantity": 0.0,
            "status": "suggested",
            "filled_qty": 0,
            "filled_avg_price": None,
            "filled_at": None,
            "user_transaction_id": None,
            "created_at": NOW,
            "analysis_id": "test-legacy",
            "chat_id": "test-chat",
            "recommendation_source": "holdings",
            "pnl_snapshots": {},
            "metadata": {
                "confidence": 7,
                "entry_price": 138.0,
                "stop_loss": 142.0,
                "take_profit": 122.0,
                "reasoning": "CRWV-style legacy short geometry",
                "legacy_short_geometry": True,
            },
        },
    ],
    "count": 3,
}


def main() -> None:
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            ctx = b.new_context(locale="zh-CN", viewport={"width": 1600, "height": 900})
            page = ctx.new_page()

            def handle_decisions(route: Route) -> None:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(DECISIONS_FIXTURE),
                )

            page.route("**/api/portfolio/decisions*", handle_decisions)

            page.goto(URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(6000)

            badges = page.locator("[data-testid=intent-badge]").evaluate_all(
                """els => els.map(e => ({
                    intent: e.getAttribute('data-intent'),
                    text: e.textContent.trim(),
                }))"""
            )
            print(f"intent badges rendered: {len(badges)}")
            for b_ in badges:
                print(f"  intent={b_['intent']} text={b_['text']!r}")

            legacy = page.locator(
                "[data-testid=legacy-geometry-warning]"
            ).count()
            print(f"\nlegacy-geometry warning chips: {legacy}")

            ok = True
            seen = {b_["intent"]: b_["text"] for b_ in badges}

            if seen.get("close_long") != "平多":
                print("FAIL: close_long badge missing or wrong text")
                ok = False
            else:
                print("PASS: close_long renders 平多")

            if seen.get("open_short") != "做空":
                print("FAIL: open_short badge missing or wrong text")
                ok = False
            else:
                print("PASS: open_short renders 做空")

            if legacy < 1:
                print("FAIL: legacy_short_geometry warning chip not rendered")
                ok = False
            else:
                print(f"PASS: {legacy} legacy warning chip(s) shown")

            page.screenshot(
                path=str(SCREEN_DIR / "intent_badge.png"), full_page=True
            )
            print(f"\nScreenshot: {SCREEN_DIR / 'intent_badge.png'}")
            print(f"\nVERDICT: {'PASS' if ok else 'FAIL'}")
            sys.exit(0 if ok else 1)
        finally:
            b.close()


if __name__ == "__main__":
    main()
