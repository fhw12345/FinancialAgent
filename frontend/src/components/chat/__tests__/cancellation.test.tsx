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

  it("does not downgrade a completed run on a late transport error", async () => {
    let messages: any[] = [];
    const setMessages = (updater: (current: any[]) => any[]) => {
      messages = updater(messages);
    };
    vi.mocked(chatService.sendMessageStreamPersistent).mockImplementation(
      (...args: any[]) => {
        const onChunk = args[2] as (content: string) => void;
        const onError = args[6] as (error: string) => void;
        const options = args[11] as {
          onRunState?: (event: {
            type: "run_state";
            run_id: string;
            status: "completed";
          }) => void;
        };
        queueMicrotask(() => {
          onChunk("Completed answer");
          options.onRunState?.({
            type: "run_state",
            run_id: "run_completed",
            status: "completed",
          });
          onError("connection reset after completion");
        });
        return vi.fn();
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
        ),
      { wrapper },
    );

    await act(async () => result.current.mutateAsync("Analyze AAPL"));

    const lastMessage = messages[messages.length - 1];
    expect(lastMessage.content).toBe("Completed answer");
    expect(lastMessage.run_status).not.toBe("failed");
  });

  it("clears a clarification card when the stream later fails", async () => {
    let messages: any[] = [];
    const setMessages = (updater: (current: any[]) => any[]) => {
      messages = updater(messages);
    };
    vi.mocked(chatService.sendMessageStreamPersistent).mockImplementation(
      (...args: any[]) => {
        const onError = args[6] as (error: string) => void;
        const options = args[11] as {
          onClarificationRequired?: (event: {
            type: "clarification_required";
            clarification_type: "symbol";
            reason_code: string;
            message: string;
            original_request: string;
            candidates: [];
          }) => void;
        };
        queueMicrotask(() => {
          options.onClarificationRequired?.({
            type: "clarification_required",
            clarification_type: "symbol",
            reason_code: "ambiguous_symbol",
            message: "Please select a company.",
            original_request: "Analyze Alpha",
            candidates: [],
          });
          onError("Clarification state could not be persisted.");
        });
        return vi.fn();
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
        ),
      { wrapper },
    );

    let request!: Promise<unknown>;
    act(() => {
      request = result.current.mutateAsync("Analyze Alpha");
    });
    await expect(request).rejects.toThrow(
      "Clarification state could not be persisted.",
    );

    const lastMessage = messages[messages.length - 1];
    expect(lastMessage.clarification_required).toBeUndefined();
    expect(lastMessage.run_status).toBe("failed");
    expect(lastMessage.content).toContain("Clarification state");
  });

  it("clears a clarification card when the stream is cancelled", async () => {
    let messages: any[] = [];
    const setMessages = (updater: (current: any[]) => any[]) => {
      messages = updater(messages);
    };
    const abort = vi.fn();
    vi.mocked(chatService.sendMessageStreamPersistent).mockImplementation(
      (...args: any[]) => {
        const options = args[11] as {
          onClarificationRequired?: (event: {
            type: "clarification_required";
            clarification_type: "symbol";
            reason_code: string;
            message: string;
            original_request: string;
            candidates: [];
          }) => void;
          onCancelled?: () => void;
        };
        queueMicrotask(() =>
          options.onClarificationRequired?.({
            type: "clarification_required",
            clarification_type: "symbol",
            reason_code: "ambiguous_symbol",
            message: "Please select a company.",
            original_request: "Analyze Alpha",
            candidates: [],
          }),
        );
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
        ),
      { wrapper },
    );

    let request!: Promise<unknown>;
    act(() => {
      request = result.current.mutateAsync("Analyze Alpha");
    });
    await waitFor(() =>
      expect(
        messages[messages.length - 1]?.clarification_required,
      ).toBeDefined(),
    );
    act(() => result.current.cancelActiveRequest());
    await act(async () => request);

    const lastMessage = messages[messages.length - 1];
    expect(lastMessage.clarification_required).toBeUndefined();
    expect(lastMessage.run_status).toBe("cancelled");
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
