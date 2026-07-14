/**
 * React Query hook for fetching portfolio agent chat details.
 * Uses the /api/portfolio/chats/{chat_id} endpoint.
 */

import { useQuery } from "@tanstack/react-query";
import type { ChatMessage, Chat } from "../types/api";
import { apiClient } from "../services/api";

interface PortfolioChatDetailResponse {
  chat: Chat;
  messages: ChatMessage[];
}

/**
 * Fetch portfolio agent chat detail from API
 */
async function fetchPortfolioChatDetail(chatId: string): Promise<PortfolioChatDetailResponse> {
  const response = await apiClient.get<PortfolioChatDetailResponse>(
    `/api/portfolio/chats/${chatId}`
  );

  return response.data;
}

/**
 * Hook to fetch portfolio agent chat detail with messages
 */
export function usePortfolioChatDetail(chatId: string | null) {
  return useQuery({
    queryKey: chatId ? ["portfolio-chat", chatId] : [],
    queryFn: () => {
      if (!chatId) {
        throw new Error("Chat ID is required");
      }
      return fetchPortfolioChatDetail(chatId);
    },
    enabled: !!chatId, // Only fetch when chatId is provided
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes
  });
}
