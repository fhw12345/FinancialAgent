/** No numeric assumptions or live activation until the user explicitly confirms a complete version. */
import { useState } from "react";
import { createRequestId } from "../../services/api";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getStrategy,
  confirmStrategy,
  deactivateStrategy,
  type StrategyState,
  type StrategyParameters,
  parametersSchema,
} from "../../services/researchStrategy";
import { getRiskPolicy } from "../../services/portfolioRisk";
import { getRecordValue } from "../../utils/safeRecord";
const numericFields: readonly [keyof StrategyParameters, string][] = [
  ["discount_rate", "Discount rate / 折现率 (fraction)"],
  ["growth_rate", "FCFF growth / 增长率 (fraction)"],
  ["terminal_growth", "Terminal growth / 永续增长 (fraction)"],
  ["tax_rate", "Assumed tax rate / 税率假设"],
  ["projection_years", "Projection years / 现金流预测年数"],
  ["valuation_discount", "Required valuation discount / 估值折扣"],
  [
    "earnings_decline_fraction",
    "EPS decline review threshold / 盈利下降复核阈值",
  ],
  ["debt_to_fcf_limit", "Net debt / FCFF review limit / 债务现金流复核上限"],
  ["max_financial_age_days", "Max financial age days / 财务期末最旧天数"],
  ["max_price_lag_sessions", "Max close lag sessions / 收盘价最大滞后交易日"],
];
function Form({
  state,
  costRevision,
  onSaved,
}: {
  state: StrategyState;
  costRevision: number;
  onSaved: () => void;
}) {
  const selected = state.versions.find(
    (v) => v.version_id === state.active_version,
  );
  const [confirmed, setConfirmed] = useState(false);
  const [invalid, setInvalid] = useState(false);
  const [requestId] = useState(createRequestId);
  const save = useMutation({
    mutationFn: (params: StrategyParameters) =>
      confirmStrategy(params, state.revision, costRevision, requestId),
    onSuccess: onSaved,
  });
  return (
    <form
      className="space-y-2 text-xs"
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        const parsed = parametersSchema.safeParse({
          ...Object.fromEntries(
            numericFields.map(([key]) => [key, Number(data.get(key))]),
          ),
          methods: data.getAll("methods"),
          peer_symbols: String(data.get("peers") ?? "")
            .split(/[ ,]+/)
            .map((s) => s.trim().toUpperCase())
            .filter(Boolean),
          peer_rationale: String(data.get("rationale") ?? ""),
          fcff_proxy_acknowledged: data.get("proxy") === "on",
        });
        if (!parsed.success || !confirmed) {
          setInvalid(true);
          return;
        }
        setInvalid(false);
        save.mutate(parsed.data);
      }}
    >
      <p>
        252 XNYS sessions · SPY total return · USD US non-financial common
        equities. Banks/insurance/ETF look-through excluded. /
        中期基本面研究，不是买卖指令。
      </p>
      <label className="block">
        <input
          name="methods"
          type="checkbox"
          value="peer_pe_annual@1"
          defaultChecked={
            selected?.parameters.methods.includes("peer_pe_annual@1") ?? false
          }
        />{" "}
        Annual peer PE / 年度同行市盈率
      </label>
      <label className="block">
        <input
          name="methods"
          type="checkbox"
          value="fcff_proxy_dcf@1"
          defaultChecked={
            selected?.parameters.methods.includes("fcff_proxy_dcf@1") ?? false
          }
        />{" "}
        FCFF proxy DCF / 代理现金流 DCF
      </label>
      <label className="block">
        Fixed peers / 预先固定同行
        <input
          name="peers"
          data-testid="strategy-peers"
          defaultValue={selected?.parameters.peer_symbols.join(", ") ?? ""}
          placeholder="Explicit tickers; blank means PE unavailable"
          className="block w-full rounded border p-1"
        />
      </label>
      <label className="block">
        Peer selection rationale / 同行选择理由
        <input
          required
          name="rationale"
          data-testid="strategy-peer-rationale"
          defaultValue={selected?.parameters.peer_rationale ?? ""}
          className="block w-full rounded border p-1"
        />
      </label>
      {numericFields.map(([key, label]) => (
        <label key={key} className="block">
          {label}
          <input
            name={key}
            data-testid={`strategy-${key}`}
            type="number"
            step="any"
            required
            defaultValue={
              selected
                ? String(
                    getRecordValue<
                      keyof StrategyParameters,
                      StrategyParameters[keyof StrategyParameters]
                    >(selected.parameters, key),
                  )
                : ""
            }
            className="ml-2 w-24 rounded border p-1"
          />
        </label>
      ))}
      <p>
        Costs bind confirmed risk policy revision {costRevision}; no automatic
        settlement ledger. Discount/growth/thresholds are your assumptions, not
        estimates supplied by the model.
      </p>
      <label className="block">
        <input
          type="checkbox"
          name="proxy"
          required
          data-testid="strategy-proxy-ack"
        />{" "}
        I understand the FCFF proxy, accrual-interest and fixed-share
        assumptions; these are not audited facts. / 确认模型局限
      </label>
      <label className="block">
        <input
          type="checkbox"
          data-testid="strategy-confirm-ack"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
        />{" "}
        Confirm immutable version for future research; no model call, approval
        or execution. / 确认后续研究使用
      </label>
      <button
        type="submit"
        data-testid="confirm-research-strategy"
        disabled={!confirmed || save.isPending}
        className="rounded border p-2 disabled:opacity-40"
      >
        Confirm strategy version
      </button>
      {(invalid || save.error) && (
        <p role="alert">
          Not saved: check fields, costs or reload after a version conflict. No
          defaults were substituted.
        </p>
      )}
    </form>
  );
}
export function ResearchStrategyPanel() {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const query = useQuery({
    queryKey: ["research-strategy"],
    queryFn: ({ signal }) => getStrategy(signal),
    refetchOnWindowFocus: false,
  });
  const costs = useQuery({
    queryKey: ["risk-policy"],
    queryFn: ({ signal }) => getRiskPolicy(signal),
    refetchOnWindowFocus: false,
  });
  const changed = () => {
    void client.invalidateQueries({ queryKey: ["research-strategy"] });
    void client.invalidateQueries({ queryKey: ["decision-assessments"] });
  };
  const disable = useMutation({
    mutationFn: () => deactivateStrategy(query.data?.revision ?? 0),
    onSuccess: changed,
  });
  return (
    <section
      data-testid="research-strategy-panel"
      className="border-b p-4 space-y-2"
    >
      <h3 className="font-semibold">Research mandate / 研究契约</h3>
      <p data-testid="active-research-strategy" className="break-all text-xs">
        {query.data?.active_version ?? "Not enabled / 尚未启用"}
      </p>
      <p className="text-xs">
        Fundamental pilot: 252 sessions · SPY total return. Short-term template
        remains disabled. / 短期实验未启用
      </p>
      <button
        className="rounded border px-2 py-1"
        data-testid="edit-research-strategy"
        onClick={() => setOpen((v) => !v)}
      >
        Configure / 配置研究契约
      </button>
      {query.data?.active_version && (
        <button
          className="ml-2 rounded border px-2 py-1"
          onClick={() => disable.mutate()}
          disabled={disable.isPending}
        >
          Deactivate for future research
        </button>
      )}
      {(query.error || disable.error) && (
        <p role="alert">Strategy unavailable; no activation implied.</p>
      )}
      {open &&
        (!costs.data?.policy ? (
          <p role="alert">
            Confirm risk preview costs first / 请先显式确认风险预览成本参数
          </p>
        ) : (
          query.data && (
            <Form
              key={`${query.data.revision}-${costs.data.revision}`}
              state={query.data}
              costRevision={costs.data.revision}
              onSaved={changed}
            />
          )
        ))}
    </section>
  );
}
