/**
 * useAnalysis Hook
 *
 * SIMPLIFIED VERSION:
 * - User chat messages → LLM (no pattern matching)
 * - Button clicks → Direct analysis endpoints
 */

import { flushSync } from "react-dom";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { analysisService } from "../../services/analysis";
import { chatService } from "../../services/api";
import { chatKeys } from "../../hooks/useChats";
import { useOptimisticCreditDeduction, creditKeys } from "../../hooks/useCredits";
import {
  formatBalanceSheetResponse,
  formatCashFlowResponse,
  formatCompanyOverviewResponse,
  formatFibonacciResponse,
  formatMacroResponse,
  formatMarketMoversResponse,
  formatNewsSentimentResponse,
  formatFundamentalsResponse,
  formatStochasticResponse,
} from "./analysisFormatters";
import { calculateDateRange } from "../../utils/dateRangeCalculator";
import {
  extractFibonacciMetadata,
  extractStochasticMetadata,
} from "../../utils/analysisMetadataExtractor";
import { createToolCall, TOOL_REGISTRY, type ToolName } from "../../constants/toolRegistry";
import type { ModelSettings } from "../../types/models";
import type { DeepStreamEvent } from "../../types/api";
import i18n from "../../i18n";

// Formatting functions moved to analysisFormatters.ts

