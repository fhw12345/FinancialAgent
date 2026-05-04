/**
 * AddTransactionModal — record a manual buy/sell that already executed.
 *
 * Auto-syncs the holdings collection: BUY adds shares with weighted-avg cost,
 * SELL deducts (oversell → 400). Mirrors HoldingFormModal pattern + uses the
 * shared SymbolSearch primitive for ticker autocomplete.
 */

import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { X } from "lucide-react";
import { SymbolSearch } from "../SymbolSearch";
import type { UserTransaction } from "../../hooks/useUserTransactions";

const schema = z.object({
  symbol: z
    .string()
    .min(1, "Symbol required")
    .max(10, "Max 10 chars")
    .transform((s) => s.toUpperCase()),
  side: z.enum(["buy", "sell"]),
  quantity: z.coerce.number().positive("Must be > 0"),
  price: z.coerce.number().positive("Must be > 0"),
  total_amount: z.coerce.number().positive().optional(),
  executed_at: z.string().min(1, "Required"),
  notes: z.string().max(500).optional(),
});

export type TransactionFormValues = z.infer<typeof schema>;

interface Props {
  open: boolean;
  initial?: UserTransaction | null;
  onClose: () => void;
  onSubmit: (values: TransactionFormValues) => Promise<void> | void;
  submitting?: boolean;
}

function nowLocalIso(): string {
  // <input type="datetime-local"> wants YYYY-MM-DDTHH:mm (no seconds, no tz)
  const d = new Date();
  const pad = (n: number) => n.toString().padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}

export function AddTransactionModal({
  open,
  initial,
  onClose,
  onSubmit,
  submitting,
}: Props) {
  const isEdit = !!initial;
  const {
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    formState: { errors },
  } = useForm<TransactionFormValues>({
    resolver: zodResolver(schema),
    defaultValues: initial
      ? {
          symbol: initial.symbol,
          side: initial.side,
          quantity: initial.quantity,
          price: initial.price,
          total_amount: initial.total_amount,
          executed_at: initial.executed_at.slice(0, 16),
          notes: initial.notes ?? "",
        }
      : {
          symbol: "",
          side: "buy",
          quantity: undefined as any,
          price: undefined as any,
          total_amount: undefined,
          executed_at: nowLocalIso(),
          notes: "",
        },
  });

  // Live-update total_amount = qty * price (unless user has touched it)
  const qty = watch("quantity");
  const price = watch("price");
  const totalDirty = !!watch("total_amount") && false; // we don't track touched; always recompute

  useEffect(() => {
    if (typeof qty === "number" && typeof price === "number" && qty > 0 && price > 0) {
      setValue("total_amount", Number((qty * price).toFixed(2)));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qty, price]);

  useEffect(() => {
    if (open) {
      reset(
        initial
          ? {
              symbol: initial.symbol,
              side: initial.side,
              quantity: initial.quantity,
              price: initial.price,
              total_amount: initial.total_amount,
              executed_at: initial.executed_at.slice(0, 16),
              notes: initial.notes ?? "",
            }
          : {
              symbol: "",
              side: "buy",
              quantity: undefined as any,
              price: undefined as any,
              total_amount: undefined,
              executed_at: nowLocalIso(),
              notes: "",
            },
      );
    }
  }, [open, initial, reset]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="w-full max-w-lg rounded-lg bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
          <h3 className="text-base font-semibold text-gray-900">
            {isEdit ? `Edit Transaction — ${initial.symbol}` : "Add Transaction"}
          </h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form
          onSubmit={handleSubmit(async (values) => {
            await onSubmit(values);
          })}
          className="px-4 py-4 space-y-3"
        >
          {/* Symbol */}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Symbol
            </label>
            {isEdit ? (
              <input
                {...register("symbol")}
                type="text"
                disabled
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm uppercase bg-gray-100 text-gray-500"
              />
            ) : (
              <>
                <input type="hidden" {...register("symbol")} />
                <SymbolSearch
                  autoFocus
                  value={watch("symbol") || ""}
                  placeholder="AAPL — Apple Inc."
                  onSymbolSelect={(sym) =>
                    setValue("symbol", sym, {
                      shouldValidate: true,
                      shouldDirty: true,
                    })
                  }
                />
              </>
            )}
            {errors.symbol && (
              <p className="mt-1 text-xs text-red-600">{errors.symbol.message}</p>
            )}
          </div>

          {/* Side */}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Side
            </label>
            <select
              {...register("side")}
              disabled={isEdit}
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none disabled:bg-gray-100 disabled:text-gray-500"
            >
              <option value="buy">BUY</option>
              <option value="sell">SELL</option>
            </select>
            {isEdit && (
              <p className="mt-1 text-xs text-gray-500">
                Side cannot be changed; delete and re-add to flip.
              </p>
            )}
          </div>

          {/* Qty + Price row */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Quantity
              </label>
              <input
                {...register("quantity")}
                type="number"
                step="any"
                min="0"
                placeholder="10"
                onWheelCapture={(e) => e.preventDefault()}
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              />
              {errors.quantity && (
                <p className="mt-1 text-xs text-red-600">
                  {errors.quantity.message}
                </p>
              )}
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Execution Price ($)
              </label>
              <input
                {...register("price")}
                type="number"
                step="0.01"
                min="0"
                placeholder="150.00"
                onWheelCapture={(e) => e.preventDefault()}
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              />
              {errors.price && (
                <p className="mt-1 text-xs text-red-600">{errors.price.message}</p>
              )}
            </div>
          </div>

          {/* Total + executed_at row */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Total Amount ($)
              </label>
              <input
                {...register("total_amount")}
                type="number"
                step="0.01"
                min="0"
                placeholder="auto = qty × price"
                onWheelCapture={(e) => e.preventDefault()}
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              />
              <p className="mt-1 text-xs text-gray-500">
                Auto-calc; override if fees/rounding differ.
              </p>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Executed At
              </label>
              <input
                {...register("executed_at")}
                type="datetime-local"
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              />
              {errors.executed_at && (
                <p className="mt-1 text-xs text-red-600">
                  {errors.executed_at.message}
                </p>
              )}
            </div>
          </div>

          {/* Notes */}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Notes (optional)
            </label>
            <input
              {...register("notes")}
              type="text"
              placeholder="e.g. limit order at IBKR"
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-blue-400"
            >
              {submitting ? "Saving…" : isEdit ? "Save" : "Add Transaction"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
