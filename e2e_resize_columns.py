"""Playwright e2e — drag-resize the portfolio dashboard left/right columns.

Verifies the new ResizableColumn behavior: drags the left column handle
+120px and the right column handle -120px, then checks that
localStorage["portfolio:leftWidth"] / ["portfolio:rightWidth"] reflect
the new sizes (rounded). Screenshots saved to e2e_screens/.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SCREEN_DIR = Path(__file__).parent / "e2e_screens"
SCREEN_DIR.mkdir(exist_ok=True)
FRONTEND_URL = "http://localhost:3001"


def main() -> int:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1600, "height": 900})
        page = ctx.new_page()

        page.goto(FRONTEND_URL, wait_until="networkidle", timeout=30000)
        # Default tab is now portfolio — clear any prior width prefs first
        page.evaluate(
            "localStorage.removeItem('portfolio:leftWidth');"
            "localStorage.removeItem('portfolio:rightWidth');"
        )
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(1500)
        page.screenshot(path=SCREEN_DIR / "resize_01_initial.png", full_page=True)

        # Find both drag handles. Both are role=separator vertical.
        handles = page.locator('[role="separator"][aria-orientation="vertical"]')
        count = handles.count()
        print(f"[step 1] found {count} drag handles")
        if count != 2:
            print(f"[ERROR] expected 2 handles, got {count}")
            ctx.close()
            browser.close()
            return 1

        left_handle = handles.nth(0)
        right_handle = handles.nth(1)
        lh_box = left_handle.bounding_box()
        rh_box = right_handle.bounding_box()
        if not lh_box or not rh_box:
            print("[ERROR] could not get handle bounding boxes")
            return 1
        print(f"  left handle  x={lh_box['x']:.1f} y={lh_box['y']:.1f} "
              f"w={lh_box['width']:.1f} h={lh_box['height']:.1f}")
        print(f"  right handle x={rh_box['x']:.1f} y={rh_box['y']:.1f} "
              f"w={rh_box['width']:.1f} h={rh_box['height']:.1f}")

        # Drag left handle +120px to the right (widen left column).
        # Aim at the handle center; some browsers fail to dispatch mousedown
        # if you click within 1px of the absolute element's edge.
        print("[step 2] drag left handle +120px")
        lh_cx = lh_box["x"] + lh_box["width"] / 2
        lh_cy = lh_box["y"] + lh_box["height"] / 2
        page.mouse.move(lh_cx, lh_cy)
        page.mouse.down()
        page.mouse.move(lh_cx + 120, lh_cy, steps=10)
        page.mouse.up()
        page.wait_for_timeout(400)
        page.screenshot(path=SCREEN_DIR / "resize_02_after_left.png",
                        full_page=True)

        # Drag right handle -120px to the left (widen right column)
        rh_box2 = right_handle.bounding_box()
        if not rh_box2:
            print("[ERROR] right handle disappeared")
            return 1
        print("[step 3] drag right handle -120px")
        rh_cx = rh_box2["x"] + rh_box2["width"] / 2
        rh_cy = rh_box2["y"] + rh_box2["height"] / 2
        page.mouse.move(rh_cx, rh_cy)
        page.mouse.down()
        page.mouse.move(rh_cx - 120, rh_cy, steps=10)
        page.mouse.up()
        page.wait_for_timeout(400)
        page.screenshot(path=SCREEN_DIR / "resize_03_after_right.png",
                        full_page=True)

        # Read back persisted widths
        left = page.evaluate("localStorage.getItem('portfolio:leftWidth')")
        right = page.evaluate("localStorage.getItem('portfolio:rightWidth')")
        print(f"[verify] localStorage  leftWidth={left}  rightWidth={right}")

        # Reload — widths should survive
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(1000)
        page.screenshot(path=SCREEN_DIR / "resize_04_after_reload.png",
                        full_page=True)

        # Sanity: the left column outer container width should now reflect the
        # stored value (defaultWidth=384 + dragged ~120 → ~504).
        left_after = int(left or "0")
        right_after = int(right or "0")
        ok_left = 480 <= left_after <= 520
        ok_right = 480 <= right_after <= 520
        print(f"  left {left_after} in [480,520] → {'PASS' if ok_left else 'FAIL'}")
        print(f"  right {right_after} in [480,520] → {'PASS' if ok_right else 'FAIL'}")

        ctx.close()
        browser.close()
        return 0 if (ok_left and ok_right) else 1


if __name__ == "__main__":
    sys.exit(main())
