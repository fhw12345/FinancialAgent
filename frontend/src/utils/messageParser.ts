/**
 * Shared utilities for parsing backend messages into frontend ChatMessage format.
 *
 * Centralizes deep_events extraction and analysis_data filtering to avoid
 * duplication between useChatRestoration and EnhancedChatInterface.
 */

import type {
  ChatMessage,
  ClarificationRequiredEvent,
  DeepStreamEvent,
  RouteSelectedEvent,
} from "../types/api";

/** Raw backend message shape (subset of fields used during parsing) */
interface BackendMessage {
  role: string;
  content: string;
  timestamp: string;
  tool_call?: ChatMessage["tool_call"];
  metadata?: {
    run_status?: "waiting_for_input" | "completed" | "failed" | "cancelled";
    run_id?: string;
    raw_data?: Record<string, unknown>;
    [key: string]: unknown;
  };
}

/**
 * Convert a backend message to a frontend ChatMessage.
 *
 * - Extracts `deep_events` from `metadata.raw_data` for accordion restore.
 * - Filters `deep_events` out of `analysis_data` to prevent duplication.
 * - Falls back to full `metadata` as `analysis_data` when no `raw_data` exists.
 */
export function parseBackendMessage(msg: BackendMessage): ChatMessage {
  const deep_events = msg.metadata?.raw_data?.deep_events as
    DeepStreamEvent[] | undefined;
  const route_selected = msg.metadata?.raw_data?.route_selected as
    RouteSelectedEvent | undefined;
  const storedClarification = msg.metadata?.raw_data?.clarification_required as
    ClarificationRequiredEvent | undefined;
  const clarification_required =
    msg.metadata?.run_status === "failed" ||
    msg.metadata?.run_status === "cancelled" ||
    msg.metadata?.run_status === "completed"
      ? undefined
      : storedClarification;

  let analysis_data: Record<string, unknown> | undefined = undefined;

  if (msg.metadata?.raw_data && Object.keys(msg.metadata.raw_data).length > 0) {
    const rawData = msg.metadata.raw_data;
    const filtered = Object.fromEntries(
      Object.entries(rawData).filter(
        ([key]) =>
          key !== "deep_events" &&
          key !== "route_selected" &&
          key !== "clarification_required",
      ),
    );
    analysis_data = Object.keys(filtered).length > 0 ? filtered : undefined;
  } else if (msg.metadata && Object.keys(msg.metadata).length > 0) {
    analysis_data = msg.metadata as unknown as Record<string, unknown>;
  }

  return {
    role: msg.role as "user" | "assistant",
    content: msg.content,
    timestamp: msg.timestamp,
    analysis_data,
    deep_events,
    route_selected,
    clarification_required,
    run_status: msg.metadata?.run_status,
    run_id: msg.metadata?.run_id,
    tool_call: msg.tool_call,
  };
}

/**
 * Replay deep events from a message array into an accordion dispatcher.
 *
 * Iterates backward to find the most recent message with deep_events,
 * replays all events, and returns true if any actions were dispatched.
 */
export function replayDeepEvents<T>(
  messages: ChatMessage[],
  mapEventToAction: (event: DeepStreamEvent) => T | null,
  dispatch: (action: T) => void,
): boolean {
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages.at(i);
    if (!msg) continue;
    if (msg.deep_events && Array.isArray(msg.deep_events)) {
      let hasAction = false;
      for (const event of msg.deep_events) {
        const action = mapEventToAction(event);
        if (action) {
          dispatch(action);
          hasAction = true;
        }
      }
      return hasAction;
    }
  }
  return false;
}
