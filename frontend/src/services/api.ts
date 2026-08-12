import axios from "axios";
import type {
  HealthResponse,
  ChatListResponse,
  ClarificationRequiredEvent,
  ChatDetailResponse,
  UpdateUIStateRequest,
  Chat,
  DeepStreamEvent,
  RouteSelectedEvent,
  ResponseStreamModeEvent,
  RunStateEvent,
  AgentRun,
  MarketStatus,
  ToolCall,
} from "../types/api";
import {
  isAgentEventEnvelope,
  normalizeAgentStreamEvent,
} from "../types/agentEvents";

const API_BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

function createRequestId(): string {
  if (typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return `request_${Array.from(bytes, (value) =>
    value.toString(16).padStart(2, "0"),
  ).join("")}`;
}

// Configure the local backend client.
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000, // 30 seconds for analysis requests
  headers: {
    "Content-Type": "application/json",
  },
});

// Export the configured axios instance for use in other services
export const apiClient = api;

// Health service
export const healthService = {
  async getHealth(): Promise<HealthResponse> {
    const response = await api.get<HealthResponse>("/api/health");
    return response.data;
  },

  async getMongoHealth(): Promise<{
    connected: boolean;
    [key: string]: unknown;
  }> {
    const response = await api.get<{
      connected: boolean;
      [key: string]: unknown;
    }>("/api/health/mongodb");
    return response.data;
  },

  async getRedisHealth(): Promise<{
    connected: boolean;
    [key: string]: unknown;
  }> {
    const response = await api.get<{
      connected: boolean;
      [key: string]: unknown;
    }>("/api/health/redis");
    return response.data;
  },

  async getReadiness(): Promise<{ ready: boolean; [key: string]: unknown }> {
    const response = await api.get<{
      ready: boolean;
      [key: string]: unknown;
    }>("/api/health/ready");
    return response.data;
  },

  async getLiveness(): Promise<{ alive: boolean; [key: string]: unknown }> {
    const response = await api.get<{
      alive: boolean;
      [key: string]: unknown;
    }>("/api/health/live");
    return response.data;
  },
};

