import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { createRequestId } from "../../services/api";
import {
  confirmReviewPolicy,
  deactivateReviewPolicy,
  reconcileReviewAccount,
  reviewPolicyInputSchema,
  reviewError,
  revisionFor,
  type ReviewSettings,
  type ReviewPolicyInput,
} from "../../services/decisionReviews";

/** No default: the user must explicitly choose whether the model may decide. */
function modelChoice(data: FormData): Partial<ReviewPolicyInput> {
  const mode = data.get("model_mode");
  if (mode === "disabled") return { model_decisions: "disabled" };
  if (mode !== "model") return {};
  const answer = (name: string) =>
    data.get(name) === "yes" ? true : data.get(name) === "no" ? false : null;
  return {
    model_decisions: "propose_for_human_review",
    model_may_open: answer("model_open"),
    model_may_exit: answer("model_exit"),
    model_acknowledgment:
      data.get("model_ack") === "on"
        ? "model-proposes-code-validates-human-decides-no-trade"
        : null,
  };
}

function ModelChoice() {
  const [mode, setMode] = useState("");
  const radio = (
    name: string,
    value: string,
    label: string,
    testId: string,
  ) => (
    <label className="mr-3">
      <input
        type="radio"
        name={name}
        value={value}
        required
        data-testid={testId}
        onChange={name === "model_mode" ? () => setMode(value) : undefined}
      />{" "}
      {label}
    </label>
  );
  return (
    <fieldset
      className="space-y-1 rounded border p-2"
      data-testid="review-model-choice"
    >
      <legend>Model investment decisions / 模型投资决策</legend>
      <div>
        {radio(
          "model_mode",
          "disabled",
          "Disabled / 不启用",
          "review-model-disabled",
        )}
        {radio(
          "model_mode",
          "model",
          "Model proposes, I approve / 模型建议，我审批",
          "review-model-enabled",
        )}
      </div>
      {mode === "model" && (
        <>
          <div>
            May open new positions / 允许建议新开仓:{" "}
            {radio("model_open", "yes", "Yes / 是", "review-model-open-yes")}
            {radio("model_open", "no", "No / 否", "review-model-open-no")}
          </div>
          <div>
            May propose full exits / 允许建议清仓:{" "}
            {radio("model_exit", "yes", "Yes / 是", "review-model-exit-yes")}
            {radio("model_exit", "no", "No / 否", "review-model-exit-no")}
          </div>
          <label className="block">
            <input
              type="checkbox"
              name="model_ack"
              required
              data-testid="review-model-ack"
            />{" "}
            The model gives explicit decisions; code checks limits and never
            resizes them; I decide; nothing is traded. /
            模型给出明确决策，代码校验且不改写，由我决定，不交易。
          </label>
        </>
      )}
    </fieldset>
  );
}

function PolicyForm({
  state,
  changed,
}: {
  state: ReviewSettings;
  changed: () => void;
}) {
  const [requestId] = useState(createRequestId);
  const [confirmed, setConfirmed] = useState(false);
  const [invalid, setInvalid] = useState(false);
  const save = useMutation({
    mutationFn: (policy: ReviewPolicyInput) =>
      confirmReviewPolicy(policy, revisionFor(state, requestId)),
    onSuccess: changed,
  });
  return (
    <form
      className="space-y-2 text-sm"
      data-testid="review-policy-form"
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        const parsed = reviewPolicyInputSchema.safeParse({
          risk_policy_revision: state.risk_policy_revision,
          strategy_version: state.strategy_version,
          allowed_symbols: String(data.get("symbols") ?? "")
            .toUpperCase()
            .split(/[\s,]+/)
            .filter(Boolean),
          max_account_sigma: Number(data.get("sigma")),
          lifetime_minutes: Number(data.get("lifetime")),
          acknowledged_contract: "manual-target-paper-review@1",
          instrument_attestation: "USD-US-nonfinancial-common-equities",
          evidence_acknowledgment: "forward-close-not-truth-or-historical-PIT",
          ...modelChoice(data),
        });
        if (
          !parsed.success ||
          !data.get("model_mode") ||
          (parsed.data.model_decisions === "propose_for_human_review" &&
            (parsed.data.model_may_open == null ||
              parsed.data.model_may_exit == null ||
              parsed.data.model_acknowledgment == null)) ||
          !confirmed ||
          data.get("instruments") !== "on" ||
          data.get("evidence") !== "on"
        ) {
          setInvalid(true);
          return;
        }
        setInvalid(false);
        save.mutate(parsed.data);
      }}
    >
      <p>
        Bound cost/risk revision / 绑定风险成本版本:{" "}
        {state.risk_policy_revision}
      </p>
      <p className="break-all text-xs">
        Strategy / 策略: {state.strategy_version}
      </p>
      <label className="block">
        Permitted targets and peers / 允许的研究目标与同行
        <input
          name="symbols"
          required
          data-testid="review-policy-symbols"
          defaultValue={state.policy?.policy.allowed_symbols.join(", ") ?? ""}
          className="ml-2 rounded border p-1"
        />
      </label>
      <label className="block">
        Maximum account sigma / 账户年化波动率上限 (fraction)
        <input
          name="sigma"
          type="number"
          min="0.000001"
          max="3"
          step="any"
          required
          data-testid="review-policy-sigma"
          defaultValue={state.policy?.policy.max_account_sigma ?? ""}
          className="ml-2 w-24 rounded border p-1"
        />
      </label>
      <label className="block">
        Evidence/proposal lifetime / 证据与提案最长有效分钟数
        <input
          name="lifetime"
          type="number"
          min="1"
          max="1440"
          step="1"
          required
          data-testid="review-policy-lifetime"
          defaultValue={state.policy?.policy.lifetime_minutes ?? ""}
          className="ml-2 w-24 rounded border p-1"
        />
      </label>
      <p>
        252-session fundamental pilot · USD · long-only · no borrowing. No
        automatic sizing or stance→BUY. Unfilled SELL proceeds cannot finance
        BUYs. / 不自动配仓，不以未成交卖出融资。
      </p>
      <p className="text-xs">
        Target-only sizing has no stop-loss plan or maximum-loss guarantee. The
        preview policy’s stop-risk budget is not applied without a stop; this
        gate uses account sigma and exposure/cash/turnover limits. /
        本版本不设置止损，不把预览止损预算当作最大亏损保证。
      </p>
      <ModelChoice />
      <label className="block">
        <input
          type="checkbox"
          name="instruments"
          required
          data-testid="review-instrument-ack"
        />{" "}
        I attest the targets and declared peers are USD US non-financial common
        equities. Provider labels alone do not prove this. /
        我核对上述标的范围。
      </label>
      <label className="block">
        <input
          type="checkbox"
          name="evidence"
          required
          data-testid="review-evidence-ack"
        />{" "}
        Forward daily-close references only. Typed matches/conditional estimates
        are not source truth, historical PIT, prose verification or guaranteed
        returns. / 理解数据与估值局限。
      </label>
      <label className="block">
        <input
          type="checkbox"
          checked={confirmed}
          data-testid="review-policy-ack"
          onChange={(e) => setConfirmed(e.target.checked)}
        />{" "}
        Confirm manual-target paper review only; no broker call or fill. /
        仅确认人工审阅政策，不执行交易。
      </label>
      <button
        type="submit"
        data-testid="confirm-review-policy"
        disabled={!confirmed || save.isPending}
        className="rounded border px-3 py-1 disabled:opacity-40"
      >
        Confirm review policy / 确认审阅政策
      </button>
      {(invalid || save.error) && (
        <p role="alert" className="text-red-700">
          {save.error
            ? reviewError(save.error)
            : "Explicit valid values and acknowledgments required / 请填写并确认所有字段"}
        </p>
      )}
    </form>
  );
}

