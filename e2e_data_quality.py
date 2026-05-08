"""W1-E3 e2e: data_quality=degraded UI tag.

Mocks /api/portfolio/decisions to return one row whose metadata
includes data_quality.degraded_fields. Verifies the gray "📉 数据降级"
chip renders + the title attribute lists the actual degraded fields.
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
NOW = "2026-05-08T03:30:00Z"

DECISIONS_FIXTURE = {
    "decisions": [
        {
            "order_id": "test-degraded",
            "symbol": "TSTQ",
            "side": "hold",
            "intent": "hold",
            "decision_type": "signal",
            "decision_price": 100.0,
            "quantity": 0.0,
            "status": "signal",
            "filled_qty": 0,
            "filled_avg_price": None,
            "filled_at": None,
            "user_transaction_id": None,
            "created_at": NOW,
            "analysis_id": "test-dq",
            "chat_id": "test-chat",
            "recommendation_source": "holdings",
            "pnl_snapshots": {},
            "metadata": {
                "confidence": 5,
                "reasoning": "test data quality",
                "data_quality": {
                    "degraded_fields": [
                        "Cash flow unavailable for TSTQ — do not cite as evidence",
                        "Fibonacci swing is stale (range_position=above_range) — do not cite golden zone or any fib level as support/resistance",
                    ],
                    "consistency_passed": False,
                },
            },
        },
        {
            "order_id": "test-clean",
            "symbol": "TSTC",
            "side": "hold",
            "intent": "hold",
            "decision_type": "signal",
            "decision_price": 200.0,
            "quantity": 0.0,
            "status": "signal",
            "filled_qty": 0,
            "filled_avg_price": None,
            "filled_at": None,
            "user_transaction_id": None,
            "created_at": NOW,
            "analysis_id": "test-clean",
            "chat_id": "test-chat",
            "recommendation_source": "holdings",
            "pnl_snapshots": {},
            "metadata": {"confidence": 8, "reasoning": "all data fresh"},
        },
    ],
    "count": 2,
}


def main() -> None:
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            ctx = b.new_context(
                locale="zh-CN", viewport={"width": 1600, "height": 900}
            )
            page = ctx.new_page()

            def handle(route: Route) -> None:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(DECISIONS_FIXTURE),
                )

            page.route("**/api/portfolio/decisions*", handle)
            page.goto(URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(6000)

            chips = page.locator("[data-testid=data-quality-degraded]")
            count = chips.count()
            print(f"data-quality chips rendered: {count}")
            ok = True
            if count != 1:
                print("FAIL: expected exactly 1 degraded chip (one row clean)")
                ok = False
            else:
                title = chips.first.get_attribute("title") or ""
                print(f"chip title: {title[:200]}")
                if "Cash flow unavailable" not in title:
                    print("FAIL: chip title missing degraded field text")
                    ok = False
                else:
                    print("PASS: chip rendered + title lists degraded field")
                txt = chips.first.text_content() or ""
                if "数据降级" not in txt:
                    print("FAIL: chip text missing 数据降级")
                    ok = False

            page.screenshot(
                path=str(SCREEN_DIR / "data_quality_degraded.png"), full_page=True
            )
            print(f"\nVERDICT: {'PASS' if ok else 'FAIL'}")
            sys.exit(0 if ok else 1)
        finally:
            b.close()


if __name__ == "__main__":
    main()
