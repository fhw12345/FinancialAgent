/** Blank explicit user-scenario inputs; never fill in investment amounts or approve AI outputs. */
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { createRequestId } from "../../../services/api";
import { reviewError } from "../../../services/decisionReviews";
import {
  createPaper,
  journalPaper,
  type ManualPaperEntry,
  type NewPaperSettings,
  type PaperView,
} from "../../../services/paperLedger";

export function CreatePaperForm({
  saved,
}: {
  saved: (view: PaperView) => void;
}) {
  const [ack, setAck] = useState(false);
  const [requestId] = useState(createRequestId);
  const mutation = useMutation({
    mutationFn: (settings: NewPaperSettings) =>
      createPaper(settings, requestId),
    onSuccess: saved,
  });
  return (
    <form
      data-testid="paper-create-form"
      className="space-y-2 rounded border p-3 text-sm"
      onSubmit={(event) => {
        event.preventDefault();
        if (!ack) return;
        const data = new FormData(event.currentTarget);
        mutation.mutate({
          name: String(data.get("name") ?? "").trim(),
          initial_cash: String(data.get("cash") ?? ""),
          symbols: String(data.get("symbols") ?? "")
            .toUpperCase()
            .split(/[\s,]+/)
            .filter(Boolean),
          commission_bps: String(data.get("fees") ?? ""),
          slippage_bps: String(data.get("slip") ?? ""),
        });
      }}
    >
      <p>
        New cash-only PAPER scenario. Nothing is copied from real holdings. /
        新建纯现金模拟账户，不复制真实账户。
      </p>
      <label className="block">
        Name / 名称{" "}
        <input
          name="name"
          required
          maxLength={80}
          data-testid="paper-name"
          className="rounded border p-1"
        />
      </label>
      <label className="block">
        Initial USD cash / 初始美元现金{" "}
        <input
          name="cash"
          required
          inputMode="decimal"
          data-testid="paper-initial-cash"
          className="rounded border p-1"
        />
      </label>
      <label className="block">
        Allowed symbols / 允许标的{" "}
        <input
          name="symbols"
          required
          data-testid="paper-symbols"
          className="rounded border p-1"
        />
      </label>
      <label className="block">
        Commission bps / 手续费基点{" "}
        <input
          name="fees"
          required
          inputMode="decimal"
          data-testid="paper-commission"
          className="w-24 rounded border p-1"
        />
      </label>
      <label className="block">
        Directional slippage bps / 买卖滑点基点{" "}
        <input
          name="slip"
          required
          inputMode="decimal"
          data-testid="paper-slippage"
          className="w-24 rounded border p-1"
        />
      </label>
      <p className="text-xs">
        Enter zero explicitly if intended. FIFO includes buy fees; cents round
        half-even. Manual prices/actions are unverified scenario assumptions,
        not profitability evidence. / 零费用需明确填
        0；先进先出成本包含买入费用，金额按分取偶舍入。
      </p>
      <label className="block">
        <input
          type="checkbox"
          data-testid="paper-create-ack"
          checked={ack}
          onChange={(e) => setAck(e.target.checked)}
        />{" "}
        Create a manual PAPER scenario only, with no real trade or AI approval.
        / 仅创建人工模拟情景，不是真实交易或 AI 批准。
      </label>
      <button
        disabled={!ack || mutation.isPending}
        data-testid="paper-create"
        className="rounded border px-2 py-1 disabled:opacity-40"
      >
        Create PAPER / 创建模拟账户
      </button>
      {mutation.error && (
        <p role="alert" className="text-red-700">
          {reviewError(mutation.error)}
        </p>
      )}
    </form>
  );
}

