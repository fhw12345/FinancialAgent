/** Current/proposed risk are diagnostics, not permission to act. */
import type { RiskReview } from "../../services/portfolioRisk";
const pct = (value: number | null) =>
  value === null ? "Unavailable" : `${(value * 100).toFixed(4)}%`;
export function RiskReceipt({ review }: { review: RiskReview }) {
  return (
    <section
      data-testid="risk-receipt"
      className="space-y-2 rounded border p-3 text-sm"
    >
      <h4 className="font-semibold">
        Account risk / 账户风险 · {review.snapshot.session_date}
      </h4>
      <p className="text-xs text-gray-600">
        USD · local holdings · {review.snapshot.calculator_version} · policy
        revision {review.snapshot.policy.revision}
      </p>
      {review.stale && (
        <p role="alert" className="text-red-700">
          Stale / 已过期: {review.stale_reasons.join(", ")} — refresh before
          comparing.
        </p>
      )}
      <p data-testid="risk-availability">{review.current.status}</p>
      <dl className="grid grid-cols-2 gap-1">
        <dt>Equity / 总权益</dt>
        <dd data-testid="risk-equity">
          {review.current.equity === null
            ? "Unavailable"
            : `$${review.current.equity.toFixed(2)}`}
        </dd>
        <dt>Cash weight / 现金权重</dt>
        <dd>{pct(review.current.cash_weight)}</dd>
        <dt>Account σ / 账户波动率</dt>
        <dd data-testid="account-sigma">
          {pct(review.current.account_sigma_annualized)}
        </dd>
        <dt>Invested σ / 股票部分波动率</dt>
        <dd data-testid="invested-sigma">
          {pct(review.current.invested_sigma_annualized)}
        </dd>
        <dt>Invested HHI / 股票集中度</dt>
        <dd data-testid="invested-hhi">
          {review.current.invested_hhi?.toFixed(4) ?? "Unavailable"}
        </dd>
        <dt>Beta / 基准敏感度</dt>
        <dd>{review.current.beta_exposure?.toFixed(4) ?? "Unavailable"}</dd>
        <dt>Common sessions / 共同交易日</dt>
        <dd>{review.current.common_sessions.length}</dd>
        <dt>History equity coverage / 数据覆盖</dt>
        <dd>{pct(review.current.history_equity_coverage)}</dd>
      </dl>
      {Object.entries(review.current.exclusions).map(([symbol, reasons]) => (
        <p key={symbol} className="text-red-700">
          {symbol}: {reasons.join(", ")}
        </p>
      ))}
      {review.current.errors.map((e) => (
        <p key={e} className="text-red-700">
          {e}
        </p>
      ))}
      <p>
        Current position weights:{" "}
        {Object.entries(review.current.position_weights)
          .map(([s, w]) => `${s} ${pct(w)}`)
          .join("; ")}
      </p>
      <p>
        Current sector weights:{" "}
        {Object.entries(review.current.sector_weights)
          .map(([s, w]) => `${s} ${pct(w)}`)
          .join("; ")}
      </p>
      {review.allocation && (
        <div className="border-t pt-2" data-testid="allocation-receipt">
          <strong>Proposed / 拟议组合: {review.allocation.status}</strong>
          <p className="text-amber-900">
            Non-actionable risk preview / 非行动性风险预览 — no ready, approval
            or execution from this calculation alone.
          </p>
          {review.snapshot.policy.policy && (
            <p data-testid="risk-policy-limits">
              Max position:{" "}
              {pct(review.snapshot.policy.policy.max_position_weight)}; max
              sector: {pct(review.snapshot.policy.policy.max_sector_weight)};
              min cash: {pct(review.snapshot.policy.policy.min_cash_weight)};
              max turnover: {pct(review.snapshot.policy.policy.max_turnover)}
            </p>
          )}
          {review.allocation.constraints.map((c) => (
            <p
              key={c}
              data-testid="allocation-constraint"
              className="text-red-700"
            >
              {c}
            </p>
          ))}
          <p>
            Post-trade cash:{" "}
            {review.allocation.posttrade_cash?.toFixed(2) ?? "Unavailable"};
            cash excluding unfilled sales:{" "}
            {review.allocation.cash_without_unfilled_sales?.toFixed(2) ??
              "Unavailable"}
          </p>
          <p>
            Proposed account σ:{" "}
            {pct(review.allocation.proposed?.account_sigma_annualized ?? null)}
          </p>
          <p>
            Proposed coverage:{" "}
            {pct(review.allocation.proposed?.history_equity_coverage ?? null)};
            common sessions:{" "}
            {review.allocation.proposed?.common_sessions.length ??
              "Unavailable"}
          </p>
          {Object.entries(review.allocation.proposed?.exclusions ?? {}).map(
            ([symbol, reasons]) => (
              <p key={symbol} className="text-red-700">
                {symbol}: {reasons.join(", ")}
              </p>
            ),
          )}
          {review.allocation.proposed?.errors.map((error) => (
            <p key={error} className="text-red-700">
              {error}
            </p>
          ))}
          {review.allocation.changes.map((c) => (
            <p key={c.symbol}>
              {c.symbol}: {c.current_quantity} → {c.proposed_quantity} shares;
              requested target {pct(c.requested_target_weight)}; costs $
              {c.estimated_cost_buffer.toFixed(2)}
            </p>
          ))}
          <p>
            Position weights:{" "}
            {Object.entries(review.allocation.proposed?.position_weights ?? {})
              .map(([s, w]) => `${s} ${pct(w)}`)
              .join("; ")}
          </p>
          <p>
            Sector weights:{" "}
            {Object.entries(review.allocation.proposed?.sector_weights ?? {})
              .map(([s, w]) => `${s} ${pct(w)}`)
              .join("; ")}
          </p>
        </div>
      )}
      <details>
        <summary>Method / 方法与限制</summary>
        <ul>
          {review.current.assumptions.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      </details>
    </section>
  );
}