// ===== Persistent Chat API =====
export const chatService = {
  /**
   * List all local chats
   */
  async listChats(
    page: number = 1,
    pageSize: number = 20,
    includeArchived: boolean = false,
  ): Promise<ChatListResponse> {
    const response = await api.get<ChatListResponse>("/api/chat/chats", {
      params: {
        page,
        page_size: pageSize,
        include_archived: includeArchived,
      },
    });
    return response.data;
  },

  /**
   * Create an empty chat (triggered by symbol selection)
   */
  async createChat(): Promise<{ chat_id: string }> {
    const response = await api.post<{ chat_id: string }>("/api/chat/chats");
    return response.data;
  },

  /**
   * Get chat detail with messages for state restoration
   */
  async getChatDetail(
    chatId: string,
    limit?: number,
    offset?: number,
  ): Promise<ChatDetailResponse> {
    const response = await api.get<ChatDetailResponse>(
      `/api/chat/chats/${chatId}`,
      {
        params: {
          ...(limit !== undefined ? { limit } : {}),
          ...(offset !== undefined ? { offset } : {}),
        },
      },
    );
    return response.data;
  },

  /**
   * Update chat UI state (debounced from frontend)
   */
  async updateUIState(
    chatId: string,
    request: UpdateUIStateRequest,
  ): Promise<Chat> {
    const response = await api.patch<Chat>(
      `/api/chat/chats/${chatId}/ui-state`,
      request,
    );
    return response.data;
  },

  /**
   * Delete a chat and all its messages
   */
  async deleteChat(chatId: string): Promise<void> {
    await api.delete(`/api/chat/chats/${chatId}`);
  },

  /**
   * Send message with streaming response and MongoDB persistence
   *
   * @param message User message
   * @param chatId Optional chat ID (creates new chat if not provided)
   * @param onChunk Callback for each content chunk
   * @param onChatCreated Callback when new chat is created
   * @param onTitleGenerated Callback when title is generated
   * @param onDone Callback when streaming completes
   * @param onError Callback for errors
   */
  sendMessageStreamPersistent(
    message: string,
    chatId: string | null,
    onChunk: (content: string) => void,
    onChatCreated?: (chatId: string) => void,
    onTitleGenerated?: (title: string) => void,
    onDone?: (chatId: string, messageCount: number) => void,
    onError?: (error: string) => void,
    onToolStart?: (event: {
      tool_name: string;
      display_name: string;
      icon: string;
      symbol?: string;
      run_id: string;
      inputs: Record<string, unknown>;
    }) => void,
    onToolEnd?: (event: {
      tool_name: string;
      output: string;
      duration_ms: number;
      run_id: string;
      status: "success";
    }) => void,
    onToolError?: (event: {
      tool_name: string;
      error: string;
      duration_ms: number;
      run_id: string;
      status: "error";
    }) => void,
    onDeepEvent?: (event: DeepStreamEvent) => void,
    options?: {
      request_id?: string;
      title?: string;
      role?: string;
      source?: string;
      metadata?: Record<string, unknown>;
      tool_call?: ToolCall;
      // Agent Configuration
      agent_version?: "auto" | "v2" | "v3" | "v4-deep";
      onRouteSelected?: (event: RouteSelectedEvent) => void;
      onStreamMode?: (event: ResponseStreamModeEvent) => void;
      onRunState?: (event: RunStateEvent) => void;
      onClarificationRequired?: (event: ClarificationRequiredEvent) => void;
      onCancelled?: () => void;
      debug_enabled?: boolean; // Enable debug logging in backend
      // Language Configuration
      language?: "zh-CN" | "en"; // Response language (default: zh-CN)
      // Symbol Context (takes priority over DB ui_state, eliminates race condition)
      current_symbol?: string;
    },
  ): () => void {
    const url = `${API_BASE_URL}/api/chat/stream`;
    const controller = new AbortController();

    const makeStreamRequest = async () => {
      return fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(options?.debug_enabled ? { "X-Debug": "true" } : {}),
        },
        body: JSON.stringify({
          message,
          request_id: options?.request_id ?? createRequestId(),
          chat_id: chatId,
          title: options?.title,
          role: options?.role ?? "user",
          source: options?.source ?? "user",
          metadata: options?.metadata,
          tool_call: options?.tool_call,
          // Agent Configuration
          agent_version: options?.agent_version ?? "auto",
          // Language Configuration
          language: options?.language ?? "zh-CN",
          // Symbol Context (priority over DB ui_state)
          current_symbol: options?.current_symbol,
        }),
        signal: controller.signal,
      });
    };

    // Helper to process the stream response
    const processStream = async (response: Response) => {
      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("Response body is not readable");
      }

      const decoder = new TextDecoder();
      let buffer = "";
      const lastSequenceByStream = new Map<string, number>();

      for (;;) {
        const { done, value } = await reader.read();

        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const messages = buffer.split("\n\n");
        buffer = messages.pop() || "";

        for (const message of messages) {
          if (message.startsWith("data: ")) {
            const parsed: unknown = JSON.parse(message.slice(6));
            if (isAgentEventEnvelope(parsed)) {
              const previous =
                lastSequenceByStream.get(parsed.stream_id ?? parsed.run_id) ??
                0;
              if (parsed.sequence <= previous) {
                continue;
              }
              lastSequenceByStream.set(
                parsed.stream_id ?? parsed.run_id,
                parsed.sequence,
              );
            }
            let data;
            try {
              data = normalizeAgentStreamEvent(parsed);
            } catch {
              console.warn("Ignored malformed SSE event");
              continue;
            }

            if (data.type === "route_selected") {
              options?.onRouteSelected?.(data);
            } else if (data.type === "response_stream_mode") {
              options?.onStreamMode?.(data);
            } else if (data.type === "run_state") {
              options?.onRunState?.(data);
            } else if (data.type === "clarification_required") {
              options?.onClarificationRequired?.(data);
            } else if (
              data.type === "chat_created" &&
              onChatCreated &&
              data.chat_id
            ) {
              onChatCreated(data.chat_id);
            } else if (data.type === "chunk" && data.content) {
              onChunk(data.content);
            } else if (
              data.type === "title_generated" &&
              onTitleGenerated &&
              data.title
            ) {
              onTitleGenerated(data.title);
            } else if (data.type === "done" && onDone && data.chat_id) {
              onDone(data.chat_id, data.message_count || 0);
            } else if (data.type === "error" && onError) {
              console.error("SSE error:", data.error);
              onError(data.error || "Unknown error");
            } else if (data.type === "cancelled") {
              options?.onCancelled?.();
            } else if (data.type === "tool_start" && onToolStart) {
              onToolStart({
                tool_name: data.tool_name,
                display_name: data.display_name,
                icon: data.icon,
                symbol: data.symbol,
                run_id: data.run_id,
                inputs: data.inputs,
              });
            } else if (data.type === "tool_end" && onToolEnd) {
              onToolEnd({
                tool_name: data.tool_name,
                output: data.output,
                duration_ms: data.duration_ms,
                run_id: data.run_id,
                status: "success",
              });
            } else if (data.type === "tool_error" && onToolError) {
              onToolError({
                tool_name: data.tool_name,
                error: data.error,
                duration_ms: data.duration_ms,
                run_id: data.run_id,
                status: "error",
              });
            } else if (data.type?.startsWith("deep_") && onDeepEvent) {
              onDeepEvent(data as DeepStreamEvent);
            }
          }
        }
      }
    };

    void (async () => {
      try {
        const response = await makeStreamRequest();

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        await processStream(response);
      } catch (error) {
        const errorName =
          typeof error === "object" &&
          error !== null &&
          "name" in error &&
          typeof error.name === "string"
            ? error.name
            : null;
        if (errorName === "AbortError") {
          options?.onCancelled?.();
        } else if (error instanceof Error && onError) {
          onError(error.message);
        }
      }
    })();

    return () => {
      controller.abort();
    };
  },
};

export const agentRunService = {
  async getRun(runId: string): Promise<AgentRun> {
    const response = await api.get<AgentRun>(`/api/runs/${runId}`);
    return response.data;
  },

  async listChatRuns(chatId: string, limit: number = 20): Promise<AgentRun[]> {
    const response = await api.get<AgentRun[]>("/api/runs", {
      params: { chat_id: chatId, limit },
    });
    return response.data;
  },
};

// ===== Market Status API =====
export const marketStatusService = {
  /**
   * Get current market status (open/closed, current session)
   */
  async getMarketStatus(): Promise<MarketStatus> {
    const response = await api.get<MarketStatus>("/api/market/status");
    return response.data;
  },
};
