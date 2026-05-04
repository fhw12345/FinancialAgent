/**
 * User-entered transaction hooks (manual buy/sell ledger).
 * Distinct from AI decision rows in /api/portfolio/transactions (legacy).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../services/api";
import { portfolioKeys } from "./usePortfolio";

export interface UserTransaction {
  transaction_id: string;
  symbol: string;
  side: "buy" | "sell";
  quantity: number;
  price: number;
  total_amount: number;
  executed_at: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface NewUserTransaction {
  symbol: string;
  side: "buy" | "sell";
  quantity: number;
  price: number;
  total_amount?: number;
  executed_at?: string; // ISO 8601
  notes?: string;
}

export interface UpdateUserTransaction {
  quantity?: number;
  price?: number;
  total_amount?: number;
  executed_at?: string;
  notes?: string;
}

const userTxKeys = {
  list: (symbol?: string) => ["user-transactions", symbol ?? "all"] as const,
};

async function listUserTransactions(symbol?: string): Promise<UserTransaction[]> {
  const params: Record<string, unknown> = { limit: 100 };
  if (symbol) params.symbol = symbol;
  const { data } = await apiClient.get<UserTransaction[]>(
    "/api/portfolio/user-transactions",
    { params },
  );
  return data;
}

export function useUserTransactions(symbol?: string) {
  return useQuery({
    queryKey: userTxKeys.list(symbol),
    queryFn: () => listUserTransactions(symbol),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}

export function useAddUserTransaction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (tx: NewUserTransaction) => {
      const { data } = await apiClient.post<UserTransaction>(
        "/api/portfolio/user-transactions",
        tx,
      );
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["user-transactions"] });
      qc.invalidateQueries({ queryKey: portfolioKeys.holdings() });
      qc.invalidateQueries({ queryKey: portfolioKeys.summary() });
    },
  });
}

export function useUpdateUserTransaction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      transactionId,
      update,
    }: {
      transactionId: string;
      update: UpdateUserTransaction;
    }) => {
      const { data } = await apiClient.patch<UserTransaction>(
        `/api/portfolio/user-transactions/${transactionId}`,
        update,
      );
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["user-transactions"] });
      qc.invalidateQueries({ queryKey: portfolioKeys.holdings() });
      qc.invalidateQueries({ queryKey: portfolioKeys.summary() });
    },
  });
}

export function useDeleteUserTransaction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (transactionId: string) => {
      await apiClient.delete(`/api/portfolio/user-transactions/${transactionId}`);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["user-transactions"] });
      qc.invalidateQueries({ queryKey: portfolioKeys.holdings() });
      qc.invalidateQueries({ queryKey: portfolioKeys.summary() });
    },
  });
}
