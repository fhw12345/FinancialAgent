import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeftRight, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import type { Holding, PortfolioSummary } from "../../types/portfolio";
import {
  useAddHolding,
  useDeleteHolding,
  useUpdateHolding,
  useRefreshHoldingPrices,
} from "../../hooks/usePortfolio";
import { useAddUserTransaction } from "../../hooks/useUserTransactions";
import { formatTime } from "../../utils/timeFormatter";
import { SessionBadge } from "../common/SessionBadge";
import { ExtHoursLine } from "../common/ExtHoursLine";
import { HoldingFormModal, type HoldingFormValues } from "./HoldingFormModal";
import {
  AddTransactionModal,
  type TransactionFormValues,
} from "./AddTransactionModal";

interface PortfolioSummaryTableProps {
  holdings: Holding[];
  summary: PortfolioSummary;
}

// Most-recent timestamp from the holdings list. Backend stamps
// `last_price_update` whenever a quote is persisted (POST/PATCH/refresh-prices),
// so the max across rows is the real freshness signal for the whole table.
// Surface the session label of THAT specific row so the chip matches the time.
type LatestUpdate = {
  date: Date;
  session: Holding["last_session"];
} | null;

function pickLatestPriceUpdate(holdings: Holding[]): LatestUpdate {
  let latestMs = 0;
  let latestSession: Holding["last_session"] = null;
  for (const h of holdings) {
    if (!h.last_price_update) continue;
    const ms = new Date(h.last_price_update).getTime();
    if (Number.isFinite(ms) && ms > latestMs) {
      latestMs = ms;
      latestSession = h.last_session ?? null;
    }
  }
  return latestMs > 0
    ? { date: new Date(latestMs), session: latestSession }
    : null;
}

function formatRelativeAge(date: Date, now: Date): string {
  const sec = Math.max(0, Math.floor((now.getTime() - date.getTime()) / 1000));
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  return `${day}d ago`;
}

