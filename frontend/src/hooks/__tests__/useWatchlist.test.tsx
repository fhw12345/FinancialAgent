import type { ReactNode } from "react";
import { act, renderHook } from "@testing-library/react";
import {
  QueryClient,
  QueryClientProvider,
  type QueryClientConfig,
} from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as watchlistApi from "../../services/watchlistApi";
import type { WatchlistItem } from "../../types/watchlist";
import { useTriggerWatchlistAnalysis, watchlistKeys } from "../useWatchlist";

vi.mock("../../services/watchlistApi");

const queryConfig: QueryClientConfig = {
  defaultOptions: {
    queries: { retry: false },
    mutations: { retry: false },
  },
};

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

function watchlistItem(): WatchlistItem {
  return {
    watchlist_id: "watch_aapl",
    symbol: "AAPL",
    added_at: "2026-07-17T05:00:00Z",
    last_analyzed_at: null,
    notes: null,
    current_price: null,
    last_price_update: null,
    last_session: null,
    day_change_percent: null,
    ext_hours_price: null,
    ext_hours_session: null,
    ext_hours_change_percent: null,
    ext_hours_asof: null,
  };
}

describe("useTriggerWatchlistAnalysis", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("updates the cached row before awaiting the Mongo refetch", async () => {
    const queryClient = new QueryClient(queryConfig);
    queryClient.setQueryData(watchlistKeys.list(), [watchlistItem()]);
    const invalidate = vi
      .spyOn(queryClient, "invalidateQueries")
      .mockResolvedValue(undefined);
    vi.mocked(watchlistApi.triggerWatchlistAnalysis).mockResolvedValue({
      status: "analysis_completed",
      symbol: "AAPL",
      result_count: 1,
      watchlist_updated: true,
      last_analyzed_at: "2026-07-17T05:30:00Z",
    });
    const { result } = renderHook(() => useTriggerWatchlistAnalysis(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      await result.current.mutateAsync("AAPL");
    });

    const cached = queryClient.getQueryData<WatchlistItem[]>(
      watchlistKeys.list(),
    );
    expect(cached?.[0].last_analyzed_at).toBe("2026-07-17T05:30:00Z");
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: watchlistKeys.list(),
    });
  });

  it("does not change a row for ad-hoc non-watchlisted analysis", async () => {
    const queryClient = new QueryClient(queryConfig);
    queryClient.setQueryData(watchlistKeys.list(), [watchlistItem()]);
    vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue(undefined);
    vi.mocked(watchlistApi.triggerWatchlistAnalysis).mockResolvedValue({
      status: "analysis_completed",
      symbol: "MSFT",
      result_count: 1,
      watchlist_updated: false,
      last_analyzed_at: null,
    });
    const { result } = renderHook(() => useTriggerWatchlistAnalysis(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      await result.current.mutateAsync("MSFT");
    });

    const cached = queryClient.getQueryData<WatchlistItem[]>(
      watchlistKeys.list(),
    );
    expect(cached?.[0].last_analyzed_at).toBeNull();
  });
});
