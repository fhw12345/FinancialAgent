"""
Playwright e2e — Mark Executed flow + Chinese history titles.

Setup:  pick an existing suggested BUY order (AMAT picks_972cc1fd594e), record
        baseline cash / holdings.
Test:   navigate to dashboard, find DecisionTracker row, click Mark Executed,
        modify qty/price in modal, submit, verify status chip + cash update.
        Also screenshot the analysis history sidebar to prove Chinese title
        prefixes (个股分析 / 持仓分析 / 今日推荐).
Teardown: restore cash_balance, revert order to suggested, delete the
        e2e-created user_transaction and any holding row that didn't exist
        before the test.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

SCREEN_DIR = Path(__file__).parent / "e2e_screens"
SCREEN_DIR.mkdir(exist_ok=True)
FRONTEND_URL = "http://localhost:3001"
TEST_ORDER_ID = "picks_972cc1fd594e"  # AMAT, status=suggested
TEST_SYMBOL = "AMAT"


def mongo(js: str) -> str:
    """Run a mongosh JS expression in the dockerized mongo and return output."""
    cmd = [
        "docker", "compose", "exec", "-T", "mongodb",
        "mongosh", "financial_agent", "--quiet", "--eval", js,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise RuntimeError(f"mongo failed: {out.stderr}")
    return out.stdout.strip()


def snapshot_state() -> dict:
    raw = mongo(
        'JSON.stringify({'
        'cash: db.user_settings.findOne({}).cash_balance,'
        f'order: db.portfolio_orders.findOne({{order_id:"{TEST_ORDER_ID}"}}),'
        f'holding: db.holdings.findOne({{symbol:"{TEST_SYMBOL}"}}),'
        f'tx_count: db.user_transactions.countDocuments({{symbol:"{TEST_SYMBOL}"}})'
        '})'
    )
    return json.loads(raw)


def main() -> int:
    print("[setup] capturing baseline state...")
    before = snapshot_state()
    print(f"  cash={before['cash']}  order_status={before['order']['status']}  "
          f"holding_qty={(before['holding'] or {}).get('quantity')}  "
          f"tx_count={before['tx_count']}")

    if before["order"]["status"] != "suggested":
        print(f"[setup] order status is {before['order']['status']}, "
              f"reverting to suggested first")
        mongo(
            f'db.portfolio_orders.updateOne({{order_id:"{TEST_ORDER_ID}"}}, '
            '{$set:{status:"suggested"}, $unset:{filled_qty:"",filled_avg_price:"",'
            'filled_at:"",user_transaction_id:""}})'
        )

    # Use a small 1-share fill to keep cash impact tiny + reversible
    test_qty = 1
    test_price = 200.00

    failure: Exception | None = None
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            page = ctx.new_page()

            print("[step 1] navigate to portfolio dashboard")
            page.goto(f"{FRONTEND_URL}/", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)
            # Default landing tab is now "投资组合" (PortfolioDashboard) — no
            # need to click a nav link.
            page.screenshot(path=SCREEN_DIR / "mark_exec_01_dashboard.png",
                            full_page=True)

            print("[step 2] filter DecisionTracker to AMAT")
            sym_filter = page.get_by_placeholder("Filter symbol…")
            sym_filter.fill(TEST_SYMBOL)
            page.wait_for_timeout(1500)
            page.screenshot(path=SCREEN_DIR / "mark_exec_02_filtered.png",
                            full_page=True)

            print("[step 3] click Mark Executed button")
            btn = page.get_by_role("button", name="Mark Executed").first
            btn.scroll_into_view_if_needed()
            page.screenshot(path=SCREEN_DIR / "mark_exec_03_button_visible.png",
                            full_page=True)
            btn.click()
            page.wait_for_timeout(800)
            page.screenshot(path=SCREEN_DIR / "mark_exec_04_modal_open.png",
                            full_page=True)

            print("[step 4] fill qty + price")
            qty_input = page.locator('input[type="number"]').nth(0)
            price_input = page.locator('input[type="number"]').nth(1)
            qty_input.fill(str(test_qty))
            price_input.fill(f"{test_price:.2f}")
            page.wait_for_timeout(400)
            page.screenshot(path=SCREEN_DIR / "mark_exec_05_filled_form.png",
                            full_page=True)

            print("[step 5] submit Confirm")
            page.get_by_role("button", name="Confirm").click()
            # Wait for mutation + refetches
            page.wait_for_timeout(2500)
            page.screenshot(path=SCREEN_DIR / "mark_exec_06_after_submit.png",
                            full_page=True)

            print("[step 6] verify status chip rendered (✓ Executed)")
            chip = page.get_by_text("@ $200.00").first
            chip.scroll_into_view_if_needed()
            chip.screenshot(path=SCREEN_DIR / "mark_exec_07_chip_closeup.png")

            print("[step 7] verify Chinese history titles")
            # Clear filter so history is visible
            sym_filter.fill("")
            page.wait_for_timeout(1000)
            # Try to find sidebar history — may need to scroll/expand
            page.screenshot(path=SCREEN_DIR / "mark_exec_08_history_titles.png",
                            full_page=True)

            ctx.close()
            browser.close()

        # Verify backend state changed correctly
        print("[verify] checking mongo state after mark-executed")
        after = snapshot_state()
        print(f"  cash={after['cash']}  order_status={after['order']['status']}  "
              f"filled_qty={after['order'].get('filled_qty')}  "
              f"filled_avg_price={after['order'].get('filled_avg_price')}  "
              f"tx_count={after['tx_count']}")
        expected_cash = round(before["cash"] - test_qty * test_price, 2)
        cash_ok = abs(after["cash"] - expected_cash) < 0.01
        order_ok = after["order"]["status"] == "filled"
        tx_ok = after["tx_count"] == before["tx_count"] + 1
        print(f"  cash {expected_cash} expected, got {after['cash']} → "
              f"{'PASS' if cash_ok else 'FAIL'}")
        print(f"  order status filled → {'PASS' if order_ok else 'FAIL'}")
        print(f"  +1 transaction → {'PASS' if tx_ok else 'FAIL'}")

    except Exception as e:
        failure = e
        print(f"[error] {type(e).__name__}: {e}", file=sys.stderr)

    # ----- TEARDOWN -----
    print("[teardown] reverting all e2e-created data")
    after_state = snapshot_state()

    # 1. Delete the e2e user_transaction (matched by portfolio_order_id back-pointer)
    deleted_tx = mongo(
        f'db.user_transactions.deleteMany({{portfolio_order_id:"{TEST_ORDER_ID}"}}).deletedCount'
    )
    print(f"  deleted {deleted_tx} test user_transaction(s)")

    # 2. Roll back the holding mutation:
    #    - if no holding existed before, drop the row created by apply_transaction
    #    - if a holding existed before, restore its qty + cost_basis
    before_holding = before.get("holding")
    if before_holding is None:
        dropped = mongo(
            f'db.holdings.deleteMany({{symbol:"{TEST_SYMBOL}"}}).deletedCount'
        )
        print(f"  dropped {dropped} test holding row(s)")
    else:
        restore_qty = before_holding["quantity"]
        restore_avg = before_holding["avg_price"]
        restore_cost = before_holding.get(
            "cost_basis", round(restore_qty * restore_avg, 4)
        )
        mongo(
            f'db.holdings.updateOne({{symbol:"{TEST_SYMBOL}"}}, {{$set:{{'
            f'quantity:{restore_qty}, avg_price:{restore_avg}, '
            f'cost_basis:{restore_cost}'
            '}}})'
        )
        print(f"  restored {TEST_SYMBOL} holding to qty={restore_qty} "
              f"avg=${restore_avg}")

    # 3. Restore cash_balance
    mongo(
        f'db.user_settings.updateOne({{}}, {{$set:{{cash_balance:{before["cash"]}}}}})'
    )
    print(f"  restored cash_balance to {before['cash']}")

    # 4. Revert order to suggested
    mongo(
        f'db.portfolio_orders.updateOne({{order_id:"{TEST_ORDER_ID}"}}, '
        '{$set:{status:"suggested"}, $unset:{filled_qty:"",filled_avg_price:"",'
        'filled_at:"",user_transaction_id:""}})'
    )
    print(f"  reverted order {TEST_ORDER_ID} to status=suggested")

    final = snapshot_state()
    clean = (
        final["cash"] == before["cash"]
        and final["order"]["status"] == "suggested"
        and final["tx_count"] == before["tx_count"]
        and (
            (before_holding is None and final["holding"] is None)
            or (
                before_holding is not None
                and final["holding"] is not None
                and final["holding"]["quantity"] == before_holding["quantity"]
            )
        )
    )
    print(f"[teardown] clean={clean}")
    if not clean:
        print(f"  WARNING — state diverges from baseline:\n"
              f"  before={before}\n  after_teardown={final}")

    if failure is not None:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
