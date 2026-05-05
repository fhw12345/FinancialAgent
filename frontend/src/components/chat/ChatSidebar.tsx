/**
 * Chat history sidebar with glassmorphism design.
 * Displays list of user's chats with create new chat button.
 */

import { useState, useMemo, memo } from "react";
import { useTranslation } from "react-i18next";
import { formatDate } from "../../utils/timeFormatter";
import {
  Plus,
  Archive,
  Loader2,
  AlertCircle,
  ChevronLeft,
  Calendar,
  X,
} from "lucide-react";
import { useChats, useDeleteChat } from "../../hooks/useChats";
import { usePortfolioChats, useDeletePortfolioChat } from "../../hooks/usePortfolioChats";
import { ChatListItem } from "./ChatListItem";
import { AnalysisTypeFilter } from "../portfolio/AnalysisTypeFilter";

interface ChatSidebarProps {
  activeChatId: string | null;
  onChatSelect: (chatId: string) => void;
  onNewChat: () => void;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  filterUserId?: string; // Optional: filter chats by user_id (e.g., "portfolio_agent")
  readOnly?: boolean; // Optional: hide "New Chat" button for read-only mode
  selectedDate?: string | null; // Optional: selected date for portfolio mode (YYYY-MM-DD)
  onDateChange?: (date: string | null) => void; // Optional: callback when date changes
  messageSortOrder?: "newest" | "oldest"; // Optional: controlled sort order for messages
  onMessageSortOrderChange?: (order: "newest" | "oldest") => void; // Optional: callback when sort changes
  analysisType?: string; // Optional: filter by analysis type ("individual" or "portfolio")
  onAnalysisTypeChange?: (type: string) => void; // Optional: callback when analysis type changes
}

