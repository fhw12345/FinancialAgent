import { describe, expect, it } from "vitest";
import {
  isAgentEventEnvelope,
  normalizeAgentStreamEvent,
} from "../agentEvents";

describe("agent event envelopes", () => {
  it("unwraps the legacy payload and retains canonical metadata", () => {
    const normalized = normalizeAgentStreamEvent({
      schema_version: "1.0",
      run_id: "run_1",
      stream_id: "run_1",
      sequence: 3,
      type: "response_chunk",
      timestamp: "2026-07-21T02:00:00Z",
      payload: { type: "chunk", content: "hello" },
    });

    expect(normalized.type).toBe("chunk");
    expect("content" in normalized && normalized.content).toBe("hello");
    expect(normalized.agent_event?.type).toBe("response_chunk");
    expect(normalized.agent_event?.sequence).toBe(3);
  });

  it("keeps migration-era legacy events unchanged", () => {
    const legacy = { type: "chunk" as const, content: "legacy" };
    expect(normalizeAgentStreamEvent(legacy)).toEqual(legacy);
    expect(isAgentEventEnvelope(legacy)).toBe(false);
  });

  it("rejects malformed event fields before dispatch", () => {
    expect(() =>
      normalizeAgentStreamEvent({
        type: "tool_start",
        tool_name: 42,
        inputs: "invalid",
      }),
    ).toThrow("Malformed agent stream event");
  });

  it("accepts older v1 envelopes without stream_id", () => {
    const normalized = normalizeAgentStreamEvent({
      schema_version: "1.0",
      run_id: "run_legacy",
      sequence: 1,
      type: "response_chunk",
      timestamp: "2026-07-21T02:00:00Z",
      payload: { type: "chunk", content: "legacy envelope" },
    });

    expect(normalized.agent_event?.stream_id).toBe("run_legacy");
  });
});
