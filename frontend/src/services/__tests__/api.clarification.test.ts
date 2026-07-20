import { describe, expect, it, vi } from "vitest";
import { chatService } from "../api";

describe("chatService clarification stream", () => {
  it("dispatches clarification as a normal stream event", async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            'data: {"type":"clarification_required","clarification_type":"symbol","reason_code":"symbol_missing","message":"Select a stock","original_request":"Analyze it","candidates":[]}\n\n',
          ),
        );
        controller.enqueue(
          encoder.encode(
            'data: {"type":"done","chat_id":"chat_1","clarification_required":true}\n\n',
          ),
        );
        controller.close();
      },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(body, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        }),
      ),
    );

    const onError = vi.fn();
    const clarification = await new Promise<string>((resolve) => {
      chatService.sendMessageStreamPersistent(
        "Analyze it",
        "chat_1",
        vi.fn(),
        undefined,
        undefined,
        undefined,
        onError,
        undefined,
        undefined,
        undefined,
        undefined,
        {
          onClarificationRequired: (event) => resolve(event.reason_code),
        },
      );
    });

    expect(clarification).toBe("symbol_missing");
    expect(onError).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("dispatches the declared response stream mode", async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            'data: {"type":"response_stream_mode","mode":"buffered"}\n\n',
          ),
        );
        controller.enqueue(
          encoder.encode('data: {"type":"done","chat_id":"chat_1"}\n\n'),
        );
        controller.close();
      },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(body, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        }),
      ),
    );

    const mode = await new Promise<string>((resolve) => {
      chatService.sendMessageStreamPersistent(
        "Analyze it",
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
        {
          onStreamMode: (event) => resolve(event.mode),
        },
      );
    });

    expect(mode).toBe("buffered");
    vi.unstubAllGlobals();
  });

  it("dispatches shared run state", async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            'data: {"type":"run_state","run_id":"run_123","status":"running","execution_mode":"instant"}\n\n',
          ),
        );
        controller.enqueue(
          encoder.encode('data: {"type":"done","chat_id":"chat_1"}\n\n'),
        );
        controller.close();
      },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(body, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        }),
      ),
    );

    const runId = await new Promise<string>((resolve) => {
      chatService.sendMessageStreamPersistent(
        "Explain",
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
        {
          onRunState: (event) => resolve(event.run_id),
        },
      );
    });

    expect(runId).toBe("run_123");
    vi.unstubAllGlobals();
  });
});