export const ChatSidebar = memo(function ChatSidebar({
  activeChatId,
  onChatSelect,
  onNewChat,
  isCollapsed,
  onToggleCollapse,
  filterUserId,
  readOnly = false,
  selectedDate = null,
  onDateChange,
  messageSortOrder,
  onMessageSortOrderChange,
  analysisType,
  onAnalysisTypeChange,
}: ChatSidebarProps) {
  const { t, i18n } = useTranslation(['chat', 'common', 'portfolio']);
  const [showArchived, setShowArchived] = useState(false);
  // Use controlled sort order if provided, otherwise use internal state
  const [internalSortOrder, setInternalSortOrder] = useState<"newest" | "oldest">("newest");
  const sortOrder = messageSortOrder ?? internalSortOrder;
  const setSortOrder = onMessageSortOrderChange ?? setInternalSortOrder;

  // Fetch chats - use portfolio chats if filterUserId is portfolio_agent
  const isPortfolioMode = filterUserId === "portfolio_agent";
  const regularChatsQuery = useChats(1, 20, showArchived);
  const portfolioChatsQuery = usePortfolioChats(selectedDate || undefined, analysisType || undefined);

  const { data, isLoading, isError, error } = isPortfolioMode
    ? portfolioChatsQuery
    : regularChatsQuery;

  // Chats are always sorted by API (newest first) - no client-side sorting needed
  const sortedChats = useMemo(() => {
    return data?.chats ?? [];
  }, [data?.chats]);

  // Delete mutations - use portfolio delete for portfolio chats
  const { mutate: deleteRegularChat } = useDeleteChat();
  const { mutate: deletePortfolioChat } = useDeletePortfolioChat();

  const deleteChat = isPortfolioMode ? deletePortfolioChat : deleteRegularChat;

  const handleDeleteChat = (chatId: string) => {
    if (
      window.confirm(t('chat:sidebar.deleteConfirm'))
    ) {
      deleteChat(chatId, {
        onSuccess: () => {
          // If deleted chat was active, clear selection
          if (chatId === activeChatId) {
            onNewChat();
          }
        },
        onError: (error) => {
          alert(
            t('chat:sidebar.deleteFailed', {
              error: error instanceof Error ? error.message : t('common:errors.general')
            }),
          );
        },
      });
    }
  };

  // If collapsed, show minimal sidebar
  if (isCollapsed) {
    return (
      <aside className="w-12 h-full flex flex-col bg-gradient-to-b from-white/80 to-gray-50/80 backdrop-blur-xl border-l border-gray-200/50 items-center justify-center relative">
        <button
          onClick={onToggleCollapse}
          className="group relative"
          title={t('chat:sidebar.expandSidebar')}
        >
          {/* Vertical bar with hover effect */}
          <div className="w-1 h-16 bg-gradient-to-b from-blue-400 via-indigo-500 to-blue-600 rounded-full transition-all duration-300 group-hover:h-20 group-hover:w-1.5 group-hover:shadow-lg group-hover:shadow-blue-500/50" />
          {/* Chevron icon - always visible */}
          <div className="absolute inset-0 flex items-center justify-center">
            <ChevronLeft size={20} strokeWidth={2.5} className="text-white drop-shadow-md opacity-90 group-hover:opacity-100 group-hover:scale-110 transition-all duration-200" />
          </div>
        </button>
      </aside>
    );
  }

  return (
    <aside className="w-full h-full flex flex-col bg-gradient-to-b from-white/80 to-gray-50/80 backdrop-blur-xl relative">
      {/* Artistic Collapse Toggle - Vertical Bar Design */}
      <button
        onClick={onToggleCollapse}
        className="group absolute right-0 top-1/2 -translate-y-1/2 z-10"
        title={t('chat:sidebar.collapseSidebar')}
      >
        {/* Elegant vertical bar that peeks from edge */}
        <div className="relative flex items-center">
          <div className="w-1 h-16 bg-gradient-to-b from-blue-400 via-indigo-500 to-blue-600 rounded-l-full transition-all duration-300 group-hover:h-20 group-hover:w-1.5 group-hover:shadow-lg group-hover:shadow-blue-500/50" />
          {/* Chevron appears on hover */}
          <div className="absolute right-2 opacity-0 group-hover:opacity-100 transition-all duration-200 group-hover:-translate-x-1">
            <div className="bg-white/90 backdrop-blur-sm rounded-full p-1.5 shadow-md">
              <ChevronLeft size={14} strokeWidth={2.5} className="text-indigo-600" />
            </div>
          </div>
        </div>
      </button>

      {/* Header */}
      <div className="px-4 py-4 border-b border-gray-200/50">
        <h2 className="text-xl font-bold bg-gradient-to-r from-gray-900 via-blue-900 to-indigo-900 bg-clip-text text-transparent mb-3">
          {isPortfolioMode ? t('chat:sidebar.analysisHistory') : t('chat:sidebar.title')}
        </h2>

        {/* New Chat Button - Hidden in readOnly mode */}
        {!readOnly && (
          <button
            onClick={onNewChat}
            className="w-full px-4 py-2.5 bg-gradient-to-r from-blue-500 to-indigo-500 text-white font-semibold rounded-xl shadow-lg shadow-blue-500/30 hover:shadow-xl hover:shadow-blue-500/40 transition-all duration-200 flex items-center justify-center gap-2"
          >
            <Plus size={18} />
            {t('chat:sidebar.newChat')}
          </button>
        )}

        {/* Date Picker - Portfolio Mode Only */}
        {isPortfolioMode && onDateChange && (
          <div className={`${readOnly ? "" : "mt-2"} relative`}>
            <div className="flex items-center gap-2">
              <div className="flex-1 relative">
                <Calendar
                  size={16}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500"
                />
                <input
                  type="date"
                  value={selectedDate || ""}
                  onChange={(e) => onDateChange(e.target.value || null)}
                  className="w-full pl-9 pr-3 py-2 text-sm bg-white border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder={t('chat:sidebar.selectDate')}
                />
              </div>
              {selectedDate && (
                <button
                  onClick={() => onDateChange(null)}
                  className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
                  title={t('chat:sidebar.clearDate')}
                >
                  <X size={16} />
                </button>
              )}
            </div>
            {selectedDate && (
              <p className="text-xs text-gray-500 mt-1 px-1">
                {t('chat:sidebar.showingChatsFor')} {formatDate(selectedDate, i18n.language, { timeZone: "UTC" })}
              </p>
            )}
          </div>
        )}

        {/* Analysis Type Filter - Portfolio Mode Only */}
        {isPortfolioMode && onAnalysisTypeChange && (
          <div className="mt-2">
            <AnalysisTypeFilter
              selectedType={analysisType || ""}
              onTypeChange={onAnalysisTypeChange}
            />
          </div>
        )}

        {/* Message Sort Toggle - Portfolio Mode Only */}
        {isPortfolioMode && (
          <div className="mt-2 flex items-center gap-2">
            <span className="text-sm text-gray-500">{t('portfolio:chatSidebar.messageOrder')}:</span>
            <button
              onClick={() => setSortOrder(sortOrder === "newest" ? "oldest" : "newest")}
              className={`text-sm font-medium transition-colors ${
                sortOrder === "newest"
                  ? "text-blue-600"
                  : "text-gray-400 hover:text-gray-600"
              }`}
            >
              {t('portfolio:chatSidebar.newestOnTop')}
            </button>
          </div>
        )}

        {/* Archive Toggle */}
        <button
          onClick={() => setShowArchived(!showArchived)}
          className={`
            w-full ${readOnly || (isPortfolioMode && onDateChange) ? "mt-2" : readOnly ? "" : "mt-2"} px-4 py-2 text-sm font-medium rounded-lg transition-all
            ${
              showArchived
                ? "bg-blue-100/80 text-blue-700 border border-blue-200"
                : "bg-gray-100/80 text-gray-700 hover:bg-gray-200/80"
            }
            flex items-center justify-center gap-2
          `}
        >
          <Archive size={16} />
          {showArchived ? t('chat:sidebar.hideArchived') : t('chat:sidebar.showArchived')}
        </button>
      </div>

      {/* Chat List */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
        {isLoading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-6 h-6 text-blue-500 animate-spin" />
          </div>
        )}

        {isError && (
          <div className="px-4 py-6 text-center">
            <AlertCircle className="w-8 h-8 text-red-500 mx-auto mb-2" />
            <p className="text-sm text-red-600 font-medium">
              {t('chat:sidebar.failedToLoadChats')}
            </p>
            <p className="text-xs text-gray-500 mt-1">
              {error instanceof Error ? error.message : t('common:errors.general')}
            </p>
          </div>
        )}

        {data && data.chats.length === 0 && (
          <div className="px-4 py-8 text-center">
            <p className="text-sm text-gray-500">
              {showArchived ? t('chat:sidebar.noArchivedChats') : t('chat:sidebar.noChats')}
            </p>
            <p className="text-xs text-gray-400 mt-1">
              {t('chat:sidebar.startNewConversation')}
            </p>
          </div>
        )}

        {sortedChats.map((chat) => (
          <ChatListItem
            key={chat.chat_id}
            chat={chat}
            isActive={chat.chat_id === activeChatId}
            onClick={() => onChatSelect(chat.chat_id)}
            onDelete={handleDeleteChat}
          />
        ))}
      </div>

      {/* Footer with count */}
      {data && data.total > 0 && (
        <div className="px-4 py-3 border-t border-gray-200/50">
          <p className="text-xs text-gray-500 text-center">
            {t('chat:sidebar.chatsCount', { count: data.chats.length, total: data.total })}
          </p>
        </div>
      )}
    </aside>
  );
});
