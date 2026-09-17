import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { RiskReceipt } from "../RiskReceipt";
import { riskSchema } from "../../../services/portfolioRisk";
afterEach(cleanup);
const base = {
  snapshot: {
    snapshot_id: "risk_fixture",
    calculator_version: "idq-002@1",
    account_scope: "local_holdings",
    account_revision: "one",
    session_date: "2026-09-16",
    captured_at: "2026-09-16T21:00:00Z",
    cash: 9000,
    policy: { revision: 0, policy: null, confirmed_at: null },
  },
  current: {
    status: "complete",
    equity: 10000,
    cash_weight: 0.9,
    account_sigma_annualized: 0.032016944666,
    invested_sigma_annualized: 0.32016944666,
    invested_hhi: 1,
    beta_exposure: 0.1,
    position_weights: { AAPL: 0.1 },
    sector_weights: { Technology: 0.1 },
    common_sessions: [],
    history_equity_coverage: 1,
    exclusions: {},
    errors: [],
    assumptions: ["Cash volatility assumed zero."],
  },
  allocation: null,
  stale: false,
  stale_reasons: [],
};
it("keeps account and invested denominators visibly separate", () => {
  render(<RiskReceipt review={riskSchema.parse(base)} />);
  expect(screen.getByTestId("account-sigma")).toHaveTextContent("3.2017%");
  expect(screen.getByTestId("invested-sigma")).toHaveTextContent("32.0169%");
  expect(screen.getByTestId("invested-hhi")).toHaveTextContent("1.0000");
});
it("missing risk remains unavailable rather than zero and stale is explicit", () => {
  const r = riskSchema.parse({
    ...base,
    current: {
      ...base.current,
      status: "unavailable",
      account_sigma_annualized: null,
    },
    stale: true,
    stale_reasons: ["ACCOUNT_CHANGED"],
  });
  render(<RiskReceipt review={r} />);
  expect(screen.getByTestId("account-sigma")).toHaveTextContent("Unavailable");
  expect(screen.getByRole("alert")).toHaveTextContent("ACCOUNT_CHANGED");
});
it("a purported executable allocation cannot cross the API schema", () => {
  expect(
    riskSchema.safeParse({
      ...base,
      allocation: {
        actionable: true,
        status: "feasible_preview",
        constraints: [],
        proposed: null,
        turnover: 0,
        posttrade_cash: 9000,
        cash_without_unfilled_sales: 9000,
        changes: [],
      },
    }).success,
  ).toBe(false);
});
