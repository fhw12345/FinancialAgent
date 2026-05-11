/**
 * Unit tests for useTranslated hook.
 *
 * Verifies:
 * - English locale → returns original, never calls API
 * - Chinese locale → returns translated text from API
 * - API failure → falls back to original
 * - Empty/null text → returns "" with no API call
 * - Result cached across re-renders
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { useTranslated } from "../useTranslated";
import * as translateApi from "../../services/translateApi";

vi.mock("../../services/translateApi");

// Mutable mock: tests flip the language as needed.
let mockLanguage = "en";
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    i18n: {
      get language() {
        return mockLanguage;
      },
    },
  }),
}));

const wrapper = () => {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return ({ children }: { children: any }) =>
    createElement(QueryClientProvider, { client: qc }, children);
};

describe("useTranslated", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLanguage = "en";
  });

  it("returns original text immediately when locale is English", () => {
    mockLanguage = "en";
    const { result } = renderHook(() => useTranslated("BUY signal on AAPL"), {
      wrapper: wrapper(),
    });
    expect(result.current).toEqual({
      text: "BUY signal on AAPL",
      isLoading: false,
      isTranslated: false,
    });
    expect(translateApi.translateBatch).not.toHaveBeenCalled();
  });

  it("returns empty for null/undefined text without calling API", () => {
    mockLanguage = "zh-CN";
    const { result } = renderHook(() => useTranslated(null), {
      wrapper: wrapper(),
    });
    expect(result.current.text).toBe("");
    expect(result.current.isTranslated).toBe(false);
    expect(translateApi.translateBatch).not.toHaveBeenCalled();
  });

  it("translates when locale is zh-CN", async () => {
    mockLanguage = "zh-CN";
    vi.mocked(translateApi.translateBatch).mockResolvedValue(["买入信号"]);

    const { result } = renderHook(() => useTranslated("BUY signal"), {
      wrapper: wrapper(),
    });

    // Initially shows original while loading
    expect(result.current.text).toBe("BUY signal");
    expect(result.current.isLoading).toBe(true);

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.text).toBe("买入信号");
    expect(result.current.isTranslated).toBe(true);
    expect(translateApi.translateBatch).toHaveBeenCalledWith(
      ["BUY signal"],
      "zh-CN"
    );
  });

  it("falls back to original on API error", async () => {
    mockLanguage = "zh-CN";
    vi.mocked(translateApi.translateBatch).mockRejectedValue(
      new Error("network down")
    );

    const { result } = renderHook(() => useTranslated("hello"), {
      wrapper: wrapper(),
    });

    // Hook retries once on error (matches useTranslated config), so wait
    // longer for the final settled state.
    await waitFor(
      () => {
        expect(result.current.isLoading).toBe(false);
        expect(result.current.text).toBe("hello");
      },
      { timeout: 3000 }
    );
    expect(result.current.isTranslated).toBe(false);
  });

  it("does not call API for unsupported locale", () => {
    mockLanguage = "ja-JP"; // not in SUPPORTED_TARGETS
    const { result } = renderHook(() => useTranslated("hi"), {
      wrapper: wrapper(),
    });
    expect(result.current.text).toBe("hi");
    expect(translateApi.translateBatch).not.toHaveBeenCalled();
  });

  it("short-circuits when source text already looks like target language", () => {
    // Legacy / repaired rows can land Chinese in the base field. Without
    // this guard the hook fires /api/translate, leaves isLoading=true, and
    // <Translated /> renders the Chinese at opacity 0.7 (faded text bug).
    mockLanguage = "zh-CN";
    const { result } = renderHook(
      () => useTranslated("买入苹果，因为第四季度服务业务增长加速。"),
      { wrapper: wrapper() }
    );
    expect(result.current.text).toBe(
      "买入苹果，因为第四季度服务业务增长加速。"
    );
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isTranslated).toBe(true);
    expect(translateApi.translateBatch).not.toHaveBeenCalled();
  });
});

describe("useTranslated precomputed", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLanguage = "zh-CN";
  });

  it("returns precomputed value without calling translateBatch", () => {
    const { result } = renderHook(
      () => useTranslated("Hello world", { precomputed: "你好世界" }),
      { wrapper: wrapper() }
    );
    expect(result.current.text).toBe("你好世界");
    expect(result.current.isTranslated).toBe(true);
    expect(result.current.isLoading).toBe(false);
    expect(translateApi.translateBatch).not.toHaveBeenCalled();
  });

  it("falls through to lazy path when precomputed is null", () => {
    vi.mocked(translateApi.translateBatch).mockResolvedValue(["你好"]);
    const { result } = renderHook(
      () => useTranslated("Hello", { precomputed: null }),
      { wrapper: wrapper() }
    );
    expect(result.current.isLoading).toBe(true);
    expect(translateApi.translateBatch).toHaveBeenCalled();
  });

  it("falls through to lazy path when precomputed is empty string", () => {
    vi.mocked(translateApi.translateBatch).mockResolvedValue(["你好"]);
    renderHook(() => useTranslated("Hello", { precomputed: "" }), {
      wrapper: wrapper(),
    });
    expect(translateApi.translateBatch).toHaveBeenCalled();
  });
});
