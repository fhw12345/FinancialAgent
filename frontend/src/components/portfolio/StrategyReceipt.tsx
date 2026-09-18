/** Research horizons/model estimates remain distinct from execution prices and approval. */
import type { StrategySummary } from "../../services/researchStrategy";
export function StrategyReceipt({ summary }: { summary: StrategySummary }) {
  return (
    <section
      data-testid="strategy-receipt"
      className="my-3 rounded border p-3 text-sm space-y-3"
    >
      <h4 className="font-semibold">Strategy-bound research / 绑定研究契约</h4>
      <p className="text-amber-900">
        Conditional estimates, not verified fair values. No ready, portfolio
        action or execution. / 模型估计不是已验证公允价值
      </p>
      {summary.reviews.map((r) => (
        <article key={r.review_id} className="border-t pt-2">
          <strong>
            {r.symbol} · {r.status}
          </strong>
          <p data-testid="strategy-horizon">
            {r.contract.horizon} {r.contract.horizon_unit} ·{" "}
            {r.contract.benchmark}
          </p>
          <p className="break-all" data-testid="strategy-version">
            {r.contract.version_id}
          </p>
          <p>
            As of {r.as_of} · costs revision {r.contract.cost_policy_revision} ·
            fixed peers:{" "}
            {r.contract.parameters.peer_symbols.join(", ") || "none"}
          </p>
          {r.stale && (
            <p role="alert">
              Stale contract/costs; historical values were not recalculated. /
              已过期，请重新研究
            </p>
          )}
          {r.errors.map((e) => (
            <p key={e} className="text-red-700">
              {e}
            </p>
          ))}
          {r.valuations.map((v) => (
            <div
              key={v.method}
              data-testid="strategy-valuation"
              className="rounded border p-2 my-2"
            >
              <strong>
                {v.method}: {v.status}
              </strong>
              <p data-testid="strategy-value">
                {v.per_share_usd === null
                  ? "Unavailable / 不可用"
                  : `${v.per_share_usd.toFixed(2)} USD/share (conditional model estimate)`}
              </p>
              {v.peer_multiple !== null && (
                <p>
                  Peer median PE: {v.peer_multiple.toFixed(4)} ratio (annual,
                  not TTM)
                </p>
              )}
              {v.enterprise_value !== null && (
                <p>
                  Enterprise: {v.enterprise_value.toFixed(2)} USD · Equity:{" "}
                  {v.equity_value?.toFixed(2)} USD
                </p>
              )}
              {v.reasons.map((reason) => (
                <p key={reason} className="text-red-700">
                  {reason}
                </p>
              ))}
              <details>
                <summary>Inputs / assumptions / 输入与假设</summary>
                {Object.entries(v.assumptions).map(([key, val]) => (
                  <p key={key}>
                    {key}: {String(val)}
                  </p>
                ))}
                {v.inputs.map((i) => (
                  <p
                    key={`${i.snapshot_id}-${i.evidence_id}`}
                    className="break-all"
                  >
                    {i.symbol} · {i.metric}: {i.value} {i.unit} · {i.period}{" "}
                    {i.period_end} · {i.evidence_id}
                  </p>
                ))}
              </details>
            </div>
          ))}
          <h5 className="font-medium">
            Invalidation / monitoring / 失效与复核条件
          </h5>
          <ul>
            {r.monitoring.map((rule) => (
              <li key={rule}>{rule}</li>
            ))}
          </ul>
          {r.checks.map((check) => (
            <p key={check.rule} data-testid="strategy-monitoring-check">
              {check.rule}: {check.status} · value {check.value ?? "unknown"} /
              threshold {check.threshold} · {check.reason}
            </p>
          ))}
          {r.conclusion && (
            <div data-testid="strategy-conclusion">
              <p>
                Investment stance: {r.conclusion.stance} · Portfolio action:
                none · Execution intent: none
              </p>
              {r.conclusion.theses.map((thesis, index) => (
                <p key={index}>
                  Unverified thesis: {thesis.text} · monitor{" "}
                  {thesis.monitoring_rule}
                </p>
              ))}
              {r.conclusion.scenarios.map((s) => (
                <p key={s.scenario}>
                  {s.scenario}: {s.condition} · probability: not estimated
                </p>
              ))}
            </div>
          )}
        </article>
      ))}
    </section>
  );
}
