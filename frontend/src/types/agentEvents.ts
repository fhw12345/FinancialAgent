import type { StreamEvent } from "./api";

export interface AgentEventEnvelope {
  schema_version: "1.0";
  run_id: string;
  stream_id?: string;
  sequence: number;
  type: string;
  timestamp: string;
  payload: Record<string, unknown>;
}

export type NormalizedStreamEvent = StreamEvent & {
  agent_event?: Omit<AgentEventEnvelope, "payload">;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function isAgentEventEnvelope(
  value: unknown,
): value is AgentEventEnvelope {
  if (!isRecord(value)) return false;
  return (
    value.schema_version === "1.0" &&
    typeof value.run_id === "string" &&
    (value.stream_id === undefined || typeof value.stream_id === "string") &&
    typeof value.sequence === "number" &&
    typeof value.type === "string" &&
    typeof value.timestamp === "string" &&
    isRecord(value.payload)
  );
}

/** Validate the fields consumed by the streaming dispatcher. */
export function isStreamEvent(value: unknown): value is StreamEvent {
  if (!isRecord(value) || typeof value.type !== "string") return false;
  const type = value.type;
  if (type.startsWith("deep_")) return true;
  switch (type) {
    case "route_selected":
      return typeof value.flow === "string" && typeof value.source === "string";
    case "response_stream_mode":
      return typeof value.mode === "string";
    case "run_state":
      return (
        typeof value.run_id === "string" && typeof value.status === "string"
      );
    case "clarification_required":
      return (
        typeof value.message === "string" && Array.isArray(value.candidates)
      );
    case "chat_created":
    case "done":
      return typeof value.chat_id === "string";
    case "chunk":
      return typeof value.content === "string";
    case "title_generated":
      return typeof value.title === "string";
    case "error":
      return value.error === undefined || typeof value.error === "string";
    case "cancelled":
      return true;
    case "tool_start":
      return (
        typeof value.tool_name === "string" &&
        typeof value.display_name === "string" &&
        typeof value.icon === "string" &&
        typeof value.run_id === "string" &&
        isRecord(value.inputs)
      );
    case "tool_end":
      return (
        typeof value.tool_name === "string" &&
        typeof value.output === "string" &&
        typeof value.run_id === "string" &&
        typeof value.duration_ms === "number"
      );
    case "tool_error":
      return (
        typeof value.tool_name === "string" &&
        typeof value.error === "string" &&
        typeof value.run_id === "string" &&
        typeof value.duration_ms === "number"
      );
    case "tool_info":
      return (
        typeof value.tool_executions === "number" &&
        typeof value.trace_id === "string"
      );
    default:
      return false;
  }
}

export function normalizeAgentStreamEvent(
  value: unknown,
): NormalizedStreamEvent {
  const envelope = isAgentEventEnvelope(value) ? value : null;
  const event = envelope?.payload ?? value;
  if (!isStreamEvent(event)) {
    throw new TypeError("Malformed agent stream event");
  }
  return {
    ...event,
    ...(envelope
      ? {
          agent_event: {
            schema_version: envelope.schema_version,
            run_id: envelope.run_id,
            stream_id: envelope.stream_id ?? envelope.run_id,
            sequence: envelope.sequence,
            type: envelope.type,
            timestamp: envelope.timestamp,
          },
        }
      : {}),
  };
}
