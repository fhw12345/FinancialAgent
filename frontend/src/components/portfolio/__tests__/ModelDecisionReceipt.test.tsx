import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { ModelDecisionReceipt } from "../ModelDecisionReceipt";
import { modelDecisionRecordSchema } from "../../../services/modelDecisionSchema";
afterEach(cleanup);
const record = {
  schema_version: 1,
  decision_id: "model_decision_x",
  request_id: "request-1",
  assessment_id: "assessment_" + "a".repeat(32),
  policy_version_id: "review_policy_x",
  scope: ["AAPL", "MSFT"],
  status: "completed",
  created_at: "2026-09-22T12:00:00Z",
  completed_at: "2026-09-22T12:00:05Z",
  provenance: {
    prompt: "portfolio-model-decision@1",
    role: "portfolio_decisions",
    provider: "github_copilot",
    model: "gpt-6-astra",
    api: "openai-responses",
    routing_revision: 1,
  },
  output: {
    decisions: [
      {
        symbol: "AAPL",
        action: "ADD",
        target_weight: 0.18,
        rationale: "Cash flow supports adding",
        evidence_ids: ["ev_1"],
        key_risks: ["Growth slows"],
        review_triggers: ["EPS falls"],
      },
      {
        symbol: "MSFT",
        action: "HOLD",
        target_weight: null,
        rationale: "Evidence mixed",
        evidence_ids: [],
        key_risks: [],
        review_triggers: [],
      },
    ],
    portfolio_summary: "Add AAPL, wait on MSFT",
  },
  error_code: null,
  executable: false,
};
it("shows explicit actions and targets as a recommendation, never an order", () => {
  render(
    <ModelDecisionReceipt record={modelDecisionRecordSchema.parse(record)} />,
  );
  expect(screen.getByTestId("model-decision-AAPL")).toHaveAttribute(
    "data-action",
    "ADD",
  );
  expect(screen.getByTestId("model-decision-AAPL")).toHaveTextContent("18.00%");
  expect(screen.getByTestId("model-decision-MSFT")).toHaveTextContent(
    "unchanged",
  );
  expect(screen.getByTestId("model-decision")).toHaveTextContent("gpt-6-astra");
  expect(screen.getByTestId("model-decision")).toHaveTextContent("No order");
  expect(screen.queryByRole("button")).toBeNull();
});
it("the wire contract cannot mark a model decision executable", () => {
  expect(
    modelDecisionRecordSchema.safeParse({ ...record, executable: true })
      .success,
  ).toBe(false);
});
