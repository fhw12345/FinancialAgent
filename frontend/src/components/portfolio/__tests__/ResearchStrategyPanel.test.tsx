import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { ResearchStrategyPanel } from "../ResearchStrategyPanel";
import {
  getStrategy,
  confirmStrategy,
} from "../../../services/researchStrategy";
import { getRiskPolicy } from "../../../services/portfolioRisk";
vi.mock("../../../services/researchStrategy", async () => ({
  ...(await vi.importActual<
    typeof import("../../../services/researchStrategy")
  >("../../../services/researchStrategy")),
  getStrategy: vi.fn(),
  confirmStrategy: vi.fn(),
  deactivateStrategy: vi.fn(),
}));
vi.mock("../../../services/portfolioRisk", async () => ({
  ...(await vi.importActual<typeof import("../../../services/portfolioRisk")>(
    "../../../services/portfolioRisk",
  )),
  getRiskPolicy: vi.fn(),
}));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
it("opens over local HTTP without randomUUID and leaves assumptions/activation blank", async () => {
  vi.stubGlobal("crypto", { getRandomValues: (a: Uint8Array) => a.fill(1) });
  vi.mocked(getStrategy).mockResolvedValue({
    revision: 0,
    active_version: null,
    versions: [],
  });
  vi.mocked(getRiskPolicy).mockResolvedValue({
    revision: 1,
    confirmed_at: "2026-09-18T00:00:00Z",
    policy: {
      max_position_weight: 0.1,
      max_sector_weight: 0.2,
      min_cash_weight: 0.1,
      max_turnover: 1,
      risk_per_trade_weight: 0.01,
      lot_size: 1,
      fee_bps: 1,
      slippage_bps: 1,
    },
  });
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <ResearchStrategyPanel />
    </QueryClientProvider>,
  );
  fireEvent.click(await screen.findByTestId("edit-research-strategy"));
  expect(await screen.findByTestId("strategy-discount_rate")).toHaveValue(null);
  expect(screen.getByTestId("strategy-confirm-ack")).not.toBeChecked();
  expect(screen.getByTestId("confirm-research-strategy")).toBeDisabled();
  expect(confirmStrategy).not.toHaveBeenCalled();
});
