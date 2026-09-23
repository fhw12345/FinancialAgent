import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createRequestId } from "../../services/api";
import {
  listAssessments,
  type DecisionAssessment,
} from "../../services/decisionAssessments";
import {
  getReviewSettings,
  getReviewBatches,
  proposeReview,
  reviewTargetSchema,
  reviewError,
  revisionFor,
  type ReviewTarget,
  type ReviewSettings,
} from "../../services/decisionReviews";
import { ReviewPolicyPanel } from "./ReviewPolicyPanel";
import { ReviewBatchCard } from "./ReviewBatchCard";
import { ModelDecisionPanel } from "./ModelDecisionPanel";

function TargetForm({
  source,
  state,
  changed,
}: {
  source: DecisionAssessment;
  state: ReviewSettings;
  changed: () => void;
}) {
  const [requestId] = useState(createRequestId);
  const [invalid, setInvalid] = useState(false);
  const create = useMutation({
    mutationFn: (targets: ReviewTarget[]) =>
      proposeReview({
        ...revisionFor(state, requestId),
        assessment_id: source.assessment_id,
        targets,
      }),
    onSuccess: changed,
  });
  return (
    <form
      className="space-y-2 text-sm"
      data-testid="review-target-form"
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        const parsed = reviewTargetSchema
          .array()
          .min(1)
          .max(20)
          .safeParse(
            source.results
              .filter((row) => String(data.get(row.symbol) ?? "").trim() !== "")
              .map((row) => ({
                symbol: row.symbol,
                target_weight: Number(data.get(row.symbol)),
              })),
          );
        if (!parsed.success) {
          setInvalid(true);
          return;
        }
        setInvalid(false);
        create.mutate(parsed.data);
      }}
    >
      <p>
        Enter account-equity target fractions yourself. Blank = omitted; 0 =
        request exit, still subject to gates. No confidence sizing or inferred
        target. / 手动填写目标权重比例；留空不纳入，0 为退出请求，仍需校验。
      </p>
      {source.results.map((row) => (
        <label key={row.symbol} className="block">
          {row.symbol} target weight / 目标权重
          <input
            name={row.symbol}
            data-testid={`review-target-${row.symbol}`}
            type="number"
            step="any"
            min="0"
            max="1"
            className="ml-2 w-24 rounded border p-1"
          />
        </label>
      ))}
      <button
        type="submit"
        data-testid="prepare-review"
        className="rounded border px-3 py-1 disabled:opacity-40"
        disabled={create.isPending || state.in_flight > 0 || state.uncertain}
      >
        Validate target proposal / 校验权重提案
      </button>
      <p className="text-xs">
        Explicit validation refreshes market inputs, but never calls a model or
        submits a trade. / 校验会读取市场数据，不调用模型或下单。
      </p>
      {(invalid || create.error) && (
        <p role="alert" className="text-red-700">
          {create.error
            ? reviewError(create.error)
            : "Enter 1–20 finite target weights / 请填写有效权重"}
        </p>
      )}
    </form>
  );
}

export function PaperReviewPanel() {
  const client = useQueryClient();
  const [selected, setSelected] = useState("");
  const state = useQuery({
    queryKey: ["review", "settings"],
    queryFn: ({ signal }) => getReviewSettings(signal),
    refetchInterval: 5000,
  });
  const batches = useQuery({
    queryKey: ["review", "batches"],
    queryFn: ({ signal }) => getReviewBatches(signal),
    refetchInterval: 5000,
  });
  const sources = useQuery({
    queryKey: ["decision-assessments", undefined, undefined],
    queryFn: ({ signal }) => listAssessments(undefined, undefined, signal),
    refetchInterval: 5000,
  });
  const changed = () => {
    void client.invalidateQueries({ queryKey: ["review"] });
  };
  const source = sources.data?.find(
    (record) => record.assessment_id === selected,
  );
  return (
    <section
      className="space-y-3 border-b p-4"
      data-testid="paper-review-panel"
    >
      <h3 className="font-semibold">
        Model decisions, manual targets & paper review /
        模型决策、人工目标与审阅
      </h3>
      <p className="text-sm text-amber-900">
        Research stance ≠ proposal ≠ human approval ≠ fill. Nothing here changes
        real holdings/cash or creates a paper trade. /
        研究倾向、提案、人工批准和成交是不同记录；这里不交易，也不模拟成交。
      </p>
      {(state.isLoading || batches.isLoading) && (
        <p role="status">Loading review state / 加载审阅状态…</p>
      )}
      {(state.error || batches.error || sources.error) && (
        <p role="alert">
          Review/source unavailable; no permission implied. /
          读取失败，不代表符合批准条件。
        </p>
      )}
      {state.data && <ReviewPolicyPanel state={state.data} changed={changed} />}
      <p className="text-xs text-gray-600">
        Older/Deep records without a positive consistency-check receipt are not
        upgraded. Run fresh Portfolio research explicitly before proposing. /
        缺少明确检查通过记录的旧研究或 Deep 结果不会自动升级；请主动运行新的
        Portfolio 研究。
      </p>
      <label className="block text-sm">
        Research source / 选择研究来源
        <select
          value={selected}
          data-testid="review-source"
          onChange={(event) => setSelected(event.target.value)}
          className="ml-2 max-w-full rounded border p-1"
        >
          <option value="">Select explicitly / 请明确选择</option>
          {sources.data?.map((record) => (
            <option key={record.assessment_id} value={record.assessment_id}>
              {record.results.map((r) => r.symbol).join(", ")} ·{" "}
              {record.created_at.slice(0, 19)} ·{" "}
              {record.run_status ?? "unverified"}
            </option>
          ))}
        </select>
      </label>
      {state.data && <ModelDecisionPanel source={source} state={state.data} />}
      {source && state.data && (
        <TargetForm
          key={`${source.assessment_id}:${state.data.revision}:${state.data.generation}`}
          source={source}
          state={state.data}
          changed={changed}
        />
      )}
      {batches.data?.map((view) => (
        <ReviewBatchCard
          key={view.batch.batch_id}
          view={view}
          changed={changed}
        />
      ))}
    </section>
  );
}
