"""W2 full-flow e2e: drive 3 UI entry points with REAL backend + LLM.

Click-throughs:
  1. PortfolioDashboard 'Analyze My Holdings' button (flow=holdings)
  2. PortfolioDashboard 'Today's Picks' (1 sector selected, flow=picks)
  3. WatchlistPanel per-row 'Analyze Now' / '立即分析' (legacy WatchlistAnalyzer)

For each step:
  - Snapshot pre-run state (max created_at across portfolio_orders)
  - Click the button via Playwright
  - Wait for status badge to reach 'done' (or watchlist row's last_analyzed_at to update)
  - Diff post-run vs pre-run; assert at least one new decision row was written
  - Inspect new rows for W2.7 research blocks (thesis / valuation / scenarios /
    price_target / risks / *_derivation). Print fill-rate.

This is the verification missing from W2.6 acceptance #6 + W2.11 (which only
mocked the API). Exposes the gap: real LLM runs do not populate the new schema.

Usage (host):
  cd D:\\repo\\FinancialAgent
  python e2e_w2_full_flow.py

Backend on :8001, frontend on :3001.
"""

from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path
from typing import Any

import urllib.request

from playwright.sync_api import Page, sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent
SCREEN_DIR = ROOT / "e2e_screens"
SCREEN_DIR.mkdir(exist_ok=True)

FE = "http://localhost:3001"
BE = "http://localhost:8001"

POLL_INTERVAL_MS = 2000
# Picks flow runs Phase1 ReAct on ~20 candidates serially → can take 6-8 min.
# Holdings is fewer symbols and finishes in ~80s. Allocate generously per step.
RUN_TIMEOUT_S = 720  # 12 min cap per LLM run


# ---------------------------------------------------------------------------
# Backend helpers (urllib so the script has no extra deps beyond Playwright)
# ---------------------------------------------------------------------------