export function PortfolioSummaryTable({
  holdings,
  summary,
}: PortfolioSummaryTableProps) {
  const { i18n } = useTranslation();
  const totalMarketValue = summary.total_market_value || 0;
  const totalPL = summary.total_unrealized_pl || 0;
  const totalPLPct = summary.total_unrealized_pl_pct || 0;

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Holding | null>(null);
  const [txModalOpen, setTxModalOpen] = useState(false);
  // Tick once a minute so the "N min ago" label re-renders without needing
  // a holdings refetch.
  const [now, setNow] = useState<Date>(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(id);
  }, []);

  const latest = pickLatestPriceUpdate(holdings);
  const latestPriceUpdate = latest?.date ?? null;
  const latestSession = latest?.session ?? null;

  const addMut = useAddHolding();
  const updateMut = useUpdateHolding();
  const deleteMut = useDeleteHolding();
  const refreshMut = useRefreshHoldingPrices();
  const addTxMut = useAddUserTransaction();

  const formatCurrency = (value: number): string => `$${value.toFixed(2)}`;
  const formatPercentage = (value: number): string => `${value.toFixed(2)}%`;
  const getPLColorClass = (value: number): string =>
    value >= 0 ? "text-green-600" : "text-red-600";
  const getPLEmoji = (value: number): string => (value >= 0 ? "🟢" : "🔴");

  const openAdd = () => {
    setEditing(null);
    setModalOpen(true);
  };
  const openEdit = (h: Holding) => {
    setEditing(h);
    setModalOpen(true);
  };
  const closeModal = () => {
    setModalOpen(false);
    setEditing(null);
  };

  const handleSubmit = async (values: HoldingFormValues) => {
    if (editing) {
      await updateMut.mutateAsync({
        holdingId: editing.holding_id,
        update: { quantity: values.quantity, avg_price: values.avg_price },
      });
    } else {
      await addMut.mutateAsync({
        symbol: values.symbol,
        quantity: values.quantity,
        avg_price: values.avg_price,
      });
    }
    closeModal();
  };

  const handleDelete = async (h: Holding) => {
    if (!window.confirm(`Delete ${h.symbol} (${h.quantity} shares)?`)) return;
    await deleteMut.mutateAsync(h.holding_id);
  };

  const handleAddTx = async (values: TransactionFormValues) => {
    try {
      await addTxMut.mutateAsync({
        symbol: values.symbol,
        side: values.side,
        quantity: values.quantity,
        price: values.price,
        total_amount: values.total_amount,
        executed_at: values.executed_at
          ? new Date(values.executed_at).toISOString()
          : undefined,
        notes: values.notes,
      });
      setTxModalOpen(false);
    } catch {
      // mutation surfaces error; keep modal open
    }
  };

  const submitting = addMut.isPending || updateMut.isPending;

  // ----- Empty state still gets the Add button -----
  if (holdings.length === 0) {
    return (
      <>
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-bold">Portfolio Holdings</h2>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setTxModalOpen(true)}
                className="inline-flex items-center gap-1 rounded border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
                title="Record a manual buy/sell — auto-syncs holdings"
              >
                <ArrowLeftRight className="h-4 w-4" />
                Add Transaction
              </button>
              <button
                onClick={openAdd}
                className="inline-flex items-center gap-1 rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
              >
                <Plus className="h-4 w-4" />
                Add Holding
              </button>
            </div>
          </div>
          <div className="text-center text-gray-500 py-8">
            <p>No positions to display</p>
            <p className="text-sm mt-2">Click Add Holding to get started.</p>
          </div>
        </div>
        <HoldingFormModal
          open={modalOpen}
          initial={editing}
          onClose={closeModal}
          onSubmit={handleSubmit}
          submitting={submitting}
        />
        <AddTransactionModal
          open={txModalOpen}
          onClose={() => setTxModalOpen(false)}
          onSubmit={handleAddTx}
          submitting={addTxMut.isPending}
        />
      </>
    );
  }

  return (
    <>
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xl font-bold">Portfolio Holdings</h2>
            {latestPriceUpdate && (
              <p className="mt-0.5 text-xs text-gray-500">
                Last updated:{" "}
                <span className="font-medium text-gray-700">
                  {formatTime(latestPriceUpdate, i18n.language, {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
                <span className="ml-1 text-gray-400">
                  · {formatRelativeAge(latestPriceUpdate, now)}
                </span>
                {latestSession && latestSession !== "regular" && (
                  <SessionBadge session={latestSession} />
                )}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => refreshMut.mutate()}
              disabled={refreshMut.isPending}
              className="inline-flex items-center gap-1 rounded border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              title="Fetch latest prices and recompute P/L for every holding"
            >
              <RefreshCw
                className={`h-4 w-4 ${refreshMut.isPending ? "animate-spin" : ""}`}
              />
              {refreshMut.isPending ? "Refreshing…" : "Refresh Prices"}
            </button>
            <button
              onClick={() => setTxModalOpen(true)}
              className="inline-flex items-center gap-1 rounded border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
              title="Record a manual buy/sell — auto-syncs holdings"
            >
              <ArrowLeftRight className="h-4 w-4" />
              Add Transaction
            </button>
            <button
              onClick={openAdd}
              className="inline-flex items-center gap-1 rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
            >
              <Plus className="h-4 w-4" />
              Add Holding
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full font-mono text-sm border-collapse">
            <thead>
              <tr className="border-b-2 border-gray-300">
                <th className="text-left py-2 px-2">Symbol</th>
                <th className="text-right py-2 px-2">Qty</th>
                <th className="text-right py-2 px-2">Avg Price</th>
                <th className="text-right py-2 px-2">Current</th>
                <th className="text-right py-2 px-2">Day %</th>
                <th className="text-right py-2 px-2">Market Value</th>
                <th className="text-right py-2 px-2">P/L</th>
                <th className="text-right py-2 px-2">P/L%</th>
                <th className="text-right py-2 px-2 w-20"></th>
              </tr>
            </thead>
            <tbody>
              {holdings.map((holding) => {
                const pl = holding.unrealized_pl || 0;
                const plPct = holding.unrealized_pl_pct || 0;
                const dayPct = holding.day_change_percent;

                return (
                  <tr
                    key={holding.symbol}
                    className="border-b border-gray-200 hover:bg-gray-50"
                  >
                    <td className="py-2 px-2 font-bold">{holding.symbol}</td>
                    <td className="text-right py-2 px-2">{holding.quantity}</td>
                    <td className="text-right py-2 px-2">
                      {formatCurrency(holding.avg_price)}
                    </td>
                    <td className="text-right py-2 px-2">
                      <span className="inline-flex items-center gap-1 justify-end">
                        {holding.current_price
                          ? formatCurrency(holding.current_price)
                          : "-"}
                        <SessionBadge session={holding.last_session} />
                      </span>
                      <ExtHoursLine
                        price={holding.ext_hours_price}
                        session={holding.ext_hours_session}
                        changePercent={holding.ext_hours_change_percent}
                      />
                    </td>
                    <td
                      className={`text-right py-2 px-2 ${
                        dayPct == null
                          ? "text-gray-400"
                          : getPLColorClass(dayPct)
                      }`}
                    >
                      {dayPct == null
                        ? "-"
                        : `${dayPct >= 0 ? "+" : ""}${dayPct.toFixed(2)}%`}
                    </td>
                    <td className="text-right py-2 px-2">
                      {holding.market_value
                        ? formatCurrency(holding.market_value)
                        : "-"}
                    </td>
                    <td
                      className={`text-right py-2 px-2 ${getPLColorClass(pl)}`}
                    >
                      {getPLEmoji(pl)} {formatCurrency(pl)}
                    </td>
                    <td
                      className={`text-right py-2 px-2 ${getPLColorClass(plPct)}`}
                    >
                      {formatPercentage(plPct)}
                    </td>
                    <td className="text-right py-2 px-2">
                      <div className="inline-flex gap-1">
                        <button
                          onClick={() => openEdit(holding)}
                          className="rounded p-1 text-gray-500 hover:bg-blue-50 hover:text-blue-700"
                          aria-label={`Edit ${holding.symbol}`}
                          title="Edit"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(holding)}
                          disabled={deleteMut.isPending}
                          className="rounded p-1 text-gray-500 hover:bg-red-50 hover:text-red-700 disabled:opacity-50"
                          aria-label={`Delete ${holding.symbol}`}
                          title="Delete"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot className="border-t-2 border-gray-300 font-bold bg-gray-50">
              <tr>
                <td colSpan={5} className="py-2 px-2">
                  TOTAL
                </td>
                <td className="text-right py-2 px-2">
                  {formatCurrency(totalMarketValue)}
                </td>
                <td
                  className={`text-right py-2 px-2 ${getPLColorClass(totalPL)}`}
                >
                  {formatCurrency(totalPL)}
                </td>
                <td
                  className={`text-right py-2 px-2 ${getPLColorClass(totalPLPct)}`}
                >
                  {formatPercentage(totalPLPct)}
                </td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        </div>

        <div className="mt-6 grid grid-cols-2 gap-4 text-sm">
          <div className="bg-blue-50 p-3 rounded">
            <p className="text-gray-600">Total Cost Basis</p>
            <p className="text-lg font-bold text-blue-600">
              {formatCurrency(summary.total_cost_basis || 0)}
            </p>
          </div>
          <div className="bg-green-50 p-3 rounded">
            <p className="text-gray-600">Total Market Value</p>
            <p className="text-lg font-bold text-green-600">
              {formatCurrency(totalMarketValue)}
            </p>
          </div>
        </div>

        {(addMut.error || updateMut.error || deleteMut.error) && (
          <div className="mt-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {(addMut.error || updateMut.error || deleteMut.error)?.message}
          </div>
        )}
      </div>

      <HoldingFormModal
        open={modalOpen}
        initial={editing}
        onClose={closeModal}
        onSubmit={handleSubmit}
        submitting={submitting}
      />
      <AddTransactionModal
        open={txModalOpen}
        onClose={() => setTxModalOpen(false)}
        onSubmit={handleAddTx}
        submitting={addTxMut.isPending}
      />
    </>
  );
}
