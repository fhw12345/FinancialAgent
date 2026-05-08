"""E2E proof: selection-drag-out no longer dismisses HoldingFormModal.

Bug being verified:
    User clicks "Add Holding" → modal opens. They select text in an input by
    holding mousedown and dragging the cursor outside the modal card. On
    mouseup, the click event lands on the backdrop and the modal closes,
    losing their input.

Fix verified by this script:
    Backdrop now distinguishes a true backdrop click (mousedown AND mouseup
    both on the backdrop) from a stray mouseup that started inside the card.
    Only the former dismisses.

Flow:
1. Visit dashboard (zh-CN), wait for portfolio table.
2. Click Add Holding button → assert modal is visible.
3. Type a value into the Quantity input.
4. Simulate selection-drag: mouse.move into the input, mouse.down(), drag
   far outside the modal, mouse.up().
5. Assert modal is STILL open and Quantity value preserved.
6. Then verify the legitimate-close path still works: click on bare backdrop
   → modal dismisses.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SCREEN_DIR = Path(__file__).parent / "e2e_screens"
SCREEN_DIR.mkdir(exist_ok=True)
URL = "http://localhost:3001"


def main() -> None:
    failures: list[str] = []

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            ctx = b.new_context(locale="zh-CN", viewport={"width": 1400, "height": 900})
            page = ctx.new_page()
            page.goto(URL, wait_until="domcontentloaded")
            # Wait for portfolio root
            page.wait_for_selector("text=持仓", timeout=10_000)

            # Find Add Holding button (zh "添加持股" or en "Add Holding")
            add_btn = page.get_by_role("button", name="添加持股")
            if add_btn.count() == 0:
                add_btn = page.get_by_role("button", name="Add Holding")
            if add_btn.count() == 0:
                # Fallback: any button containing the plus + "Add"
                add_btn = page.locator("button:has-text('Add')").first
            add_btn.first.click()

            # Modal should be visible
            modal = page.locator("[role=dialog]")
            modal.wait_for(state="visible", timeout=5_000)
            print("step1 modal opened")

            # Fill quantity (skip symbol — selection drag from quantity is
            # the simplest reproduction; symbol uses an autocomplete popover)
            qty = modal.locator("input[type=number]").first
            qty.fill("12345")

            box = qty.bounding_box()
            assert box is not None, "quantity input has no bounding box"

            # Press inside the input, drag far outside the modal, release
            # outside. Pre-fix this would dismiss the modal.
            page.mouse.move(box["x"] + 10, box["y"] + box["height"] / 2)
            page.mouse.down()
            page.mouse.move(box["x"] + 10, box["y"] + box["height"] / 2, steps=2)
            # End point: outside the modal (top-left corner of viewport)
            page.mouse.move(20, 20, steps=10)
            page.mouse.up()
            page.wait_for_timeout(300)

            still_open = modal.is_visible()
            preserved_value = qty.input_value() if still_open else ""
            print(f"step2 after drag-out: modal_open={still_open} qty='{preserved_value}'")

            if not still_open:
                failures.append("modal dismissed by selection-drag-out (regression)")
            elif preserved_value != "12345":
                failures.append(f"quantity lost during drag: '{preserved_value}'")
            else:
                print("PASS drag-out preserved modal + value")

            page.screenshot(path=str(SCREEN_DIR / "holding_modal_after_drag.png"))

            # Now verify true backdrop click still closes the modal.
            # Click on a region clearly outside the white card (top of
            # viewport, well above the centered modal box).
            page.mouse.click(20, 20)
            page.wait_for_timeout(300)
            closed = not modal.is_visible()
            print(f"step3 backdrop click: modal_closed={closed}")
            if not closed:
                failures.append("backdrop click no longer dismisses modal (broke close path)")
            else:
                print("PASS backdrop click still closes")

        finally:
            b.close()

    if failures:
        print("\nVERDICT: FAIL")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("\nVERDICT: PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()
