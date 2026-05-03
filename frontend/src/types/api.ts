export interface HealthResponse {
  status: "ok" | "degraded" | "error";
  environment: string;
  version: string;
  timestamp: string;
  kubernetes?: {
    running_in_kubernetes: boolean;
    pod_name?: string;
    node_name?: string;
    namespace?: string;
    node_pool?: string;
    resources?: {
      requests: {
        cpu: string;
        memory: string;
      };
      limits: {
        cpu: string;
        memory: string;
      };
    };
  };
  dependencies: {
    mongodb: {
      connected: boolean;
      version?: string;
      database?: string;
      error?: string;
    };
    redis: {
      connected: boolean;
      version?: string;
      memory_usage?: string;
      error?: string;
    };
  };
  configuration: {
    langfuse_enabled: boolean;
    database_name: string;
  };
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  chart_url?: string;
  analysis_data?: Record<string, unknown>;
  _id?: string | number; // Optional ID for frontend tracking
  tool_call?: ToolCall;
  tool_progress?: {
    toolName: string;
    displayName: string;
    icon: string;
    status: "running" | "success" | "error";
    symbol?: string;
    inputs?: Record<string, unknown>;
    output?: string;
    error?: string;
    durationMs?: number;
  };
  deep_events?: DeepStreamEvent[]; // Persisted accordion events for restore
}

export interface ChatRequest {
  message: string;
  session_id?: string;
  current_symbol?: string; // Symbol from UI, takes priority over DB ui_state
}

export interface ChatResponse {
  response: string;
  session_id: string;
  message_count: number;
  chart_url?: string;
  analysis_data?: Record<string, unknown>;
}

export interface FibonacciData {
  symbol: string;
  timeframe: string;
  trend_direction: "uptrend" | "downtrend";
  swing_high: {
    price: number;
    date: string;
  };
  swing_low: {
    price: number;
    date: string;
  };
  fibonacci_levels: Array<{
    level: number;
    price: number;
    percentage: string;
  }>;
  confidence_score: number;
  analysis_summary: string;
}

export interface MacroData {
  vix_level: number;
  vix_interpretation: string;
  market_sentiment: "fearful" | "neutral" | "greedy";
  major_indices: Record<string, number>;
  sector_performance: Record<string, number>;
  overall_confidence: number;
}

export interface MarketStatus {
  is_open: boolean;
  current_session: "pre" | "regular" | "post" | "closed";
  next_open: string | null;
  next_close: string | null;
  timestamp: string;
}

export interface ErrorResponse {
  detail: string;
  error_code?: string;
}

// ===== Chat Types =====

export interface UIState {
  current_symbol?: string | null;
  current_company_name?: string | null;
  current_interval?: string;
  current_date_range?: {
    start?: string | null;
    end?: string | null;
  };
  active_overlays?: Record<string, Record<string, unknown>>;
}

export interface Chat {
  chat_id: string;
  title: string;
  is_archived: boolean;
  ui_state?: UIState;
  last_message_preview?: string | null;
  created_at: string;
  updated_at: string;
  last_message_at?: string | null;
}

export interface ChatListResponse {
  chats: Chat[];
  total: number;
  page: number;
  page_size: number;
}

// Tool invocation metadata for UI rendering
export interface ToolCall {
  tool_name: string;
  title: string;
  icon: string;
  symbol?: string;
  invoked_at: string;
  metadata?: Record<string, unknown>;
}

export interface Message {
  message_id: string;
  chat_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  source:
    | "user"
    | "llm"
    | "fibonacci"
    | "stochastic"
    | "macro"
    | "fundamentals"
    | "tool"; // Added 'tool' as a valid source
  timestamp: string;
  metadata?: Record<string, unknown>;
  tool_call?: ToolCall; // NEW: Tool invocation metadata for collapsible UI
}

export interface ChatDetailResponse {
  chat: Chat;
  messages: Message[];
}

export interface UpdateUIStateRequest {
  ui_state: UIState;
}

// ===== Stream Event Types =====

export type StreamEvent =
  | {
      type: "chat_created";
      chat_id: string;
    }
  | {
      type: "chunk";
      content: string;
    }
  | {
      type: "title_generated";
      title: string;
    }
  | {
      type: "done";
      chat_id: string;
      message_count?: number;
    }
  | {
      type: "error";
      error?: string;
    }
  | {
      type: "tool_start";
      tool_name: string;
      display_name: string;
      icon: string;
      inputs: Record<string, unknown>;
      symbol?: string;
      run_id: string;
      timestamp: string;
    }
  | {
      type: "tool_end";
      tool_name: string;
      output: string;
      duration_ms: number;
      run_id: string;
      status: "success";
      timestamp: string;
    }
  | {
      type: "tool_error";
      tool_name: string;
      error: string;
      duration_ms: number;
      run_id: string;
      status: "error";
      timestamp: string;
    }
  | {
      type: "tool_info";
      tool_executions: number;
      trace_id: string;
    }
  // ===== Deep Agent Events (v4-deep) =====
  | DeepStreamEvent;

// Deep agent structured lifecycle events for accordion tree UI
export type DeepStreamEvent =
  | {
      type: "deep_start";
      seq: number;
      timestamp: string;
      symbol: string;
      subagent_names: string[];
      enable_debate: boolean;
    }
  | {
      type: "deep_subagent_start";
      seq: number;
      timestamp: string;
      subagent_name: string;
      display_name: string;
      icon: string;
      tool_names: string[];
    }
  | {
      type: "deep_tool_start";
      seq: number;
      timestamp: string;
      subagent_name: string;
      tool_name: string;
      display_name: string;
      inputs: Record<string, unknown>;
    }
  | {
      type: "deep_tool_end";
      seq: number;
      timestamp: string;
      subagent_name: string;
      tool_name: string;
      status: "success" | "error";
      duration_ms: number;
      output_preview: string;
    }
  | {
      type: "deep_subagent_result";
      seq: number;
      timestamp: string;
      subagent_name: string;
      status: "success" | "error";
      duration_ms: number;
      result_summary: string;
      tool_count: number;
    }
  | {
      type: "deep_debate_start";
      seq: number;
      timestamp: string;
      round: number;
      max_rounds: number;
    }
  | {
      type: "deep_debate_round";
      seq: number;
      timestamp: string;
      round: number;
      has_concerns: boolean;
      summary: string;
    }
  | {
      type: "deep_rebuttal_start";
      seq: number;
      timestamp: string;
      round: number;
    }
  | {
      type: "deep_rebuttal_result";
      seq: number;
      timestamp: string;
      round: number;
      defense_summary: string;
      tool_count: number;
      duration_ms: number;
    }
  | {
      type: "deep_synthesis_start";
      seq: number;
      timestamp: string;
    }
  | {
      type: "deep_verdict";
      seq: number;
      timestamp: string;
      verdict_text: string;
      risk_level: string | null;
      tool_count: number;
      total_duration_ms: number;
    };
