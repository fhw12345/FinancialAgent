import { describe, expect, it } from "vitest";
import { assessmentSchema } from "../decisionAssessments";
const record = {
  schema_version: 1,
  policy_version: "idq-001-a@1",
  assessment_id: "assessment_fixture",
  run_id: null,
  source: "holdings",
  created_at: "2026-09-16T00:00:00Z",
  readiness: "research_only",
  actionable: false,
  action: null,
  run_status: null,
  results: [],
};
describe("Stage A response boundary", () => {
  it("accepts research-only, never a ready action", () => {
    expect(assessmentSchema.safeParse(record).success).toBe(true);
    expect(
      assessmentSchema.safeParse({ ...record, readiness: "ready" }).success,
    ).toBe(false);
    expect(
      assessmentSchema.safeParse({ ...record, actionable: true }).success,
    ).toBe(false);
    expect(
      assessmentSchema.safeParse({ ...record, action: "BUY" }).success,
    ).toBe(false);
  });
  it("rejects a nested symbol action even if the batch is non-actionable", () => {
    const result = {
      symbol: "AAPL",
      readiness: "research_only",
      actionable: true,
      action: null,
      proposal: null,
      research: "Recorded",
      research_truncated: false,
      exposure_context: "held",
      reasons: [],
    };
    expect(
      assessmentSchema.safeParse({ ...record, results: [result] }).success,
    ).toBe(false);
    expect(
      assessmentSchema.safeParse({
        ...record,
        results: [{ ...result, actionable: false }],
      }).success,
    ).toBe(true);
  });
});
