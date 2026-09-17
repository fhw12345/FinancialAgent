/** Explicit snapshot refresh and policy confirmation; opening this panel never invokes a model. */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getRisk,
  refreshRisk,
  getRiskPolicy,
  confirmRiskPolicy,
  policySchema,
  type PolicyState,
  type RiskPolicy,
} from "../../services/portfolioRisk";
import { RiskReceipt } from "./RiskReceipt";
const fields: readonly [keyof RiskPolicy, string][] = [
  ["max_position_weight", "Max position / 单股上限 (0–1 equity)"],
  ["max_sector_weight", "Max sector / 行业上限 (0–1 equity)"],
  ["min_cash_weight", "Min cash / 现金下限 (0–1 equity)"],
  ["max_turnover", "Max turnover / 换手上限 (0–2 equity)"],
  ["risk_per_trade_weight", "Risk per trade / 单笔止损预算 (0–1 equity)"],
  ["lot_size", "Share lot / 股数步长 (0.000001–1)"],
  ["fee_bps", "Fees / 手续费 bps"],
  ["slippage_bps", "Slippage / 滑点 bps"],
];
function PolicyForm({
  state,
  onSaved,
}: {
  state: PolicyState;
  onSaved: () => void;
}) {
  const [confirmed, setConfirmed] = useState(false);
  const [invalid, setInvalid] = useState(false);
  const mutation = useMutation({
    mutationFn: (p: RiskPolicy) => confirmRiskPolicy(p, state.revision),
    onSuccess: onSaved,
  });
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        const raw = Object.fromEntries(
          fields.map(([key]) => [key, Number(data.get(key))]),
        );
        const parsed = policySchema.safeParse(raw);
        if (!parsed.success || !confirmed) {
          setInvalid(true);
          return;
        }
        setInvalid(false);
        mutation.mutate(parsed.data);
      }}
      className="space-y-2"
    >
      <p className="text-xs text-amber-900">
        Confirm your own limits. No defaults are inferred from risk tolerance.
        Preview policy only; Stage A remains non-actionable. /
        请自行填写限额，仅用于预览，不开放批准。
      </p>
      {fields.map(([key, label]) => (
        <label key={key} className="block text-xs">
          {label}
          <input
            data-testid={`risk-policy-${key}`}
            name={key}
            type="number"
            step="any"
            required
            defaultValue={
              state.policy
                ? Object.entries(state.policy).find(
                    ([name]) => name === key,
                  )?.[1]
                : ""
            }
            className="ml-2 w-28 rounded border p-1"
          />
        </label>
      ))}
      <label className="block text-xs">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
        />{" "}
        I confirm these preview limits / 确认上述预览限额
      </label>
      <button
        type="submit"
        disabled={!confirmed || mutation.isPending}
        className="rounded border px-3 py-1 disabled:opacity-50"
      >
        Confirm risk policy
      </button>
      {(invalid || mutation.error) && (
        <p role="alert">
          Policy not saved. Check values or reload after a revision conflict. /
          未保存，请检查数值或重新加载版本。
        </p>
      )}
    </form>
  );
}
export function PortfolioRiskPanel() {
  const client = useQueryClient();
  const [showPolicy, setShowPolicy] = useState(false);
  const risk = useQuery({
    queryKey: ["portfolio-risk"],
    queryFn: ({ signal }) => getRisk(signal),
  });
  const policy = useQuery({
    queryKey: ["risk-policy"],
    queryFn: ({ signal }) => getRiskPolicy(signal),
    refetchOnWindowFocus: false,
  });
  const refresh = useMutation({
    mutationFn: refreshRisk,
    onSuccess: () =>
      void client.invalidateQueries({ queryKey: ["portfolio-risk"] }),
  });
  return (
    <section
      className="rounded border bg-white p-3 space-y-3"
      data-testid="portfolio-risk-panel"
    >
      <h3 className="font-semibold">Portfolio risk / 组合风险</h3>
      <p className="text-xs">
        Daily-close snapshot, not a live execution price /
        日收盘快照，不是实时成交价
      </p>
      <button
        data-testid="refresh-portfolio-risk"
        disabled={refresh.isPending}
        onClick={() => refresh.mutate()}
        className="rounded border px-3 py-1"
      >
        {refresh.isPending ? "Calculating…" : "Refresh risk / 刷新风险"}
      </button>
      {(risk.error || refresh.error) && (
        <p role="alert">
          Risk unavailable. No zero-risk fallback. /
          风险不可用，不代表风险为零。
        </p>
      )}
      {risk.data && <RiskReceipt review={risk.data} />}
      {!risk.data && !risk.isLoading && (
        <p>No risk snapshot yet / 尚无风险快照</p>
      )}
      <button
        onClick={() => setShowPolicy((v) => !v)}
        className="rounded border px-3 py-1"
      >
        Risk preview policy / 预览限额
      </button>
      {showPolicy && policy.data && (
        <PolicyForm
          key={policy.data.revision}
          state={policy.data}
          onSaved={() => {
            void client.invalidateQueries({ queryKey: ["risk-policy"] });
            void client.invalidateQueries({ queryKey: ["portfolio-risk"] });
          }}
        />
      )}
      {showPolicy && policy.error && (
        <p role="alert">Policy unavailable; no allocation enabled.</p>
      )}
    </section>
  );
}
