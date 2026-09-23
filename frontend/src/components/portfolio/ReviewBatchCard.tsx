import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { createRequestId } from "../../services/api";
import {
  approveReview,
  cancelReview,
  reviewError,
  type ReviewView,
} from "../../services/decisionReviews";
import { RiskReceipt } from "./RiskReceipt";

function ApprovalForm({
  view,
  changed,
}: {
  view: ReviewView;
  changed: () => void;
}) {
  const [selected, setSelected] = useState(() =>
    view.batch.trades
      .filter((t) => t.delta_quantity !== 0)
      .map((t) => t.symbol),
  );
  const [confirmed, setConfirmed] = useState(false);
  const [requestId, setRequestId] = useState(createRequestId);
  const approve = useMutation({
    mutationFn: () =>
      approveReview(view.batch.batch_id, {
        expected_revision: view.control_revision,
        expected_generation: view.control_generation,
        request_id: requestId,
        symbols: selected,
        confirm: true,
        acknowledgment: "review-only-no-real-or-paper-fill",
      }),
    onSuccess: changed,
  });
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (confirmed && selected.length) approve.mutate();
      }}
      className="mt-3 space-y-2 border-t pt-2"
    >
      <p className="text-sm">
        Approve only the checked subset; all constraints are recomputed. /
        仅批准勾选子集，重新校验所有限制。
      </p>
      {view.batch.trades
        .filter((t) => t.delta_quantity !== 0)
        .map((trade) => (
          <label key={trade.symbol} className="mr-4 inline-block">
            <input
              type="checkbox"
              data-testid={`approve-symbol-${trade.symbol}`}
              checked={selected.includes(trade.symbol)}
              disabled={approve.isPending}
              onChange={(event) => {
                const checked = event.target.checked;
                setSelected((old) =>
                  checked
                    ? [...old, trade.symbol]
                    : old.filter((s) => s !== trade.symbol),
                );
                setConfirmed(false);
                setRequestId(createRequestId());
              }}
            />{" "}
            {trade.symbol} {trade.action} {trade.delta_quantity}
          </label>
        ))}
      <label className="block text-sm">
        <input
          type="checkbox"
          checked={confirmed}
          disabled={approve.isPending}
          data-testid="approve-review-ack"
          onChange={(e) => setConfirmed(e.target.checked)}
        />{" "}
        I reviewed this subset and its limits. This records human paper-review
        approval only, no real or simulated fill. /
        我已审阅子集与限制；仅登记批准，不修改真实账户，也不模拟成交。
      </label>
      <button
        data-testid="approve-review"
        disabled={!confirmed || !selected.length || approve.isPending}
        className="rounded border border-emerald-700 px-3 py-1 disabled:opacity-40"
      >
        Approve paper review / 批准人工审阅
      </button>
      {approve.error && (
        <p
          role="alert"
          data-testid="review-approval-error"
          className="text-red-700"
        >
          {reviewError(approve.error)}
        </p>
      )}
    </form>
  );
}

export function ReviewBatchCard({
  view,
  changed,
}: {
  view: ReviewView;
  changed: () => void;
}) {
  const cancel = useMutation({
    mutationFn: () =>
      cancelReview(view.batch.batch_id, {
        expected_revision: view.control_revision,
        expected_generation: view.control_generation,
        request_id: createRequestId(),
      }),
    onSuccess: changed,
  });
  return (
    <article
      data-testid="review-batch"
      data-readiness={view.readiness}
      data-lifecycle={view.lifecycle}
      data-executable="false"
      className="space-y-2 rounded border p-3"
    >
      <h4 className="font-semibold">
        {view.readiness} · {view.lifecycle}
      </h4>
      <p className="text-sm">
        Ready = eligible for defined human paper review, not a good-investment
        certificate. / ready 仅表示符合既定人工审阅规则，不保证投资质量。
      </p>
      <p className="break-all text-xs">{view.batch.batch_id}</p>
      <p className="text-xs">
        Expires / 到期: {view.batch.expires_at} · idq-001-b@1
      </p>
      <p className="text-xs">Source / 研究: {view.batch.run_id ?? "missing"}</p>
      {view.reasons.map((reason, index) => (
        <p
          key={`${reason.code}:${reason.symbol}:${index}`}
          data-testid="review-gate-reason"
          className="text-sm text-amber-900"
        >
          <code>{reason.code}</code> {reason.symbol}
        </p>
      ))}
      {view.batch.trades.map((trade) => (
        <p
          key={trade.symbol}
          className="text-sm"
          data-testid={`review-trade-${trade.symbol}`}
        >
          {trade.symbol} ·{" "}
          {trade.action === "HOLD" && trade.exposure === "flat"
            ? "WAIT"
            : trade.action}{" "}
          · {trade.intent} · Δ {trade.delta_quantity} shares · close reference $
          {trade.reference_price} (not an execution price / 不是成交价)
        </p>
      ))}
      <details>
        <summary>Account/constraint receipt / 账户与限制回执</summary>
        {view.batch.risk && <RiskReceipt review={view.batch.risk} />}
      </details>
      {view.batch.model_decision && (
        <p className="text-sm" data-testid="batch-model-decision">
          Source: model recommendation / 来源：模型决策{" "}
          <span className="break-all text-xs">
            {view.batch.model_decision.decision_id}
          </span>
        </p>
      )}
      <details>
        <summary>Sealed source and policy IDs / 证据与政策版本</summary>
        <p className="break-all text-xs">{view.batch.policy?.version_id}</p>
        {view.batch.proofs.map((proof) => (
          <div key={proof.symbol} className="break-all text-xs">
            <p>
              {proof.symbol}: {proof.snapshot_id}
            </p>
            <p>{proof.dossier_id}</p>
            <p>{proof.strategy_review_id}</p>
            <p>Unverified / 未认证: {proof.unverified_context.join(", ")}</p>
            <p>
              {Object.entries(proof.monitoring)
                .map(([rule, result]) => `${rule}: ${result}`)
                .join("; ")}
            </p>
          </div>
        ))}
      </details>
      {view.approval && (
        <div
          data-testid="review-approved"
          data-current={String(view.approval_current)}
          className="rounded border border-emerald-600 p-2 text-sm"
        >
          <strong>Human review recorded / 人工审阅已登记</strong>
          <p>
            {view.approval_current
              ? "Currently valid / 当前有效"
              : "Historical only — stale, superseded or cancelled / 仅历史记录，已失效"}
          </p>
          <p>
            Approved subset / 已批准子集:{" "}
            {view.approval.request.symbols.join(", ")}
          </p>
          <p>
            No account mutation, broker call, paper fill or measured return. /
            未修改账户、下单或模拟成交。
          </p>
          <p className="break-all text-xs">{view.approval.approval_id}</p>
          <details>
            <summary>Approved subset receipt / 批准子集回执</summary>
            {view.approval_receipt?.evaluation.risk && (
              <RiskReceipt review={view.approval_receipt.evaluation.risk} />
            )}
          </details>
        </div>
      )}
      {view.approvable && (
        <ApprovalForm
          key={`${view.control_revision}:${view.control_generation}`}
          view={view}
          changed={changed}
        />
      )}
      {(view.lifecycle === "current" || view.lifecycle === "approved") && (
        <button
          className="rounded border px-2 py-1 text-sm"
          disabled={cancel.isPending}
          onClick={() => cancel.mutate()}
        >
          Cancel / withdraw review · 取消或撤回
        </button>
      )}
      {cancel.error && <p role="alert">{reviewError(cancel.error)}</p>}
    </article>
  );
}
