/**
 * Hook for fetching portfolio agent chat history.
 * Transforms portfolio API response to match chat structure.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../services/api";

interface Message {
  message_id: string;
  chat_id: string;
  role: string;
  content: string;
  /** Server-precomputed Chinese translation. Null when the writer didn't
   *  translate this message (or translation failed cleanly via post-fix
   *  fallback that no longer dirties the field with English). */
  content_zh?: string | null;
  timestamp: string;
  metadata?: {
    symbol?: string;
    analysis_id?: string;
    trend_direction?: string;
  };
}

interface Chat {
  chat_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  is_archived: boolean;
  last_message_preview?: string;
  last_message_preview_zh?: string | null;
  last_message_at?: string;
}

interface ChatsResponse {
  chats: Chat[];
  total: number;
  page: number;
  page_size: number;
}

interface SymbolChat {
  chat_id: string;
  symbol: string;
  title: string;
  message_count: number;
  messages: Message[];
  latest_timestamp: string;
}

interface PortfolioChatHistoryResponse {
  chats: SymbolChat[];
}

async function fetchPortfolioChats(date?: string, analysisType?: string): Promise<ChatsResponse> {
  // Use apiClient (axios) for automatic auth token injection
  const params: Record<string, string> = {};
  if (date) {
    params.date = date;
  }
  if (analysisType) {
    params.analysis_type = analysisType;
  }

  const response = await apiClient.get<PortfolioChatHistoryResponse>(
    "/api/portfolio/chat-history",
    { params }
  );

  const data = response.data;

  // Transform to chat structure. Prefer content_zh for both the visible
  // preview and the precomputed translation slot — when zh is present we
  // can render it directly without triggering a /api/translate round-trip
  // from ChatListItem's <Translated> wrapper.
  const chats: Chat[] = data.chats.map((symbolChat) => {
    const last = symbolChat.messages[symbolChat.messages.length - 1];
    const lastEn = last?.content ?? "";
    const lastZh = last?.content_zh ?? null;
    return {
      chat_id: symbolChat.chat_id,
      title: symbolChat.title,
      created_at: symbolChat.latest_timestamp,
      updated_at: symbolChat.latest_timestamp,
      is_archived: false,
      last_message_preview: lastEn.substring(0, 100),
      last_message_preview_zh: lastZh ? lastZh.substring(0, 100) : null,
      last_message_at: symbolChat.latest_timestamp,
    };
  });

  return {
    chats,
    total: chats.length,
    page: 1,
    page_size: chats.length,
  };
}

export function usePortfolioChats(date?: string, analysisType?: string) {
  return useQuery({
    queryKey: ["portfolio-chats", date, analysisType],
    queryFn: () => fetchPortfolioChats(date, analysisType),
    refetchInterval: 30000, // Refetch every 30 seconds
  });
}

/**
 * Delete a portfolio agent chat.
 * Uses /api/portfolio/chats/{chatId} endpoint.
 */
async function deletePortfolioChat(chatId: string): Promise<void> {
  // Use apiClient (axios) for automatic auth token injection
  await apiClient.delete(`/api/portfolio/chats/${chatId}`);
}

/**
 * Hook for deleting portfolio agent chats.
 */
export function useDeletePortfolioChat() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deletePortfolioChat,
    onSuccess: () => {
      // Invalidate portfolio chats query to refetch the list
      queryClient.invalidateQueries({ queryKey: ["portfolio-chats"] });
    },
  });
}
