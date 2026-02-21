/**
 * Hook for restoring chat state when selecting a previous conversation.
 * Loads messages from MongoDB and restores UI state (symbol, interval, overlays).
 */

import { useCallback } from "react";
import type { ChatMessage } from "../types/api";
import type { TimeInterval } from "../services/market";
import { parseBackendMessage } from "../utils/messageParser";

interface ChatRestoreCallbacks {
  setMessages: (messages: ChatMessage[]) => void;
  setCurrentSymbol: (symbol: string) => void;
  setCurrentCompanyName: (name: string) => void;
  setSelectedInterval: (interval: TimeInterval) => void;
  setSelectedDateRange: (range: { start: string; end: string }) => void;
  setChatId: (chatId: string | null) => void;
}

export function useChatRestoration(callbacks: ChatRestoreCallbacks) {
  const {
    setMessages,
    setCurrentSymbol,
    setCurrentCompanyName,
    setSelectedInterval,
    setSelectedDateRange,
    setChatId,
  } = callbacks;

  /**
   * Load chat and restore full UI state
   */
  const restoreChat = useCallback(
    async (chatId: string) => {
      try {
        // Import chatService dynamically to avoid circular deps
        const { chatService } = await import("../services/api");

        // Fetch chat detail with recent 50 messages (pagination for performance)
        const chatDetail = await chatService.getChatDetail(chatId, 50);

        // Convert backend Message[] to frontend ChatMessage[]
        const restoredMessages: ChatMessage[] =
          chatDetail.messages.map(parseBackendMessage);

        // Restore messages
        setMessages(restoredMessages);

        // Restore UI state from chat.ui_state (with default empty state)
        const uiState = chatDetail.chat.ui_state || {
          current_symbol: null,
          current_company_name: null,
          current_interval: "1d",
          current_date_range: { start: null, end: null },
          active_overlays: {},
        };

        console.log("🔄 Restoring chat UI state:", {
          chatId,
          symbol: uiState.current_symbol,
          companyName: uiState.current_company_name,
          interval: uiState.current_interval,
          dateRange: uiState.current_date_range,
          overlays: uiState.active_overlays,
        });

        // Always set symbol and company name (even if empty) to clear old state
        setCurrentSymbol(uiState.current_symbol || "");
        setCurrentCompanyName(uiState.current_company_name || "");

        console.log(
          "✅ Symbol restored to search bar:",
          uiState.current_symbol,
          uiState.current_company_name,
        );

        // Always set interval with fallback
        setSelectedInterval((uiState.current_interval as TimeInterval) || "1d");

        if (
          uiState.current_date_range?.start &&
          uiState.current_date_range?.end
        ) {
          setSelectedDateRange({
            start: uiState.current_date_range.start,
            end: uiState.current_date_range.end,
          });
        } else {
          setSelectedDateRange({ start: "", end: "" });
        }

        // TODO: Restore active_overlays when overlay state management is implemented

        // Set active chat for API calls
        setChatId(chatId);

        console.log("✅ Chat restored:", {
          chatId,
          messageCount: restoredMessages.length,
          symbol: uiState.current_symbol,
          interval: uiState.current_interval,
        });

        return restoredMessages;
      } catch (error) {
        console.error("❌ Failed to restore chat:", error);

        // Show user-friendly error message
        setMessages([
          {
            role: "assistant",
            content:
              "⚠️ Failed to restore this chat. The data may be corrupted or unavailable. Please try refreshing the page or start a new chat.",
            timestamp: new Date().toISOString(),
          },
        ]);

        // Clear state on error to prevent showing stale data
        setCurrentSymbol("");
        setCurrentCompanyName("");
        setSelectedDateRange({ start: "", end: "" });

        return undefined;
      }
    },
    [
      setMessages,
      setCurrentSymbol,
      setCurrentCompanyName,
      setSelectedInterval,
      setSelectedDateRange,
      setChatId,
    ],
  );

  return { restoreChat };
}
