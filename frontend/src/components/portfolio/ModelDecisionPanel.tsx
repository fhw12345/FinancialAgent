import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createRequestId } from "../../services/api";
import {
  reviewError,
  revisionFor,
  type ReviewSettings,
} from "../../services/decisionReviews";
import {
  getModelDecisions,
  requestModelDecision,
  revalidateModelDecision,
} from "../../services/modelDecisions";
import type { DecisionAssessment } from "../../services/decisionAssessments";
import { ModelDecisionReceipt } from "./ModelDecisionReceipt";

export function ModelDecisionPanel({
  source,
  state,
}: {
  source: DecisionAssessment | undefined;
  state: ReviewSettings;
}) {
  const client = useQueryClient();
  const [confirmed, setConfirmed] = useState(false);
  const [requestId, setRequestId] = useState(createRequestId);
  const history = useQuery({
    queryKey: ["review", "model-decisions"],
    queryFn: ({ signal }) => getModelDecisions(signal),
    refetchInterval: 5000,
  });
  const changed = () => {
    setConfirmed(false);
    setRequestId(createRequestId());
    void client.invalidateQueries({ queryKey: ["review"] });
  };
  const decide = useMutation({
    mutationFn: () =>
      requestModelDecision(
        revisionFor(state, requestId),
        source?.assessment_id ?? "",
      ),
    onSettled: changed,
  });
  const revalidate = useMutation({
    mutationFn: (id: string) =>
      revalidateModelDecision(id, revisionFor(state, createRequestId())),
    onSettled: changed,
  });
  const enabled =
    state.policy?.policy.model_decisions === "propose_for_human_review";
  return (
    <div
      className="space-y-2 rounded border p-3"
      data-testid="model-decision-panel"
    >
      <h4 className="font-semibold">
        Model investment decision / 模型投资决策
      </h4>
      {!enabled && (
        <p className="text-sm">
          Enable model decisions in the review policy first. /
          请先在审阅政策中启用模型决策。
        </p>
      )}
      {enabled && !source && (
        <p className="text-sm">
          Select a completed research source above. / 请先选择研究来源。
        </p>
      )}
      {enabled && source && (
        <form
          className="space-y-2 text-sm"
          onSubmit={(event) => {
            event.preventDefault();
            if (confirmed) decide.mutate();
          }}
        >
          <p>
            The model decides BUY/ADD/REDUCE/SELL/HOLD and a target weight for:{" "}
            <span className="font-mono">
              {source.results
                .map((r) => r.symbol)
                .filter((s) => state.policy?.policy.allowed_symbols.includes(s))
                .join(", ")}
            </span>
            . / 模型将为这些股票给出明确动作与目标仓位。
          </p>
          <label className="block">
            <input
              type="checkbox"
              data-testid="model-decision-ack"
              checked={confirmed}
              disabled={decide.isPending}
              onChange={(e) => setConfirmed(e.target.checked)}
            />{" "}
            Make one paid model call now. The result is a recommendation that I
            review; nothing is traded. /
            立即调用一次模型（消耗额度）；结果仅供我审阅，不交易。
          </label>
          <button
            type="submit"
            data-testid="request-model-decision"
            disabled={
              !confirmed ||
              decide.isPending ||
              state.in_flight > 0 ||
              state.uncertain
            }
            className="rounded border border-indigo-700 px-3 py-1 disabled:opacity-40"
          >
            {decide.isPending
              ? "Model deciding… / 模型决策中…"
              : "Get model decision / 获取模型决策"}
          </button>
          {decide.error && (
            <p
              role="alert"
              data-testid="model-decision-error"
              className="text-red-700"
            >
              {reviewError(decide.error)}
            </p>
          )}
        </form>
      )}
      {history.data?.map((view) => (
        <div key={view.record.decision_id} className="space-y-1">
          <ModelDecisionReceipt record={view.record} />
          {view.review ? (
            <p className="text-xs" data-testid="model-decision-review-state">
              Review / 校验: {view.review.readiness} · {view.review.lifecycle}
              {view.review.reasons.length > 0 &&
                ` · ${view.review.reasons.map((r) => r.code).join(", ")}`}{" "}
              (see batch below / 见下方批次)
            </p>
          ) : (
            view.record.status === "completed" && (
              <div className="text-xs">
                <p>{view.review_error ?? "Not yet validated / 尚未校验"}</p>
                <button
                  type="button"
                  className="rounded border px-2 py-1"
                  disabled={revalidate.isPending}
                  onClick={() => revalidate.mutate(view.record.decision_id)}
                >
                  Re-validate stored decision (no model call) /
                  重新校验（不再调用模型）
                </button>
              </div>
            )
          )}
        </div>
      ))}
      {revalidate.error && <p role="alert">{reviewError(revalidate.error)}</p>}
    </div>
  );
}
