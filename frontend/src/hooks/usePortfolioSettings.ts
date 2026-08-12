import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../services/api";

export interface PortfolioSettings {
  cash_balance: number;
  risk_tolerance: "conservative" | "moderate" | "aggressive";
  max_position_pct: number;
}

export const PORTFOLIO_SETTINGS_PATH = "/api/admin/portfolio/settings";

async function fetchSettings(): Promise<PortfolioSettings | null> {
  const { data } = await apiClient.get<PortfolioSettings | null>(
    PORTFOLIO_SETTINGS_PATH,
  );
  return data;
}

export function usePortfolioSettings() {
  return useQuery({
    queryKey: ["portfolio-settings"],
    queryFn: fetchSettings,
    staleTime: 60_000,
  });
}
