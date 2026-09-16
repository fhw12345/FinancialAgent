import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  listAssessments,
  getAssessment,
  type DecisionAssessment,
} from "../../services/decisionAssessments";
import { AssistantMarkdown } from "../chat/AssistantMarkdown";
import { getRecordValue } from "../../utils/safeRecord";

const labels = {
  research_only: ["仅研究", "Research only"],
  insufficient_evidence: ["证据不足", "Insufficient evidence"],
  needs_review: ["需要复核", "Needs review"],
  blocked: ["已阻断", "Blocked"],
};

export default function DecisionAssessments({
  symbol,
  source,
}: {
  symbol?: string;
  source?: string;
}) {
  const { i18n } = useTranslation();
  const zh = i18n.language.startsWith("zh");
  const query = useQuery({
    queryKey: ["decision-assessments", symbol, source],
    queryFn: ({ signal }) => listAssessments(symbol, source, signal),
    refetchInterval: 5000,
  });
  const [selected, setSelected] = useState<string | null>(null);
  const detail = useQuery({
    queryKey: ["decision-assessment", selected],
    queryFn: ({ signal }) => getAssessment(selected ?? "", signal),
    enabled: selected !== null,
    refetchInterval: 5000,
  });
  const label = (state: DecisionAssessment["readiness"]) =>
    getRecordValue(labels, state)?.at(zh ? 0 : 1) ?? state;
  return (
    <section className="border-b p-4" data-testid="decision-assessments">
      <h3 className="font-semibold">
        {zh
          ? "研究安全评估 · Stage A"
          : "Research safety assessments · Stage A"}
      </h3>
      <p
        className="my-2 text-sm text-amber-900"
        data-testid="assessment-stage-a-notice"
      >
        {zh
          ? "当前仅提供非行动性研究记录。政策、证据、组合风控和策略门禁尚未接齐，因此没有 ready、批准或执行资格。"
          : "Non-actionable research only. Policy, evidence, portfolio-risk and strategy gates are not integrated: no ready, approval or execution eligibility."}
      </p>
      {query.isLoading && (
        <p role="status">{zh ? "加载评估…" : "Loading assessments…"}</p>
      )}
      {query.error && (
        <p role="alert" className="text-red-700">
          {zh
            ? "无法读取评估；不代表没有风险。"
            : "Assessment unavailable; this does not mean no risk."}
        </p>
      )}
      {query.data?.length === 0 && (
        <p className="text-sm text-gray-500">
          {zh
            ? "尚无评估。运行研究后会记录结果及缺失项。"
            : "No assessments yet. Research runs record their results and missing checks here."}
        </p>
      )}
      <div className="space-y-3">
        {query.data?.map((batch) => (
          <article
            key={batch.assessment_id}
            className="rounded border p-3"
            data-testid="assessment-batch"
            data-readiness={batch.readiness}
            data-actionable="false"
          >
            <div className="flex flex-wrap justify-between gap-2 text-sm">
              <strong>{label(batch.readiness)}</strong>
              <span>
                {batch.source} · {batch.created_at.slice(0, 10)} ·{" "}
                {batch.run_status ?? "standalone"}
              </span>
            </div>
            {batch.results.map((item) => (
              <div
                key={item.symbol}
                className="mt-2 border-t pt-2"
                data-testid={`assessment-symbol-${item.symbol}`}
                data-readiness={item.readiness}
              >
                <span className="font-mono font-medium">{item.symbol}</span> ·{" "}
                <span>{label(item.readiness)}</span>
                {item.proposal && (
                  <p className="mt-1 text-xs text-gray-600">
                    {zh
                      ? "模型草稿（不是建议）："
                      : "Model draft (not a recommendation): "}
                    {item.proposal.proposed_action} · {item.exposure_context}
                  </p>
                )}
                <ul className="mt-1 space-y-1 text-xs text-gray-600">
                  {item.reasons.map((reason) => (
                    <li key={reason.code}>
                      <code>{reason.code}</code> — {reason.message}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            <div className="mt-3 flex gap-3">
              <button
                type="button"
                className="rounded border px-2 py-1 text-sm"
                onClick={() => setSelected(batch.assessment_id)}
              >
                {zh ? "查看研究 / 草稿" : "View research / draft"}
              </button>
              <span
                className="text-sm text-amber-800"
                data-testid="assessment-not-approvable"
              >
                {zh ? "不可批准 / 不可执行" : "Not approvable / not executable"}
              </span>
            </div>
          </article>
        ))}
      </div>
      {selected && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
        >
          <div className="max-h-[80vh] w-full max-w-3xl overflow-auto rounded bg-white p-5">
            <button
              type="button"
              onClick={() => setSelected(null)}
              className="float-right rounded border px-3 py-1"
            >
              {zh ? "关闭" : "Close"}
            </button>
            <h3 className="mb-4 font-semibold">
              {zh ? "非行动性研究记录" : "Non-actionable research record"}
            </h3>
            {detail.isLoading && <p role="status">Loading…</p>}
            {detail.error && (
              <p role="alert">
                {zh ? "读取失败，请重试。" : "Unable to load research."}
              </p>
            )}
            {detail.data?.results.map((item) => (
              <section key={item.symbol} className="mt-4 border-t pt-3">
                <h4 className="font-mono font-semibold">
                  {item.symbol} · {label(item.readiness)}
                </h4>
                {item.proposal && (
                  <p className="my-2 text-sm">
                    {zh ? "未验证模型草稿：" : "Unverified model draft: "}
                    {item.proposal.proposed_action} — {item.proposal.reasoning}
                  </p>
                )}
                <AssistantMarkdown>
                  {item.research ||
                    (zh ? "没有可用研究" : "No research available")}
                </AssistantMarkdown>
              </section>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
