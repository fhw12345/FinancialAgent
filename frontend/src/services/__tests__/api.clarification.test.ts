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
});