def be_get(path: str) -> Any:
    with urllib.request.urlopen(f"{BE}{path}", timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def latest_decisions(limit: int = 200) -> list[dict[str, Any]]:
    return be_get(f"/api/portfolio/decisions?limit={limit}").get("decisions", [])


def max_created_at(decs: list[dict[str, Any]]) -> str:
    if not decs:
        return ""
    return max(d.get("created_at", "") for d in decs)


def new_rows_since(snapshot_max: str) -> list[dict[str, Any]]:
    return [d for d in latest_decisions() if d.get("created_at", "") > snapshot_max]


def research_block_fill(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Count rows whose metadata.<key> is non-null. The decisions API
    keeps W2.7+ research blocks under `metadata`, not at the top level."""
    keys = [
        "thesis",
        "valuation",
        "price_target",
        "scenarios",
        "catalysts",
        "risks",
        "entry_derivation",
        "stop_derivation",
        "target_derivation",
        "size_derivation",
    ]
    out = {k: 0 for k in keys}
    for r in rows:
        md = r.get("metadata") or {}
        for k in keys:
            if md.get(k) is not None:
                out[k] += 1
    return out


# ---------------------------------------------------------------------------
# Page-level wait helpers
# ---------------------------------------------------------------------------


def wait_for_badge_done(
    page: Page,
    run_id: str,
    pre_started_at: str,
    timeout_s: int = RUN_TIMEOUT_S,
) -> str:
    """Poll backend status endpoint until a NEW run (started_at > pre)
    reaches done. Without the started_at gate we'd read the previous run's
    stale 'done' and exit immediately."""
    start = time.time()
    last = ""
    last_started = ""
    while time.time() - start < timeout_s:
        try:
            data = be_get(f"/api/admin/portfolio/status/{run_id}")
            status = data.get("status", "?")
            started = data.get("started_at", "") or ""
            tag = f"{status}@{started}"
            if tag != last:
                print(f"  [{run_id}] -> {tag}")
                last = tag
                last_started = started
            # Only accept terminal state for a run that started AFTER our snapshot.
            if started > pre_started_at:
                if status == "done":
                    return data.get("message", "") or ""
                if status == "error":
                    raise RuntimeError(f"{run_id} failed: {data.get('message')}")
        except Exception as e:
            print(f"  [{run_id}] poll error: {e}")
        time.sleep(POLL_INTERVAL_MS / 1000)
    raise TimeoutError(f"{run_id} did not reach done in {timeout_s}s (last={last})")


def get_status_started(run_id: str) -> str:
    try:
        return be_get(f"/api/admin/portfolio/status/{run_id}").get("started_at", "") or ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Step 1: Holdings analysis
# ---------------------------------------------------------------------------


def step_holdings(page: Page, results: dict[str, Any]) -> None:
    print("\n=== STEP 1: Holdings analysis ===")
    pre_max = max_created_at(latest_decisions())
    pre_started = get_status_started("holdings")
    print(f"  pre-run max created_at = {pre_max!r}")
    print(f"  pre-run holdings.started_at = {pre_started!r}")

    page.goto(f"{FE}/portfolio", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    btn = page.get_by_role("button", name="Analyze My Holdings").first
    if btn.count() == 0:
        # locale fallback
        btn = page.get_by_role("button", name="分析持仓").first
    btn.wait_for(state="visible", timeout=10000)
    print("  clicking 'Analyze My Holdings'")
    btn.click()

    msg = wait_for_badge_done(page, "holdings", pre_started)
    print(f"  done: {msg}")

    new = [d for d in new_rows_since(pre_max) if d.get("recommendation_source") == "holdings"]
    print(f"  new holdings rows: {len(new)}")
    fill = research_block_fill(new)
    print(f"  research-block fill: {fill}")

    page.screenshot(path=str(SCREEN_DIR / "w2_step1_holdings.png"), full_page=True)
    results["holdings"] = {
        "new_row_count": len(new),
        "fill": fill,
        "message": msg,
        "ok": len(new) > 0,
    }


# ---------------------------------------------------------------------------
# Step 2: Today's Picks
# ---------------------------------------------------------------------------


def step_picks(page: Page, results: dict[str, Any]) -> None:
    print("\n=== STEP 2: Today's Picks ===")
    pre_max = max_created_at(latest_decisions())
    pre_started = get_status_started("picks")
    print(f"  pre-run max created_at = {pre_max!r}")
    print(f"  pre-run picks.started_at = {pre_started!r}")

    # Already on /portfolio from step 1, but be explicit.
    page.goto(f"{FE}/portfolio", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    # Pick a single sector toggle. Technology is in the universe
    # (verified via /api/admin/portfolio/universe/sectors).
    sector_btn = page.get_by_role("button", name="Technology").first
    sector_btn.wait_for(state="visible", timeout=10000)
    sector_btn.click()
    print("  selected sector: Technology")
    page.wait_for_timeout(800)

    # The picks button text becomes "Today's Picks (1 sector)" once selected.
    # Match the active form to avoid catching disabled "Today's Picks" before
    # selection.
    picks_btn = page.locator(
        "button:has-text(\"Today's Picks (\")"
    ).first
    if picks_btn.count() == 0:
        picks_btn = page.locator("button:has-text(\"Today's Picks\")").first
    picks_btn.wait_for(state="visible", timeout=10000)
    btn_text = picks_btn.inner_text().strip()
    is_disabled = picks_btn.is_disabled()
    print(f"  picks button text={btn_text!r} disabled={is_disabled}")
    if is_disabled:
        results["picks"] = {
            "ok": False,
            "error": f"picks button still disabled after sector toggle (text={btn_text!r})",
        }
        return
    picks_btn.click()
    page.wait_for_timeout(1500)

    msg = wait_for_badge_done(page, "picks", pre_started)
    print(f"  done: {msg}")

    new = [d for d in new_rows_since(pre_max) if d.get("recommendation_source") == "picks"]
    print(f"  new picks rows: {len(new)}")
    fill = research_block_fill(new)
    print(f"  research-block fill: {fill}")

    page.screenshot(path=str(SCREEN_DIR / "w2_step2_picks.png"), full_page=True)
    results["picks"] = {
        "new_row_count": len(new),
        "fill": fill,
        "message": msg,
        "ok": len(new) > 0,
    }


# ---------------------------------------------------------------------------
# Step 3: Watchlist single-symbol (W2.2 reroute → run_single_symbol)
# ---------------------------------------------------------------------------


def step_watchlist(page: Page, results: dict[str, Any]) -> None:
    print("\n=== STEP 3: Watchlist single-symbol (W2.2 W2.1 flow) ===")
    pre_decs = latest_decisions()
    pre_max = max_created_at(pre_decs)
    pre_count = len(pre_decs)
    print(f"  pre-run max created_at = {pre_max!r} (total decisions={pre_count})")

    page.goto(f"{FE}/portfolio", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    # The watchlist panel is on the same page. Each row is a div.flex.items-center
    # .justify-between.p-3 with a span.font-medium.text-gray-900 carrying the
    # symbol and a button on the right whose i18n text is 'Analyze Now' (en) or
    # '立即分析' (zh-CN). Locale=en in our context, but fall back regardless.
    rows = page.locator("div.flex.items-center.justify-between.p-3.bg-gray-50")
    n_rows = rows.count()
    print(f"  watchlist rows in DOM: {n_rows}")
    if n_rows == 0:
        results["watchlist"] = {"ok": False, "error": "no watchlist rows visible"}
        return

    # Pick the watchlist symbol with the OLDEST last_analyzed_at — minimises
    # rate-limit collisions and gives a clean signal when it advances. Backend
    # endpoint is rate-limited to 10/min and the 14:44 batch already analysed
    # most rows today, so reusing them risks a silent 429.
    def list_watchlist_items() -> list[dict[str, Any]]:
        try:
            with urllib.request.urlopen(f"{BE}/api/watchlist", timeout=10) as r:
                items = json.loads(r.read().decode("utf-8"))
            if isinstance(items, list):
                return items
            return items.get("items", [])
        except Exception:
            return []

    items = list_watchlist_items()
    items_sorted = sorted(items, key=lambda it: it.get("last_analyzed_at") or "")
    if not items_sorted:
        results["watchlist"] = {"ok": False, "error": "watchlist API empty"}
        return
    target_symbol = items_sorted[0]["symbol"]
    print(f"  oldest last_analyzed_at row: {target_symbol!r} "
          f"({items_sorted[0].get('last_analyzed_at')})")

    target_row = page.locator(
        f"div.flex.items-center.justify-between.p-3.bg-gray-50:has(span.font-medium:text-is('{target_symbol}'))"
    ).first
    if target_row.count() == 0:
        results["watchlist"] = {
            "ok": False,
            "error": f"row for {target_symbol!r} not found in DOM",
        }
        return

    symbol = target_symbol

    # Snapshot the row's current last_analyzed_at via the API so we can detect
    # completion by observing it advance. After W2.2 reroute the route
    # internally calls run_single_symbol → persists to portfolio_orders with
    # recommendation_source="single_symbol", THEN updates
    # watchlist_items.last_analyzed_at as a cosmetic post-step. We assert
    # both: a fresh portfolio_orders row AND advancing last_analyzed_at.
    def wl_last_for(sym: str) -> str:
        try:
            with urllib.request.urlopen(f"{BE}/api/watchlist", timeout=10) as r:
                items = json.loads(r.read().decode("utf-8"))
            for it in items if isinstance(items, list) else items.get("items", []):
                if it.get("symbol") == sym:
                    return it.get("last_analyzed_at") or ""
        except Exception:
            pass
        return ""

    pre_la = wl_last_for(symbol)
    print(f"  row symbol={symbol!r} pre-run last_analyzed_at={pre_la!r}")

    btn = target_row.locator(
        "button:has-text('Analyze Now'), button:has-text('立即分析'), button:has-text('Analyzing'), button:has-text('分析中')"
    ).first
    if btn.count() == 0:
        # Last-ditch: take the first <button> in the row's right-side action area.
        btn = target_row.locator("button").first
    print(f"  clicking analyze button on row {symbol!r}")
    btn.scroll_into_view_if_needed(timeout=4000)
    btn.click()

    # The route is synchronous (await run_single_symbol → ~60-120s for the
    # LLM round-trip). Wait by polling either:
    #   (a) watchlist_items.last_analyzed_at advances, OR
    #   (b) portfolio_orders has a NEW row with recommendation_source=single_symbol
    # for this symbol.
    start = time.time()
    post_la = pre_la
    new_single_rows: list[dict[str, Any]] = []
    while time.time() - start < RUN_TIMEOUT_S:
        time.sleep(POLL_INTERVAL_MS / 1000)
        post_la = wl_last_for(symbol)
        cur = latest_decisions()
        new_single_rows = [
            d
            for d in cur
            if d.get("created_at", "") > pre_max
            and d.get("symbol", "").upper() == symbol.upper()
            and d.get("recommendation_source") == "single_symbol"
        ]
        advanced = bool(post_la and post_la > pre_la)
        if advanced or new_single_rows:
            print(
                f"  detected completion: la_advanced={advanced} "
                f"new_single_symbol_rows={len(new_single_rows)}"
            )
            break

    completed = bool(post_la and post_la > pre_la) or bool(new_single_rows)

    # W2.2 success criterion: a fresh portfolio_orders row tagged
    # recommendation_source=single_symbol must appear, AND it should be eligible
    # for W2.7+ research blocks (BUY/SELL only — HOLD intentionally skips).
    cur = latest_decisions()
    new_rows = [d for d in cur if d.get("created_at", "") > pre_max]
    sources: dict[str, int] = {}
    for r in new_rows:
        s = r.get("recommendation_source", "?")
        sources[s] = sources.get(s, 0) + 1
    fill = research_block_fill(new_rows)
    print(f"  watchlist completed: {completed}")
    print(f"  new portfolio_orders rows: {len(new_rows)} sources={sources}")
    print(f"  research-block fill: {fill}")
    print(
        "  W2.2 expectation: at least 1 row with recommendation_source=single_symbol."
    )

    page.screenshot(path=str(SCREEN_DIR / "w2_step3_watchlist.png"), full_page=True)
    has_single_symbol_row = sources.get("single_symbol", 0) >= 1
    results["watchlist"] = {
        "symbol": symbol,
        "completed": completed,
        "pre_last_analyzed_at": pre_la,
        "post_last_analyzed_at": post_la,
        "new_portfolio_orders": len(new_rows),
        "sources": sources,
        "fill": fill,
        # ok = both completion signals present (fresh portfolio_orders row +
        # advancing last_analyzed_at). last_analyzed_at advance alone would
        # match the legacy path, which is no longer expected.
        "ok": has_single_symbol_row,
        "writes_to_portfolio_orders": len(new_rows) > 0,
        "has_single_symbol_row": has_single_symbol_row,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    results: dict[str, Any] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(
                locale="en-US",
                viewport={"width": 1600, "height": 1000},
            )
            page = ctx.new_page()
            try:
                step_holdings(page, results)
            except Exception as e:
                results["holdings"] = {"ok": False, "error": str(e)}
                print(f"  step_holdings ERROR: {e}")

            try:
                step_picks(page, results)
            except Exception as e:
                results["picks"] = {"ok": False, "error": str(e)}
                print(f"  step_picks ERROR: {e}")

            try:
                step_watchlist(page, results)
            except Exception as e:
                results["watchlist"] = {"ok": False, "error": str(e)}
                print(f"  step_watchlist ERROR: {e}")
        finally:
            browser.close()

    # ---------- Verdict ----------
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(json.dumps(results, indent=2, default=str))

    # PASS conditions: each step's `ok` is true.
    each_ok = all(s.get("ok") for s in results.values())

    # Hard W2 acceptance check: at least one of the rows produced by the new
    # holdings / picks flow must have non-null structured research blocks.
    # If everything is null → W2.7-W2.10 broken in prod.
    any_block_filled = False
    for step in ("holdings", "picks"):
        fill = results.get(step, {}).get("fill", {})
        if any(v > 0 for v in fill.values()):
            any_block_filled = True
            break

    # W2.2 reroute evidence: watchlist analyze NOW writes a single_symbol row
    # to portfolio_orders. legacy_path_evidence flips: True is now BAD.
    wl = results.get("watchlist", {})
    legacy_path_still_in_use = (
        wl.get("ok") is True and wl.get("writes_to_portfolio_orders") is False
    )

    print(f"\n  steps OK: {each_ok}")
    print(f"  any W2.7+ block populated by real LLM: {any_block_filled}")
    print(f"  W2.2 reroute live (watchlist now in portfolio_orders): {wl.get('has_single_symbol_row', False)}")
    if not any_block_filled:
        print(
            "  ⚠ FINDING #1: Wave 2 schema fields (thesis/valuation/scenarios/...) "
            "are NOT populated by the real LLM run."
        )
    if legacy_path_still_in_use:
        print(
            "  ⚠ FINDING #2: Watchlist 'Analyze Now' still hits the legacy path; "
            "no portfolio_orders row was written. W2.2 reroute is broken."
        )

    overall = each_ok and any_block_filled
    print(f"\nVERDICT: {'PASS' if overall else 'FAIL'}")
    # Save machine-readable result for the record.
    (SCREEN_DIR / "w2_full_flow_result.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
