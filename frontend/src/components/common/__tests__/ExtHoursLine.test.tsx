/**
 * W3.18 — ExtHoursLine renders the secondary AH/PM line beneath the
 * primary price cell on Holdings + Watchlist tables.
 *
 * The component must:
 *   * render nothing when price OR session is null (response shape
 *     guarantee — backend leaves both null when no fresh ext-hours
 *     print is available);
 *   * label "AH" for post and "PM" for pre;
 *   * color the percentage green when ≥ 0, red when < 0;
 *   * render the percentage block only when changePercent is non-null.
 */

import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { ExtHoursLine } from "../ExtHoursLine";

describe("ExtHoursLine", () => {
  it("renders nothing when price is null", () => {
    const { container } = render(
      <ExtHoursLine price={null} session="post" changePercent={-0.07} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when session is null", () => {
    const { container } = render(
      <ExtHoursLine price={215.05} session={null} changePercent={-0.07} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("labels post-market session as AH", () => {
    const { container } = render(
      <ExtHoursLine price={215.05} session="post" changePercent={-0.07} />,
    );
    expect(container.textContent).toContain("AH");
    expect(container.textContent).toContain("$215.05");
    expect(container.textContent).toContain("-0.07%");
  });

  it("labels pre-market session as PM", () => {
    const { container } = render(
      <ExtHoursLine price={214.8} session="pre" changePercent={-0.19} />,
    );
    expect(container.textContent).toContain("PM");
    expect(container.textContent).toContain("$214.80");
  });

  it("prefixes positive change with +", () => {
    const { container } = render(
      <ExtHoursLine price={216.5} session="post" changePercent={0.6} />,
    );
    expect(container.textContent).toContain("+0.60%");
  });

  it("colors negative change red", () => {
    const { container } = render(
      <ExtHoursLine price={215.05} session="post" changePercent={-0.07} />,
    );
    const pctSpan = container.querySelector("span.text-red-600");
    expect(pctSpan).not.toBeNull();
  });

  it("colors positive change green", () => {
    const { container } = render(
      <ExtHoursLine price={216.5} session="post" changePercent={0.6} />,
    );
    const pctSpan = container.querySelector("span.text-green-600");
    expect(pctSpan).not.toBeNull();
  });

  it("omits the percentage block when changePercent is null", () => {
    const { container } = render(
      <ExtHoursLine price={215.05} session="post" changePercent={null} />,
    );
    expect(container.textContent).toContain("AH");
    expect(container.textContent).toContain("$215.05");
    expect(container.textContent ?? "").not.toContain("%");
  });
});
