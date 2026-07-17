import { waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { chatService } from "../api";

describe("chat stream cancellation", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("invokes onCancelled when AbortController stops fetch", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init?: RequestInit) => {
        return new Promise<Response>((_resolve, reject) => {
          if (init?.signal?.aborted) {
            reject(new DOMException("Aborted", "AbortError"));
            return;
          }
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        });
      }),
    );
    const onCancelled = vi.fn();

    const cancel = chatService.sendMessageStreamPersistent(
      "Analyze AAPL",
      "chat_1",
      vi.fn(),
      undefined,
      undefined,
      vi.fn(),
      vi.fn(),
      undefined,
      undefined,
      undefined,
      undefined,
      { onCancelled },
    );
    cancel();

    await waitFor(() => expect(onCancelled).toHaveBeenCalledOnce());
  });
});