// Chat hook - streams LLM responses in real-time
export const useAnalysis = (
  currentSymbol: string | null, // Used for symbol context injection (takes priority over DB)
  _selectedDateRange: { start: string; end: string },
  setMessages: (updater: (prevMessages: any[]) => any[]) => void,
  _setSelectedDateRange: (range: { start: string; end: string }) => void,
  _selectedInterval?: string,
  chatId?: string | null,
  setChatId?: (id: string) => void,
  modelSettings?: ModelSettings,
  agentMode?: "v2" | "v3" | "v4-deep",
  onDeepEvent?: (event: DeepStreamEvent) => void,
) => {
  const queryClient = useQueryClient();
  const optimisticDeduction = useOptimisticCreditDeduction();

  const mutation = useMutation({
    mutationKey: ["chat", chatId],
    mutationFn: async (userMessage: string) => {
      // Input validation
      const trimmed = userMessage.trim();

      if (!trimmed) {
        throw new Error("Message cannot be empty");
      }

      if (trimmed.length > 5000) {
        throw new Error("Message too long. Maximum 5000 characters allowed.");
      }

      // Check for potential XSS patterns (additional safety layer)
      if (/<script|javascript:|onerror=/i.test(trimmed)) {
        throw new Error("Invalid characters detected in message");
      }

      // Add user message immediately
      const userMessageObj = {
        role: "user" as const,
        content: userMessage,
        timestamp: new Date().toISOString(),
      };

      // Create placeholder for streaming assistant message
      const assistantMessageId = Date.now();
      const assistantMessageObj = {
        role: "assistant" as const,
        content: "",
        timestamp: new Date().toISOString(),
        _id: assistantMessageId,
      };

      setMessages((prev) => [...prev, userMessageObj, assistantMessageObj]);

      // Optimistically deduct credits (10 credits estimated cost)
      const { rollback } = optimisticDeduction.deduct(10.0);

      // Local accumulator to avoid race conditions
      let accumulatedContent = "";

      // Stream response using persistent MongoDB endpoint
      return new Promise((resolve, reject) => {
        chatService.sendMessageStreamPersistent(
          userMessage,
          chatId || null,
          (chunk: string) => {
            // Accumulate content locally (SAFE - no race condition)
            accumulatedContent += chunk;

            // Use flushSync to force immediate render of each chunk
            flushSync(() => {
              setMessages((prev) =>
                prev.map((msg: any) =>
                  msg._id === assistantMessageId
                    ? { ...msg, content: accumulatedContent }
                    : msg,
                ),
              );
            });
          },
          (newChatId: string) => {
            // Chat created callback - save new chat ID
            if (setChatId) {
              setChatId(newChatId);
            }
            // Don't invalidate here - wait for stream completion to avoid duplicate requests
          },
          (title: string) => {
            // Title generated callback - could update UI if needed
            console.log("📝 Chat title generated:", title);
          },
          () => {
            // Stream complete - use accumulated content (SAFE)
            resolve({ type: "chat", content: accumulatedContent });
            // Invalidate chat list ONCE after stream completes
            void queryClient.invalidateQueries({ queryKey: chatKeys.lists() });
            // Refresh credits to show actual cost deducted by backend
            void queryClient.invalidateQueries({ queryKey: creditKeys.profile() });
          },
          (error: string) => {
            // Error callback - rollback optimistic deduction
            console.error("❌ Streaming error:", error);
            rollback();
            setMessages((prev) =>
              prev.map((msg: any) =>
                msg._id === assistantMessageId
                  ? {
                      ...msg,
                      content: `❌ **Error**: ${error}`,
                    }
                  : msg,
              ),
            );
            reject(new Error(error));
          },
          // Tool event callbacks (agent mode v3 only)
          (event) => {
            // Tool started - add tool progress message
            const toolProgressMessage = {
              role: "assistant" as const,
              content: "",
              timestamp: new Date().toISOString(),
              _id: `tool_${event.run_id}`,
              tool_progress: {
                toolName: event.tool_name,
                displayName: event.display_name,
                icon: event.icon,
                status: "running" as const,
                symbol: event.symbol,
                inputs: event.inputs,
              },
            };

            setMessages((prev) => {
              // Find and preserve assistant placeholder (may have accumulated content)
              const placeholder = prev.find(msg => msg._id === assistantMessageId);
              const withoutPlaceholder = prev.filter(msg => msg._id !== assistantMessageId);

              // Insert tool message, then re-add placeholder at end (preserves streamed content)
              return [...withoutPlaceholder, toolProgressMessage, placeholder || assistantMessageObj];
            });
          },
          (event) => {
            // Tool completed successfully - update the tool progress message
            setMessages((prev) =>
              prev.map((msg) =>
                msg._id === `tool_${event.run_id}` && msg.tool_progress
                  ? {
                      ...msg,
                      tool_progress: {
                        ...msg.tool_progress,
                        status: "success" as const,
                        output: event.output,
                        durationMs: event.duration_ms,
                      },
                    }
                  : msg,
              ),
            );
          },
          (event) => {
            // Tool failed - update the tool progress message with error
            setMessages((prev) =>
              prev.map((msg) =>
                msg._id === `tool_${event.run_id}` && msg.tool_progress
                  ? {
                      ...msg,
                      tool_progress: {
                        ...msg.tool_progress,
                        status: "error" as const,
                        error: event.error,
                        durationMs: event.duration_ms,
                      },
                    }
                  : msg,
              ),
            );
          },
          // Deep agent event callback (v4-deep only)
          onDeepEvent,
          // LLM Configuration options
          {
            model: modelSettings?.model ?? "qwen-plus",
            thinking_enabled: modelSettings?.thinking_enabled ?? false,
            max_tokens: modelSettings?.max_tokens ?? 3000,
            debug_enabled: modelSettings?.debug_enabled ?? false,
            agent_version: agentMode, // Pass agent mode (v2/v3/v4-deep)
            // Language configuration - get from i18n
            language: (i18n.language === "zh-CN" || i18n.language === "en" ? i18n.language : "zh-CN") as "zh-CN" | "en",
            // Symbol context - takes priority over DB ui_state, eliminates race condition
            current_symbol: currentSymbol || undefined,
          },
        );
      });
    },
  });

  return mutation;
};

