"""W2-E1..E5 e2e: ResearchPanel renders W2.7+ structured research blocks.

Mocks /api/portfolio/decisions to return a row with full schema (thesis,
valuation, scenarios with prob sum 1.0, catalysts, risks, derivations)
+ a row with prob sum 0.7 (must show warning) + a row with no blocks
(back-compat). Asserts the right sections appear / don't appear.
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
NOW = "2026-05-08T04:00:00Z"


def _row(order_id, symbol, **md_overrides):
    md = {"confidence": 7, "reasoning": "test"}
    md.update(md_overrides)
    return {
        "order_id": order_id,
        "symbol": symbol,
        "side": "buy",
        "intent": "open_long",
        "decision_type": "order",
        "decision_price": 100.0,
        "quantity": 0.0,
        "status": "suggested",
        "filled_qty": 0,
        "filled_avg_price": None,
        "filled_at": None,
        "user_transaction_id": None,
        "created_at": NOW,
        "analysis_id": "test",
        "chat_id": "test-chat",
        "recommendation_source": "single_symbol",
        "pnl_snapshots": {},
        "metadata": md,
    }


FULL = _row(
    "test-full",
    "TFUL",
    thesis=["secular AI demand", "operating leverage", "buyback float reduction"],
    valuation=[
        {"method": "pe_vs_peer", "value": 28.5, "note": "vs MAG7 median 31"},
        {"method": "ev_revenue", "value": 7.2, "note": "vs sector 5.5"},
    ],
    price_target={"value": 320.0, "horizon_days": 365, "method": "blended"},
    scenarios={
        "bull": {"price_target": 360, "probability": 0.30, "rationale": "..."},
        "base": {"price_target": 320, "probability": 0.50, "rationale": "..."},
        "bear": {"price_target": 240, "probability": 0.20, "rationale": "..."},
    },
    catalysts=[
        {"event": "Q1 earnings", "eta_window": "2026-05-15"},
        {"event": "FOMC decision", "eta_window": "2026-06-12"},
    ],
    risks=["macro shock", "earnings miss", "supply constraint"],
    entry_derivation={"value": 100.0, "formula": "support level $100", "inputs": {"swing_low": 100}},
    stop_derivation={"value": 95.0, "formula": "price - n * atr", "inputs": {"price": 100, "atr": 2.5, "n": 2}},
)
BAD_PROB = _row(
    "test-bad-prob",
    "TBAD",
    scenarios={
        "bull": {"price_target": 360, "probability": 0.30, "rationale": "..."},
        "base": {"price_target": 320, "probability": 0.20, "rationale": "..."},
        "bear": {"price_target": 240, "probability": 0.20, "rationale": "..."},
    },
)
BARE = _row("test-bare", "TBAR")  # no W2.7+ blocks


def main() -> None:
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            ctx = b.new_context(locale="zh-CN", viewport={"width": 1920, "height": 1200}, device_scale_factor=2)
            page = ctx.new_page()

            def handle(route: Route) -> None:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"decisions": [FULL, BAD_PROB, BARE], "count": 3}),
                )

            page.route("**/api/portfolio/decisions*", handle)
            page.goto(URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(6000)

            # Click each row to expand it (DecisionTracker rows are <tr>).
            for sym in ("TFUL", "TBAD", "TBAR"):
                try:
                    page.locator(f"tr:has(td:text-is('{sym}'))").first.click(timeout=4000)
                    page.wait_for_timeout(400)
                except Exception:
                    pass

            # Scroll the first ResearchPanel into view so the screenshot
            # actually captures the rendered structured-research output
            # (the dashboard is long; default screenshot starts at top).
            try:
                page.locator("[data-testid=research-panel]").first.scroll_into_view_if_needed(timeout=2000)
                page.wait_for_timeout(300)
            except Exception:
                pass

            # Hide sticky/fixed chrome (header, sidebar, footer watermark) so
            # the panel screenshot isn't obscured. Then bounding-box crop
            # both panels at full resolution.
            page.add_style_tag(content="""
                [data-testid=research-panel] {
                  background: white !important;
                  position: fixed !important;
                  left: 20px !important;
                  top: 20px !important;
                  width: 1100px !important;
                  max-width: 1100px !important;
                  z-index: 99999 !important;
                  box-shadow: 0 0 0 2px #2563eb !important;
                }
            """)
            page.wait_for_timeout(200)

            ok = True
            counts = {
                "research-panel": page.locator("[data-testid=research-panel]").count(),
                "thesis": page.locator("[data-testid=research-thesis]").count(),
                "valuation": page.locator("[data-testid=research-valuation]").count(),
                "scenarios": page.locator("[data-testid=research-scenarios]").count(),
                "catalysts": page.locator("[data-testid=research-catalysts]").count(),
                "risks": page.locator("[data-testid=research-risks]").count(),
                "prob-warning": page.locator("[data-testid=scenarios-prob-warning]").count(),
                "deriv-entry": page.locator("[data-testid=derivation-entry]").count(),
                "deriv-stop": page.locator("[data-testid=derivation-stop]").count(),
            }
            for k, v in counts.items():
                print(f"  {k}: {v}")

            # FULL row should produce 1 of each section + 2 derivation chips.
            # BAD_PROB row produces a panel with scenarios + warning.
            # BARE row produces NO panel (back-compat).
            if counts["research-panel"] != 2:
                print("FAIL: expected 2 panels (FULL + BAD_PROB), not BARE")
                ok = False
            else:
                print("PASS W2-E5: bare row has no panel (back-compat)")

            if counts["thesis"] != 1:
                print("FAIL: thesis section count != 1")
                ok = False
            else:
                print("PASS W2-E2 thesis")
            if counts["valuation"] != 1:
                print("FAIL: valuation count != 1")
                ok = False
            else:
                print("PASS W2-E2 valuation")
            if counts["catalysts"] != 1:
                print("FAIL: catalysts != 1")
                ok = False
            if counts["risks"] != 1:
                print("FAIL: risks != 1")
                ok = False

            if counts["scenarios"] != 2:
                print("FAIL: scenarios count != 2 (FULL + BAD_PROB)")
                ok = False
            else:
                print("PASS W2-E2 scenarios (both rows)")
            if counts["prob-warning"] != 1:
                print("FAIL: bad-prob row should show 1 warning, FULL row 0")
                ok = False
            else:
                print("PASS W2-E3 prob warning shown for bad-prob row only")

            if counts["deriv-entry"] != 1 or counts["deriv-stop"] != 1:
                print("FAIL: derivation chips not rendered correctly")
                ok = False
            else:
                print("PASS W2-E4 derivation chips")

            page.screenshot(path=str(SCREEN_DIR / "research_panel.png"), full_page=True)

            # Also dump a tight crop of just the Decision Tracker / panels
            # area for high-DPI proof shots.
            try:
                panels = page.locator("[data-testid=research-panel]")
                n = panels.count()
                names = ["research_panel_full.png", "research_panel_badprob.png"]
                for idx in range(min(n, 2)):
                    page.evaluate(
                        """(target) => {
                            document.querySelectorAll('[data-testid=research-panel]').forEach((el, i) => {
                                el.style.display = (i === target) ? '' : 'none';
                            });
                        }""",
                        idx,
                    )
                    page.wait_for_timeout(200)
                    panel = panels.nth(idx)
                    box = panel.bounding_box()
                    print(f"  {names[idx]} bbox: {box}")
                    if box:
                        page.screenshot(
                            path=str(SCREEN_DIR / names[idx]),
                            clip={"x": box["x"], "y": box["y"], "width": box["width"], "height": box["height"]},
                        )
                        print(f"  shot {names[idx]}")
            except Exception as e:
                print(f"crop screenshot skipped: {e}")
            print(f"\nVERDICT: {'PASS' if ok else 'FAIL'}")
            sys.exit(0 if ok else 1)
        finally:
            b.close()


if __name__ == "__main__":
    main()
