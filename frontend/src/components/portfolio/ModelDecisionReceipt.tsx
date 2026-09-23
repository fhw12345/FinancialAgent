import type { ModelDecisionRecord } from "../../services/modelDecisionSchema";
const labels: Record<string, string> = {
  BUY: "BUY / 建仓",
  ADD: "ADD / 增持",
  REDUCE: "REDUCE / 减仓",
  SELL: "SELL / 清仓",
  HOLD: "HOLD / WAIT · 维持",
};
const pct = (value: number | null) =>
  value === null ? "unchanged / 不变" : `${(value * 100).toFixed(2)}%`;
export function ModelDecisionReceipt({
  record,
}: {
  record: ModelDecisionRecord;
}) {
  return (
    <div
      data-testid="model-decision"
      data-status={record.status}
      className="space-y-2 rounded border border-indigo-300 p-2 text-sm"
    >
      <p className="font-semibold">
        Model recommendation / 模型投资决策（建议）· {record.status}
      </p>
      <p className="text-xs text-gray-600">
        {record.provenance
          ? `${record.provenance.model} · ${record.provenance.prompt} · ${record.provenance.provider}`
          : "No model output recorded"}{" "}
        · {record.created_at.slice(0, 19)}
      </p>
      {record.error_code && (
        <p role="alert" className="text-red-700">
          Model call failed / 调用失败: {record.error_code}
        </p>
      )}
      {record.output?.decisions.map((d) => (
        <div
          key={d.symbol}
          data-testid={`model-decision-${d.symbol}`}
          data-action={d.action}
          className="border-t pt-1"
        >
          <p>
            <strong className="font-mono">{d.symbol}</strong> ·{" "}
            <strong>{labels[d.action] ?? d.action}</strong> · target / 目标仓位{" "}
            {pct(d.target_weight)}
          </p>
          <p>{d.rationale}</p>
          {d.key_risks.length > 0 && (
            <p className="text-xs">Risks / 风险: {d.key_risks.join("; ")}</p>
          )}
          {d.review_triggers.length > 0 && (
            <p className="text-xs">
              Re-evaluate when / 重新评估条件: {d.review_triggers.join("; ")}
            </p>
          )}
          <p className="break-all text-xs text-gray-500">
            Evidence / 证据: {d.evidence_ids.join(", ") || "none / 无"}
          </p>
        </div>
      ))}
      {record.output && (
        <p className="text-xs">
          Summary / 总结: {record.output.portfolio_summary}
        </p>
      )}
      <p className="text-xs text-amber-900">
        Recommendation only. Code checks every limit and never resizes it; you
        decide. No order or simulated fill. /
        仅为建议：代码校验但不改写，由你决定，不下单。
      </p>
    </div>
  );
}
