/**
 * Shared utilities for parsing backend messages into frontend ChatMessage format.
 *
 * Centralizes deep_events extraction and analysis_data filtering to avoid
 * duplication between useChatRestoration and EnhancedChatInterface.
 */

import type { ChatMessage, DeepStreamEvent } from "../types/api";

/** Raw backend message shape (subset of fields used during parsing) */
interface BackendMessage {
  role: string;
  content: string;
  timestamp: string;
  tool_call?: ChatMessage["tool_call"];
  metadata?: {
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
    | DeepStreamEvent[]
    | undefined;

  let analysis_data: Record<string, unknown> | undefined = undefined;

  if (msg.metadata?.raw_data && Object.keys(msg.metadata.raw_data).length > 0) {
    const rawData = msg.metadata.raw_data as Record<string, unknown>;
    const filtered = Object.fromEntries(
      Object.entries(rawData).filter(([key]) => key !== "deep_events"),
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
    tool_call: msg.tool_call,
  };
}

/**
 * Replay deep events from a message array into an accordion dispatcher.
 *
 * Iterates backward to find the most recent message with deep_events,
 * replays all events, and returns true if any actions were dispatched.
 */
export function replayDeepEvents(
  messages: ChatMessage[],
  mapEventToAction: (event: DeepStreamEvent) => unknown | null,
  dispatch: (action: unknown) => void,
): boolean {
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
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
