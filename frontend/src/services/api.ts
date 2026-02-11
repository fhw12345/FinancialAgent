import axios from "axios";
import type {
  HealthResponse,
  ChatListResponse,
  ChatDetailResponse,
  UpdateUIStateRequest,
  Chat,
  StreamEvent,
  DeepStreamEvent,
  MarketStatus,
} from "../types/api";
import type {
  UserProfile,
  TransactionHistoryResponse,
  CreditAdjustmentRequest,
  CreditAdjustmentResponse,
} from "../types/credits";
import {
  refreshTokenIfNeeded,
  retryWithRefreshToken,
  performTokenRefresh,
} from "./tokenRefresh";

// Configure axios with base URL
// In production, use empty string for relative URLs (nginx proxy)
// In development, use localhost
const api = axios.create({
  baseURL:
    import.meta.env.VITE_API_URL !== undefined
      ? import.meta.env.VITE_API_URL
      : import.meta.env.MODE === "production"
        ? ""
        : "http://localhost:8000",
  timeout: 30000, // 30 seconds for analysis requests
  headers: {
    "Content-Type": "application/json",
  },
});

// Export the configured axios instance for use in other services
export const apiClient = api;

// Request interceptor for authentication with auto-refresh
api.interceptors.request.use(
  async (config) => {
    return await refreshTokenIfNeeded(config);
  },
  (error) => {
    return Promise.reject(error);
  },
);

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => {
    return response;
  },
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      const newToken = await retryWithRefreshToken();

      if (newToken) {
        // Retry original request with new token
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return api(originalRequest);
      }
    }

    return Promise.reject(error);
  },
);

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
    const response = await api.get("/api/health/mongodb");
    return response.data;
  },

  async getRedisHealth(): Promise<{
    connected: boolean;
    [key: string]: unknown;
  }> {
    const response = await api.get("/api/health/redis");
    return response.data;
  },

  async getReadiness(): Promise<{ ready: boolean; [key: string]: unknown }> {
    const response = await api.get("/api/health/ready");
    return response.data;
  },

  async getLiveness(): Promise<{ alive: boolean; [key: string]: unknown }> {
    const response = await api.get("/api/health/live");
    return response.data;
  },
};

// ===== Persistent Chat API =====
export const chatService = {
  /**
   * List all chats for the authenticated user
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
      title?: string;
      role?: string;
      source?: string;
      metadata?: any; // Analysis metadata for overlays
      tool_call?: any; // Tool invocation metadata for collapsible UI wrapper
      // Agent Configuration
      agent_version?: "v2" | "v3" | "v4-deep"; // v2: simple chat, v3: ReAct agent, v4-deep: deep analysis
      // LLM Configuration
      model?: string;
      thinking_enabled?: boolean;
      max_tokens?: number;
      debug_enabled?: boolean; // Enable debug logging in backend
      // Language Configuration
      language?: "zh-CN" | "en"; // Response language (default: zh-CN)
      // Symbol Context (takes priority over DB ui_state, eliminates race condition)
      current_symbol?: string;
    },
  ): () => void {
    const baseURL =
      import.meta.env.VITE_API_URL !== undefined
        ? import.meta.env.VITE_API_URL
        : import.meta.env.MODE === "production"
          ? ""
          : "http://localhost:8000";

    const url = `${baseURL}/api/chat/stream`;
    const controller = new AbortController();

    // Helper to make the streaming request
    const makeStreamRequest = async (accessToken: string | null) => {
      return fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
          ...(options?.debug_enabled ? { "X-Debug": "true" } : {}),
        },
        body: JSON.stringify({
          message,
          chat_id: chatId,
          title: options?.title,
          role: options?.role ?? "user",
          source: options?.source ?? "user",
          metadata: options?.metadata,
          tool_call: options?.tool_call,
          // Agent Configuration
          agent_version: options?.agent_version ?? "v3", // Default to v3 (ReAct agent)
          // LLM Configuration
          model: options?.model ?? "qwen-plus",
          thinking_enabled: options?.thinking_enabled ?? false,
          max_tokens: options?.max_tokens ?? 3000,
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

      while (true) {
        const { done, value } = await reader.read();

        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const messages = buffer.split("\n\n");
        buffer = messages.pop() || "";

        for (const message of messages) {
          if (message.startsWith("data: ")) {
            const data: StreamEvent = JSON.parse(message.slice(6));

            if (
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
            } else if (
              data.type?.startsWith("deep_") &&
              onDeepEvent
            ) {
              onDeepEvent(data as DeepStreamEvent);
            }
          }
        }
      }
    };

    // Main request flow with 401 retry
    void (async () => {
      try {
        let response = await makeStreamRequest(
          localStorage.getItem("access_token"),
        );

        // Handle 401 - try refresh token and retry
        if (response.status === 401) {
          console.log(
            "[Streaming] Got 401, attempting token refresh and retry...",
          );
          const newToken = await performTokenRefresh();

          if (newToken) {
            // Retry with new token
            response = await makeStreamRequest(newToken);
          } else {
            // Refresh failed - redirect to login
            console.log(
              "[Streaming] Token refresh failed, redirecting to login",
            );
            window.location.href = "/login";
            return;
          }
        }

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        await processStream(response);
      } catch (error) {
        if (
          error instanceof Error &&
          error.name !== "AbortError" &&
          onError
        ) {
          onError(error.message);
        }
      }
    })();

    return () => {
      controller.abort();
    };
  },
};

// ===== Credit System API =====
export const creditService = {
  /**
   * Get current user profile with credit balance
   */
  async getUserProfile(): Promise<UserProfile> {
    const response = await api.get<UserProfile>("/api/users/me");
    return response.data;
  },

  /**
   * Get paginated transaction history for current user
   */
  async getTransactionHistory(
    page: number = 1,
    pageSize: number = 20,
    status?: string,
  ): Promise<TransactionHistoryResponse> {
    const response = await api.get<TransactionHistoryResponse>(
      "/api/credits/transactions",
      {
        params: {
          page,
          page_size: pageSize,
          ...(status ? { status } : {}),
        },
      },
    );
    return response.data;
  },

  /**
   * Admin: Manually adjust user credits
   */
  async adjustCredits(
    request: CreditAdjustmentRequest,
  ): Promise<CreditAdjustmentResponse> {
    const response = await api.post<CreditAdjustmentResponse>(
      "/api/admin/credits/adjust",
      request,
    );
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