// Button analysis hook - direct API calls
export const useButtonAnalysis = (
  currentSymbol: string | null,
  selectedDateRange: { start: string; end: string },
  setMessages: (updater: (prevMessages: any[]) => any[]) => void,
  _setSelectedDateRange: (range: { start: string; end: string }) => void,
  selectedInterval?: string,
  chatId?: string | null,
  setChatId?: (id: string) => void,
) => {
  const queryClient = useQueryClient();

  return useMutation({
    // Note: Single mutation instance handles all analysis types
    // Deduplication happens automatically via isPending state
    mutationKey: [
      "button-analysis",
      currentSymbol,
      selectedInterval,
      selectedDateRange.start,
      selectedDateRange.end,
    ],
    mutationFn: async (
      analysisType:
        | "fibonacci"
        | "macro"
        | "company_overview"
        | "stochastic"
        | "cash_flow"
        | "balance_sheet"
        | "news_sentiment"
        | "market_movers",
    ) => {
      let response;

      // Title mapping for different analysis types
      const titleMap = {
        fibonacci: "Fibonacci Analysis",
        macro: "Macro Sentiment",
        company_overview: "Company Overview",
        stochastic: "Stochastic Analysis",
        cash_flow: "Cash Flow",
        balance_sheet: "Balance Sheet",
        news_sentiment: "News Sentiment",
        market_movers: "Market Movers",
      };

      const analysisTitle = titleMap[analysisType];
      const chatTitle = currentSymbol
        ? `${currentSymbol} ${analysisTitle}`
        : analysisTitle;

      // Source matches analysis type for MongoDB filtering
      const sourceType = "tool"; // All analysis types use 'tool' source

      switch (analysisType) {
        case "fibonacci": {
          if (!currentSymbol)
            throw new Error("Please select a stock symbol first.");

          // Calculate date range using shared utility
          const dateRange = calculateDateRange(
            selectedDateRange,
            (selectedInterval as "1d" | "1w" | "1mo") || "1d",
          );

          const result = await analysisService.fibonacciAnalysis({
            symbol: currentSymbol,
            start_date: dateRange.start,
            end_date: dateRange.end,
            timeframe: (selectedInterval || "1d") as "1d" | "1w" | "1mo",
          });
          response = {
            type: "fibonacci",
            content: formatFibonacciResponse(result),
            // Store only compact metadata, not full price history
            analysis_data: extractFibonacciMetadata(result),
          };
          break;
        }

        case "macro": {
          const result = await analysisService.macroSentimentAnalysis({});
          response = { type: "macro", content: formatMacroResponse(result) };
          break;
        }

        case "company_overview": {
          if (!currentSymbol)
            throw new Error("Please select a stock symbol first.");
          const result = await analysisService.companyOverview({
            symbol: currentSymbol,
          });
          response = {
            type: "company_overview",
            content: formatCompanyOverviewResponse(result),
          };
          break;
        }

        case "stochastic": {
          if (!currentSymbol)
            throw new Error("Please select a stock symbol first.");

          // Calculate date range using shared utility
          const dateRange = calculateDateRange(
            selectedDateRange,
            (selectedInterval as "1d" | "1w" | "1mo") || "1d",
          );

          const result = await analysisService.stochasticAnalysis({
            symbol: currentSymbol,
            start_date: dateRange.start,
            end_date: dateRange.end,
            timeframe: (selectedInterval as "1d" | "1w" | "1mo") || "1d",
            k_period: 14,
            d_period: 3,
          });
          response = {
            type: "stochastic",
            content: formatStochasticResponse(result),
            // Store only compact metadata, not full K/D arrays
            analysis_data: extractStochasticMetadata(result),
          };
          break;
        }

        case "cash_flow": {
          if (!currentSymbol)
            throw new Error("Please select a stock symbol first.");
          const result = await analysisService.cashFlow({
            symbol: currentSymbol,
          });
          response = {
            type: "cash_flow",
            content: formatCashFlowResponse(result),
          };
          break;
        }

        case "balance_sheet": {
          if (!currentSymbol)
            throw new Error("Please select a stock symbol first.");
          const result = await analysisService.balanceSheet({
            symbol: currentSymbol,
          });
          response = {
            type: "balance_sheet",
            content: formatBalanceSheetResponse(result),
          };
          break;
        }

        case "news_sentiment": {
          if (!currentSymbol)
            throw new Error("Please select a stock symbol first.");
          const result = await analysisService.newsSentiment({
            symbol: currentSymbol,
          });
          response = {
            type: "news_sentiment",
            content: formatNewsSentimentResponse(result),
          };
          break;
        }

        case "market_movers": {
          const result = await analysisService.marketMovers();
          response = {
            type: "market_movers",
            content: formatMarketMoversResponse(result),
          };
          break;
        }
      }

      // Save to MongoDB using streaming endpoint (analysis sources skip LLM)
      if (response) {
        return new Promise((resolve, reject) => {
          // Get tool metadata for user message
          const toolInfo = TOOL_REGISTRY[analysisType as ToolName];
          const toolTitle = toolInfo?.title || analysisType;
          const toolIcon = toolInfo?.icon || "🔧";

          // Create user message describing the action
          const userMessage = currentSymbol
            ? `${toolIcon} Get ${toolTitle} for ${currentSymbol}`
            : `${toolIcon} Get ${toolTitle}`;

          // Track chatId across nested calls to avoid creating duplicate chats
          let activeChatId = chatId;
          let userMessageSaved = false;

          // First, save user message (the trigger)
          chatService.sendMessageStreamPersistent(
            userMessage,
            activeChatId || null,
            () => {},
            (newChatId: string) => {
              // Capture new chat ID for use in second call
              activeChatId = newChatId;
              if (setChatId) {
                setChatId(newChatId);
              }
            },
            () => {},
            () => {
              // User message saved successfully
              userMessageSaved = true;

              // Now save assistant response
              chatService.sendMessageStreamPersistent(
                response.content,
                activeChatId || null,
                () => {},
                (newChatId: string) => {
                  if (setChatId) {
                    setChatId(newChatId);
                  }
                },
                () => {},
                () => {
                  // Both messages saved - invalidate queries
                  resolve(response);
                  void queryClient.invalidateQueries({
                    queryKey: chatKeys.lists(),
                  });
                  void queryClient.invalidateQueries({
                    queryKey: creditKeys.profile(),
                  });
                },
                (error: string) => {
                  // Assistant message save failed - show error to user
                  console.error("❌ Failed to save assistant message:", error);

                  // Show user-visible error
                  setMessages((prev) => [
                    ...prev,
                    {
                      role: "assistant",
                      content: `⚠️ **Warning**: Analysis completed but failed to save to chat history. Error: ${error}`,
                      timestamp: new Date().toISOString(),
                    },
                  ]);

                  // Still resolve with response data (analysis succeeded even if save failed)
                  resolve(response);
                },
                undefined, // onToolStart
                undefined, // onToolEnd
                undefined, // onToolError
                undefined, // onDeepEvent
                {
                  title: chatTitle,
                  role: "assistant",
                  source: sourceType,
                  metadata: { raw_data: response.analysis_data },
                  tool_call: createToolCall(
                    analysisType as ToolName,
                    currentSymbol || undefined,
                    response.analysis_data,
                  ),
                },
              );
            },
            (error: string) => {
              // User message save failed - this is more critical
              console.error("❌ Failed to save user message:", error);

              // Show user-visible error
              setMessages((prev) => [
                ...prev,
                {
                  role: "assistant",
                  content: `❌ **Error**: Failed to save analysis to chat. Please try again. Error: ${error}`,
                  timestamp: new Date().toISOString(),
                },
              ]);

              // Reject because user can't continue without saving the request
              reject(new Error(`Failed to save analysis: ${error}`));
            },
            undefined, // onToolStart
            undefined, // onToolEnd
            undefined, // onToolError
            undefined, // onDeepEvent
            {
              title: chatTitle,
              role: "user",
              source: "tool",  // Prevent agent invocation for button clicks
            },
          );
        });
      }

      return response;
    },
    onSuccess: (response: any) => {
      console.log("✅ Button analysis complete:", {
        type: response?.type,
        hasAnalysisData: !!response?.analysis_data,
        analysisData: response?.analysis_data,
      });

      // Add both user message and assistant response to frontend messages
      if (response) {
        // Get tool metadata
        const toolInfo = TOOL_REGISTRY[response.type as ToolName];
        const toolTitle = toolInfo?.title || response.type;
        const toolIcon = toolInfo?.icon || "🔧";

        // Create user message
        const userMessage = currentSymbol
          ? `${toolIcon} Get ${toolTitle} for ${currentSymbol}`
          : `${toolIcon} Get ${toolTitle}`;

        setMessages((prev) => [
          ...prev,
          // User message (trigger)
          {
            role: "user",
            content: userMessage,
            timestamp: new Date().toISOString(),
          },
          // Assistant message (tool response)
          {
            role: "assistant",
            content: response.content,
            timestamp: new Date().toISOString(),
            analysis_data: response.analysis_data,
            tool_call: createToolCall(
              response.type as ToolName,
              currentSymbol || undefined,
              response.analysis_data,
            ),
          },
        ]);

        console.log("📝 User message and assistant response added to state");
      }
    },
    onError: (error: any) => {
      const errorContent =
        error?.response?.data?.detail || error.message || "Unknown error";
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `❌ **Error**: ${errorContent}`,
          timestamp: new Date().toISOString(),
        },
      ]);
    },
  });
};
