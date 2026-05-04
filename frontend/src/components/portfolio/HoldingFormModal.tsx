/**
 * HoldingFormModal — Add or Edit a holding row.
 *
 * Mirrors HelpModal pattern: fixed-position backdrop, role="dialog",
 * Escape + click-outside to close. Light theme matching the rest of
 * PortfolioSummaryTable (bg-white, gray-200 borders, blue-600 primary).
 *
 * Validation via react-hook-form + zod (first usage in this codebase;
 * deps were installed but unused).
 */

import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { X } from "lucide-react";
import type { Holding } from "../../types/portfolio";
import { SymbolSearch } from "../SymbolSearch";

const schema = z.object({
  symbol: z
    .string()
    .min(1, "Symbol required")
    .max(10, "Max 10 chars")
    .transform((s) => s.toUpperCase()),
  quantity: z.coerce.number().int("Whole shares only").positive("Must be > 0"),
  avg_price: z.coerce.number().positive("Must be > 0"),
});

export type HoldingFormValues = z.infer<typeof schema>;

interface Props {
  open: boolean;
  initial?: Holding | null;
  onClose: () => void;
  onSubmit: (values: HoldingFormValues) => Promise<void> | void;
  submitting?: boolean;
}

export function HoldingFormModal({
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
  } = useForm<HoldingFormValues>({
    resolver: zodResolver(schema),
    defaultValues: initial
      ? {
          symbol: initial.symbol,
          quantity: initial.quantity,
          avg_price: initial.avg_price,
        }
      : { symbol: "", quantity: undefined as any, avg_price: undefined as any },
  });

  // Reset whenever initial changes (open/close cycle or switching rows)
  useEffect(() => {
    if (open) {
      reset(
        initial
          ? {
              symbol: initial.symbol,
              quantity: initial.quantity,
              avg_price: initial.avg_price,
            }
          : { symbol: "", quantity: undefined as any, avg_price: undefined as any },
      );
    }
  }, [open, initial, reset]);

  // Escape to close
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
        className="w-full max-w-md rounded-lg bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
          <h3 className="text-base font-semibold text-gray-900">
            {isEdit ? `Edit ${initial.symbol}` : "Add Holding"}
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
          className="px-4 py-4 space-y-4"
        >
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Symbol
            </label>
            {isEdit ? (
              // Edit mode: locked plain input (symbol is the row identity)
              <input
                {...register("symbol")}
                type="text"
                disabled
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm uppercase bg-gray-100 text-gray-500"
              />
            ) : (
              // Add mode: autocomplete via shared SymbolSearch
              <>
                {/* Hidden input keeps react-hook-form aware of the symbol value */}
                <input type="hidden" {...register("symbol")} />
                <SymbolSearch
                  autoFocus
                  value={watch("symbol") || ""}
                  placeholder="AAPL — Apple Inc."
                  onSymbolSelect={(sym) => {
                    setValue("symbol", sym, {
                      shouldValidate: true,
                      shouldDirty: true,
                    });
                  }}
                />
              </>
            )}
            {errors.symbol && (
              <p className="mt-1 text-xs text-red-600">{errors.symbol.message}</p>
            )}
            {isEdit && (
              <p className="mt-1 text-xs text-gray-500">
                Symbol cannot be changed; delete and re-add to rename.
              </p>
            )}
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Quantity
            </label>
            <input
              {...register("quantity")}
              type="number"
              step="1"
              min="1"
              placeholder="10"
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
              Average Cost ($)
            </label>
            <input
              {...register("avg_price")}
              type="number"
              step="0.01"
              min="0.01"
              placeholder="150.00"
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            />
            {errors.avg_price && (
              <p className="mt-1 text-xs text-red-600">
                {errors.avg_price.message}
              </p>
            )}
            {!isEdit && (
              <p className="mt-1 text-xs text-gray-500">
                Same symbol added twice = quantities merged with weighted-average
                cost.
              </p>
            )}
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
              {submitting ? "Saving…" : isEdit ? "Save" : "Add"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
