/**
 * Hook for fetching local AI order suggestions and tracked decisions.
 */

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../services/api";

export interface PortfolioOrder {
  order_id: string;
  symbol: string;
  side: "buy" | "sell";
  quantity: number;
  order_type: string;
  status: string;
  filled_qty: number;
  filled_avg_price: number | null;
  submitted_at: string | null;
  filled_at: string | null;
  analysis_id: string | null;
}

interface PortfolioOrdersResponse {
  orders: PortfolioOrder[];
  total: number;
}

async function fetchPortfolioOrders(
  limit: number = 50,
  status?: string,
): Promise<PortfolioOrdersResponse> {
  const params = new URLSearchParams({
    limit: limit.toString(),
  });

  if (status) {
    params.append("status", status);
  }

  const response = await apiClient.get<PortfolioOrdersResponse>(
    `/api/portfolio/orders?${params}`,
  );
  return response.data;
}

export function usePortfolioOrders(limit: number = 50, status?: string) {
  return useQuery({
    queryKey: ["portfolio-orders", limit, status],
    queryFn: () => fetchPortfolioOrders(limit, status),
    refetchInterval: 30000, // Refetch every 30 seconds
  });
}