export function PaperJournalForm({
  view,
  changed,
}: {
  view: PaperView;
  changed: () => void;
}) {
  const [ack, setAck] = useState(false);
  const [kind, setKind] = useState("");
  const [requestId] = useState(createRequestId);
  const mutation = useMutation({
    mutationFn: (entry: ManualPaperEntry) =>
      journalPaper(view, entry, requestId),
    onSuccess: changed,
  });
  return (
    <form
      data-testid="paper-journal-form"
      className="space-y-2 rounded border p-3 text-sm"
      onSubmit={(event) => {
        event.preventDefault();
        if (!ack) return;
        const data = new FormData(event.currentTarget);
        const symbol = String(data.get("symbol") ?? "");
        const origin = "manual_unverified_scenario" as const;
        if (kind === "trade") {
          const side = data.get("side");
          if (side !== "buy" && side !== "sell") return;
          mutation.mutate({
            kind,
            symbol,
            origin,
            side,
            quantity: String(data.get("quantity") ?? ""),
            reference_price: String(data.get("price") ?? ""),
          });
        } else if (kind === "split")
          mutation.mutate({
            kind,
            symbol,
            origin,
            numerator: Number(data.get("numerator")),
            denominator: Number(data.get("denominator")),
          });
        else if (kind === "dividend")
          mutation.mutate({
            kind,
            symbol,
            origin,
            gross_per_share: String(data.get("gross") ?? ""),
            withholding: String(data.get("tax") ?? ""),
          });
        else if (kind === "close") mutation.mutate({ kind });
      }}
    >
      <h4 className="font-semibold">Manual scenario journal / 人工模拟分录</h4>
      <label className="block">
        Entry / 分录{" "}
        <select
          data-testid="paper-entry-kind"
          required
          value={kind}
          onChange={(e) => {
            setKind(e.target.value);
            setAck(false);
          }}
          className="rounded border p-1"
        >
          <option value="">Choose explicitly / 请明确选择</option>
          <option value="trade">Manual trade / 人工模拟买卖</option>
          <option value="split">Manual split / 人工拆股核对</option>
          <option value="dividend">Manual dividend / 人工分红核对</option>
          <option value="close">Close read-only / 关闭为只读</option>
        </select>
      </label>
      {kind && kind !== "close" && (
        <label className="block">
          Symbol / 标的{" "}
          <select
            name="symbol"
            data-testid="paper-entry-symbol"
            required
            className="rounded border p-1"
          >
            <option value="">Choose / 选择</option>
            {view.settings.symbols.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      )}
      {kind === "trade" && (
        <>
          <label className="block">
            Side / 方向{" "}
            <select
              name="side"
              required
              data-testid="paper-trade-side"
              className="rounded border p-1"
            >
              <option value="">Choose / 选择</option>
              <option value="buy">Buy / 买入</option>
              <option value="sell">Sell / 卖出</option>
            </select>
          </label>
          <label className="block">
            Shares (≤6 decimals) / 股数{" "}
            <input
              name="quantity"
              required
              inputMode="decimal"
              data-testid="paper-trade-quantity"
              className="w-28 rounded border p-1"
            />
          </label>
          <label className="block">
            Scenario reference USD/share / 情景参考价{" "}
            <input
              name="price"
              required
              inputMode="decimal"
              data-testid="paper-trade-price"
              className="w-28 rounded border p-1"
            />
          </label>
          <p className="text-xs">
            Server records this now; not a market fill or an AI-approved trade.
            Slippage/fees apply to your price. No backdated entry or automatic
            stop. / 按当前时间登记，输入价不是已证实成交价，不补记过去成交。
          </p>
        </>
      )}
      {kind === "split" && (
        <>
          <label className="block">
            New shares / 新股数比例{" "}
            <input
              name="numerator"
              type="number"
              min="1"
              max="10000"
              step="1"
              required
              data-testid="paper-split-numerator"
              className="w-20 rounded border p-1"
            />
          </label>
          <label className="block">
            Old shares / 旧股数比例{" "}
            <input
              name="denominator"
              type="number"
              min="1"
              max="10000"
              step="1"
              required
              data-testid="paper-split-denominator"
              className="w-20 rounded border p-1"
            />
          </label>
          <p className="text-xs">
            Basis and cash unchanged; no inferred price adjustment. /
            现金及总成本不变，不自动调整价格。
          </p>
        </>
      )}
      {kind === "dividend" && (
        <>
          <label className="block">
            Gross USD per current share / 每股毛分红{" "}
            <input
              name="gross"
              required
              inputMode="decimal"
              data-testid="paper-dividend-gross"
              className="w-28 rounded border p-1"
            />
          </label>
          <label className="block">
            Total withholding USD / 总扣税额{" "}
            <input
              name="tax"
              required
              inputMode="decimal"
              data-testid="paper-dividend-tax"
              className="w-28 rounded border p-1"
            />
          </label>
          <p className="text-xs">
            Applies to current PAPER quantity, not claimed ex-date entitlement.
            Do not credit an adjusted-price dividend twice. /
            按当前模拟股数登记，不证明历史除息资格，请勿重复计入。
          </p>
        </>
      )}
      {kind === "close" && (
        <p className="text-amber-900">
          Close permanently read-only; history is retained. Mistakes cannot be
          edited away. / 关闭后仅能读取历史，不能删除或修改分录。
        </p>
      )}
      <label className="block">
        <input
          type="checkbox"
          checked={ack}
          data-testid="paper-entry-ack"
          onChange={(e) => setAck(e.target.checked)}
        />{" "}
        I explicitly record this manual scenario, not an actual or AI-validated
        transaction. / 明确登记人工模拟情景，不是真实或 AI 验证交易。
      </label>
      <button
        disabled={!ack || !kind || mutation.isPending}
        data-testid="paper-journal-submit"
        className="rounded border px-2 py-1 disabled:opacity-40"
      >
        Record PAPER entry / 登记模拟分录
      </button>
      {mutation.error && (
        <p
          role="alert"
          data-testid="paper-journal-error"
          className="text-red-700"
        >
          {reviewError(mutation.error)}
        </p>
      )}
    </form>
  );
}