export function ReviewPolicyPanel({
  state,
  changed,
}: {
  state: ReviewSettings;
  changed: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [inspected, setInspected] = useState(false);
  const disable = useMutation({
    mutationFn: () =>
      deactivateReviewPolicy(revisionFor(state, createRequestId())),
    onSuccess: changed,
  });
  const reconcile = useMutation({
    mutationFn: () =>
      reconcileReviewAccount(state, revisionFor(state, createRequestId())),
    onSuccess: () => {
      setInspected(false);
      changed();
    },
  });
  return (
    <div className="space-y-2 border-b pb-3" data-testid="review-policy-panel">
      <p className="break-all text-xs" data-testid="active-review-policy">
        {state.policy?.version_id ?? "Not confirmed / 尚未确认"}
      </p>
      <p className="text-xs">
        Revision {state.revision} · generation {state.generation} ·{" "}
        {state.reasons.join(" / ")}
      </p>
      <button
        className="rounded border px-2 py-1"
        onClick={() => setOpen((v) => !v)}
        data-testid="configure-review-policy"
      >
        Configure review policy / 配置审阅政策
      </button>
      {state.policy && (
        <button
          className="ml-2 rounded border px-2 py-1"
          disabled={disable.isPending}
          onClick={() => disable.mutate()}
        >
          Deactivate review policy / 停用
        </button>
      )}
      {open &&
        (state.strategy_version && state.risk_policy_revision > 0 ? (
          <PolicyForm
            key={`${state.revision}:${state.generation}`}
            state={state}
            changed={changed}
          />
        ) : (
          <p role="alert">
            Confirm risk costs and an active research strategy first /
            请先确认风险成本和研究契约
          </p>
        ))}
      {state.uncertain && (
        <div className="space-y-2 rounded border border-amber-500 p-2">
          <p>
            Account mutation failed; review is paused, not manual bookkeeping.
            Inspect holdings, transactions and declared cash before
            reconciliation. Abandoned in-flight writes require offline
            investigation; no force-unlock. /
            核对账户后才能恢复审阅，手动记账不受阻。
          </p>
          <label className="block">
            <input
              type="checkbox"
              checked={inspected}
              onChange={(e) => setInspected(e.target.checked)}
            />{" "}
            I inspected the declared account / 我已核对账户
          </label>
          <button
            disabled={!inspected || state.in_flight > 0 || reconcile.isPending}
            onClick={() => reconcile.mutate()}
            className="rounded border p-1 disabled:opacity-40"
          >
            Record reconciliation / 登记核对
          </button>
        </div>
      )}
      {(disable.error || reconcile.error) && (
        <p role="alert">{reviewError(disable.error ?? reconcile.error)}</p>
      )}
      <details>
        <summary>
          Immutable policy history / 政策历史 ({state.versions.length})
        </summary>
        {state.versions.map((version) => (
          <details key={version.version_id} className="text-xs">
            <summary className="break-all">{version.version_id}</summary>
            <pre className="overflow-auto">
              {JSON.stringify(version.policy, null, 2)}
            </pre>
          </details>
        ))}
      </details>
    </div>
  );
}
