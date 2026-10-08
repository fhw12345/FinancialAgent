/** Last-known PAPER values keep their as-of/stale/manual provenance visible. */
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { createRequestId } from "../../../services/api";
import { reviewError } from "../../../services/decisionReviews";
import {
  exportPaper,
  refreshPaper,
  type PaperView,
} from "../../../services/paperLedger";

export function PaperDetails({
  view,
  changed,
}: {
  view: PaperView;
  changed: () => void;
}) {
  const [inspected, setInspected] = useState(false);
  const [requestId] = useState(createRequestId);
  const [manifest, setManifest] = useState<string | null>(null);
  const refresh = useMutation({
    mutationFn: () => refreshPaper(view, requestId),
    onSuccess: () => {
      setInspected(false);
      changed();
    },
  });
  const exported = useMutation({
    mutationFn: () => exportPaper(view.experiment.experiment_id),
    onSuccess: setManifest,
  });
  const valuation = view.valuation;
  return (
    <div
      data-testid="paper-details"
      className="space-y-2 rounded border p-3 text-sm"
    >
      <h4 className="font-semibold">
        PAPER · {view.settings.name} ·{" "}
        {view.projection.closed
          ? "closed / 已关闭"
          : "manual scenario / 人工情景"}
      </h4>
      <p className="text-xs">
        Sequence / 修订 {view.experiment.sequence} · USD · FIFO · fee{" "}
        {view.settings.commission_bps} bps · slip {view.settings.slippage_bps}{" "}
        bps
      </p>
      <p>
        Cash / 模拟现金:{" "}
        <strong data-testid="paper-cash">{view.projection.cash}</strong> USD
      </p>
      <p>
        Realized scenario P&L / 已实现情景盈亏:{" "}
        <span data-testid="paper-realized">{view.projection.realized_pnl}</span>{" "}
        USD · commissions / 手续费: {view.projection.commissions}
      </p>
      <p>
        Manual dividend income / 人工分红净收入:{" "}
        {view.projection.dividend_income} USD
      </p>
      <ul>
        {view.projection.positions.map((p) => (
          <li key={p.symbol} data-testid={`paper-position-${p.symbol}`}>
            {p.symbol}: {p.quantity} shares · basis / 成本 {p.cost_basis} USD
          </li>
        ))}
      </ul>
      {!valuation && (
        <p data-testid="paper-nav">
          Not valued yet / 尚未估值 — holdings are not zero-priced.
        </p>
      )}
      {valuation && (
        <div
          data-testid="paper-valuation"
          data-status={valuation.status}
          data-stale={String(valuation.stale)}
          className="rounded border p-2"
        >
          <p>
            Last recorded session / 最近登记交易日: {valuation.session_date} ·{" "}
            {valuation.status}
          </p>
          <p data-testid="paper-nav">
            Last-known NAV / 最近记录净值:{" "}
            {valuation.nav ?? "Unavailable / 无法估值"} USD
          </p>
          <p>
            Conditional scenario P&L / 条件情景盈亏:{" "}
            {valuation.scenario_pnl ?? "Unavailable"} USD
          </p>
          <p>
            Marked positions / 已估值持仓: {valuation.marked_positions}/
            {valuation.total_positions}
          </p>
          {valuation.stale && (
            <p role="status" className="text-amber-900">
              Stale / 陈旧: {valuation.stale_reasons.join(", ")} — not current
              NAV / 不是当前净值
            </p>
          )}
          {valuation.errors.map((reason) => (
            <p key={reason} className="text-red-700">
              {reason}
            </p>
          ))}
          <p className="text-xs">
            Recorded / 记录时间: {valuation.recorded_at}
          </p>
          <p className="text-xs">
            Current scenario quantities × last completed close. The closing
            session may precede today’s entries; this is not a historical fill
            or return. /
            当前情景股数按最近收盘价估值；交易日可能早于今日分录，不代表历史成交或收益。
          </p>
        </div>
      )}
      <p className="text-xs text-amber-900">
        Scenario assumptions, not verified returns or AI-approved fills. No
        activity while offline. /
        这是情景假设，不是已验证收益；服务关闭时不执行任何操作。
      </p>
      {!view.projection.closed && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (inspected) refresh.mutate();
          }}
          className="space-y-2"
        >
          <label className="block">
            <input
              type="checkbox"
              checked={inspected}
              data-testid="paper-reconciliation-ack"
              onChange={(e) => setInspected(e.target.checked)}
            />{" "}
            I inspected splits/dividends through {view.current_session} and
            recorded any necessary manual reconciliation. /
            我已核对截至该交易日的拆股与分红并登记必要分录。
          </label>
          <p className="text-xs">
            This is your attestation, not automatic corporate-action
            verification. Only this button fetches current closing marks; no
            model call. /
            这是人工声明，不是自动核实；仅此按钮读取收盘价，不调用模型。
          </p>
          <button
            disabled={!inspected || refresh.isPending}
            data-testid="paper-refresh"
            className="rounded border px-2 py-1 disabled:opacity-40"
          >
            Refresh PAPER valuation / 按需更新模拟估值
          </button>
        </form>
      )}
      {(refresh.error || exported.error) && (
        <p
          role="alert"
          data-testid="paper-valuation-error"
          className="text-red-700"
        >
          {reviewError(refresh.error ?? exported.error)}
        </p>
      )}
      <details>
        <summary>
          Append-only events / 不可改写分录 ({view.experiment.events.length})
        </summary>
        {view.experiment.events.map((row) => (
          <div
            key={row.event_id}
            className="border-t py-2 text-xs"
            data-testid="paper-event"
          >
            <p>
              #{row.sequence} {row.payload.kind} · {row.recorded_at}
            </p>
            {row.payload.kind === "trade" && (
              <p>
                {row.payload.symbol} {row.payload.side} {row.payload.quantity} @
                scenario reference {row.payload.reference_price}
              </p>
            )}
            {view.trade_receipts
              .filter((r) => r.event_id === row.event_id)
              .map((receipt) => (
                <p key={receipt.event_id}>
                  Effective scenario price {receipt.effective_price} · principal{" "}
                  {receipt.principal} · fee {receipt.commission} USD
                </p>
              ))}
            {(row.payload.kind === "split" ||
              row.payload.kind === "dividend") && (
              <p>{JSON.stringify(row.payload)}</p>
            )}
            <p className="break-all text-gray-500">{row.event_hash}</p>
          </div>
        ))}
      </details>
      <button
        type="button"
        onClick={() => exported.mutate()}
        disabled={exported.isPending}
        data-testid="paper-export"
        className="rounded border px-2 py-1"
      >
        Read ledger manifest / 读取账本清单
      </button>
      {manifest && (
        <details open>
          <summary>PAPER manifest / 账本清单</summary>
          <pre
            data-testid="paper-manifest"
            className="max-h-60 overflow-auto text-xs"
          >
            {manifest}
          </pre>
        </details>
      )}
    </div>
  );
}
