/**
 * Recent Transactions Component (v0.16.x).
 *
 * Shows user-entered manual buy/sell transactions only — NOT AI decision rows
 * (those live in DecisionTracker). Each row supports inline edit/delete.
 * Holdings auto-syncs via the backend on every mutation.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowDownCircle, ArrowUpCircle, Pencil, Trash2 } from "lucide-react";
import {
  useDeleteUserTransaction,
  useUpdateUserTransaction,
  useUserTransactions,
  type UserTransaction,
} from "../../hooks/useUserTransactions";
import {
  AddTransactionModal,
  type TransactionFormValues,
} from "./AddTransactionModal";
import { formatTimestamp } from "../../utils/timeFormatter";

function formatTxDate(s: string, locale: string): string {
  try {
    return formatTimestamp(s, locale);
  } catch {
    return s;
  }
}

function SideBadge({ side }: { side: UserTransaction["side"] }) {
  if (side === "buy") {
    return (
      <span className="inline-flex items-center gap-1 rounded bg-green-100 text-green-800 px-2 py-0.5 text-xs font-medium">
        <ArrowUpCircle className="h-3 w-3" />
        BUY
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded bg-red-100 text-red-800 px-2 py-0.5 text-xs font-medium">
      <ArrowDownCircle className="h-3 w-3" />
      SELL
    </span>
  );
}

export function RecentTransactions() {
  const { i18n } = useTranslation();
  const { data: txs = [], isLoading, error } = useUserTransactions();
  const updateMut = useUpdateUserTransaction();
  const deleteMut = useDeleteUserTransaction();

  const [editing, setEditing] = useState<UserTransaction | null>(null);

  const handleSubmitEdit = async (values: TransactionFormValues) => {
    if (!editing) return;
    try {
      await updateMut.mutateAsync({
        transactionId: editing.transaction_id,
        update: {
          quantity: values.quantity,
          price: values.price,
          total_amount: values.total_amount,
          executed_at: values.executed_at
            ? new Date(values.executed_at).toISOString()
            : undefined,
          notes: values.notes,
        },
      });
      setEditing(null);
    } catch {
      // Mutation surfaces error; keep modal open so user can fix
    }
  };

  const handleDelete = async (tx: UserTransaction) => {
    if (
      !window.confirm(
        `Delete ${tx.side.toUpperCase()} ${tx.quantity} ${tx.symbol} @ $${tx.price}?`,
      )
    ) {
      return;
    }
    try {
      await deleteMut.mutateAsync(tx.transaction_id);
    } catch (e) {
      alert(`Delete failed: ${(e as Error).message}`);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow p-6 mt-6">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold text-gray-900">
          Recent Transactions
          <span className="ml-2 text-xs font-normal text-gray-500">
            (your manual buy/sell records)
          </span>
        </h2>
      </div>

      {isLoading && (
        <div className="text-sm text-gray-500">Loading…</div>
      )}
      {error && (
        <div className="text-sm text-red-600">
          Failed to load: {(error as Error).message}
        </div>
      )}

      {!isLoading && txs.length === 0 && (
        <div className="text-center text-gray-500 py-6">
          <p>No transactions yet.</p>
          <p className="text-sm mt-1">
            Click <span className="font-medium">Add Transaction</span> on the
            Portfolio Holdings card to record a buy or sell.
          </p>
        </div>
      )}

      {txs.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase text-gray-500 border-b border-gray-200">
                <th className="py-2 pr-3">Date</th>
                <th className="py-2 pr-3">Symbol</th>
                <th className="py-2 pr-3">Side</th>
                <th className="py-2 pr-3 text-right">Qty</th>
                <th className="py-2 pr-3 text-right">Price</th>
                <th className="py-2 pr-3 text-right">Total</th>
                <th className="py-2 pr-3">Notes</th>
                <th className="py-2 pr-3 w-20"></th>
              </tr>
            </thead>
            <tbody>
              {txs.map((tx) => (
                <tr
                  key={tx.transaction_id}
                  className="border-b border-gray-100 hover:bg-gray-50"
                >
                  <td className="py-2 pr-3 text-xs text-gray-500">
                    {formatTxDate(tx.executed_at, i18n.language)}
                  </td>
                  <td className="py-2 pr-3 font-mono font-medium text-gray-900">
                    {tx.symbol}
                  </td>
                  <td className="py-2 pr-3">
                    <SideBadge side={tx.side} />
                  </td>
                  <td className="py-2 pr-3 text-right text-gray-700">
                    {tx.quantity}
                  </td>
                  <td className="py-2 pr-3 text-right text-gray-700">
                    ${tx.price.toFixed(2)}
                  </td>
                  <td className="py-2 pr-3 text-right text-gray-700">
                    ${tx.total_amount.toFixed(2)}
                  </td>
                  <td className="py-2 pr-3 text-xs text-gray-500 max-w-[12rem] truncate">
                    {tx.notes ?? ""}
                  </td>
                  <td className="py-2 pr-3 text-right">
                    <div className="inline-flex gap-1">
                      <button
                        onClick={() => setEditing(tx)}
                        className="rounded p-1 text-gray-500 hover:bg-blue-50 hover:text-blue-700"
                        aria-label="Edit"
                        title="Edit"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => handleDelete(tx)}
                        disabled={deleteMut.isPending}
                        className="rounded p-1 text-gray-500 hover:bg-red-50 hover:text-red-700 disabled:opacity-50"
                        aria-label="Delete"
                        title="Delete"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <AddTransactionModal
        open={!!editing}
        initial={editing}
        onClose={() => setEditing(null)}
        onSubmit={handleSubmitEdit}
        submitting={updateMut.isPending}
      />

      {(updateMut.error || deleteMut.error) && (
        <div className="mt-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {(updateMut.error || deleteMut.error)?.message}
        </div>
      )}
    </div>
  );
}
