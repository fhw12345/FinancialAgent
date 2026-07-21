import type { StreamEvent } from "./api";

export interface AgentEventEnvelope {
  schema_version: "1.0";
  run_id: string;
  sequence: number;
  type: string;
  timestamp: string;
  payload: Record<string, unknown>;
}

export type NormalizedStreamEvent = StreamEvent & {
  agent_event?: Omit<AgentEventEnvelope, "payload">;
};

export function isAgentEventEnvelope(
  value: unknown,
): value is AgentEventEnvelope {
  if (!value || typeof value !== "object") return false;
  const event = value as Record<string, unknown>;
  return (
    event.schema_version === "1.0" &&
    typeof event.run_id === "string" &&
    typeof event.sequence === "number" &&
    typeof event.type === "string" &&
    typeof event.timestamp === "string" &&
    !!event.payload &&
    typeof event.payload === "object"
  );
}

export function normalizeAgentStreamEvent(
  value: AgentEventEnvelope | StreamEvent,
): NormalizedStreamEvent {
  if (!isAgentEventEnvelope(value)) {
    return value as NormalizedStreamEvent;
  }
  const payload = value.payload as unknown as StreamEvent;
  return {
    ...payload,
    agent_event: {
      schema_version: value.schema_version,
      run_id: value.run_id,
      sequence: value.sequence,
      type: value.type,
      timestamp: value.timestamp,
    },
  } as NormalizedStreamEvent;
}
