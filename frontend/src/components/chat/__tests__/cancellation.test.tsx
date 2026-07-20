import type { ReactNode } from "react";
import {
  act,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChatInput } from "../ChatInput";
import { useAnalysis } from "../useAnalysis";
import {
  deepAccordionReducer,
  INITIAL_STATE,
} from "../deep/useDeepAccordionState";
import { mapDeepEventToAction } from "../deep/mapDeepEvent";
import type { DeepStreamEvent } from "../../../types/api";
import { chatService } from "../../../services/api";

vi.mock("../../../services/api", () => ({
  chatService: {
    sendMessageStreamPersistent: vi.fn(),
  },
}));

vi.mock("../../../i18n", () => ({
  default: {
    language: "en",
    t: (key: string) =>
      key === "chat:message.cancelled" ? "Request cancelled." : key,
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("chat cancellation UI", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("settles the mutation and marks the placeholder cancelled", async () => {
    let messages: any[] = [];
    const setMessages = (updater: (current: any[]) => any[]) => {
      messages = updater(messages);
    };
    const abort = vi.fn();
    vi.mocked(chatService.sendMessageStreamPersistent).mockImplementation(
      (...args: any[]) => {
        const options = args[11] as { onCancelled?: () => void };
        abort.mockImplementation(() => options.onCancelled?.());
        return abort;
      },
    );
    const { result, rerender } = renderHook(
      ({ chatId }: { chatId: string | null }) =>
        useAnalysis(
          "AAPL",
          { start: "", end: "" },
          setMessages,
          vi.fn(),
          "1d",
          chatId,
          vi.fn(),
        ),
      {
        wrapper,
        initialProps: { chatId: null } as { chatId: string | null },
      },
    );

    let request!: Promise<unknown>;
    act(() => {
      request = result.current.mutateAsync("Analyze AAPL");
    });
    await waitFor(() =>
      expect(chatService.sendMessageStreamPersistent).toHaveBeenCalledOnce(),
    );
    rerender({ chatId: "chat_created" });
    expect(result.current.isPending).toBe(true);

    act(() => result.current.cancelActiveRequest());
    await act(async () => request);

    expect(abort).toHaveBeenCalledOnce();
    await waitFor(() => expect(result.current.isPending).toBe(false));
    const lastMessage = messages[messages.length - 1];
    expect(lastMessage.content).toBe("Request cancelled.");
    expect(lastMessage.run_status).toBe("cancelled");
  });

  it("renders a stop button only for cancellable streaming", () => {
    const onCancel = vi.fn();
    const { rerender } = render(
      <ChatInput
        message="Analyze AAPL"
        setMessage={vi.fn()}
        onSendMessage={vi.fn()}
        onCancelMessage={onCancel}
        isPending={false}
        canCancel={false}
        currentSymbol="AAPL"
      />,
    );

    expect(screen.getByTestId("chat-send")).not.toBeNull();
    rerender(
      <ChatInput
        message=""
        setMessage={vi.fn()}
        onSendMessage={vi.fn()}
        onCancelMessage={onCancel}
        isPending
        canCancel
        currentSymbol="AAPL"
      />,
    );
    fireEvent.click(screen.getByTestId("chat-stop"));

    expect(onCancel).toHaveBeenCalledOnce();
    expect(screen.queryByTestId("chat-send")).toBeNull();
  });

  it("does not overwrite a completed run when transport aborts late", async () => {
    let messages: any[] = [];
    const setMessages = (updater: (current: any[]) => any[]) => {
      messages = updater(messages);
    };
    const abort = vi.fn();
    vi.mocked(chatService.sendMessageStreamPersistent).mockImplementation(
      (...args: any[]) => {
        const onChunk = args[2] as (content: string) => void;
        const options = args[11] as {
          onRunState?: (event: {
            type: "run_state";
            run_id: string;
            status: "completed";
          }) => void;
          onCancelled?: () => void;
        };
        queueMicrotask(() => {
          onChunk("Completed answer");
          options.onRunState?.({
            type: "run_state",
            run_id: "run_completed",
            status: "completed",
          });
        });
        abort.mockImplementation(() => options.onCancelled?.());
        return abort;
      },
    );
    const { result } = renderHook(
      () =>
        useAnalysis(
          "AAPL",
          { start: "", end: "" },
          setMessages,
          vi.fn(),
          "1d",
          "chat_1",
          vi.fn(),
          undefined,
          undefined,
          undefined,
          vi.fn(),
        ),
      { wrapper },
    );

    let request!: Promise<unknown>;
    act(() => {
      request = result.current.mutateAsync("Analyze AAPL");
    });
    await waitFor(() =>
      expect(messages[messages.length - 1]?.content).toBe("Completed answer"),
    );
    act(() => result.current.cancelActiveRequest());
    await act(async () => request);

    expect(messages[messages.length - 1].content).toBe("Completed answer");
    expect(messages[messages.length - 1].run_status).not.toBe("cancelled");
  });

  it("maps persisted deep cancellation into cancelled accordion state", () => {
    const running = deepAccordionReducer(INITIAL_STATE, {
      type: "DEEP_START",
      symbol: "AAPL",
      subagentNames: ["technical"],
      enableDebate: true,
    });
    const event: DeepStreamEvent = {
      type: "deep_cancelled",
      seq: 2,
      timestamp: "2026-07-17T08:00:00Z",
    };
    const action = mapDeepEventToAction(event);

    expect(action).toEqual({ type: "CANCEL" });
    expect(
      deepAccordionReducer(running, action ?? { type: "RESET" }).status,
    ).toBe("cancelled");
    expect(deepAccordionReducer(INITIAL_STATE, { type: "CANCEL" }).status).toBe(
      "pending",
    );
  });
});
