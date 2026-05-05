/**
 * Individual chat item in sidebar.
 * Displays title, preview, and timestamp with glassmorphism design.
 */

import { MessageSquare, Clock, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { Chat } from "../../types/api";
import { Translated } from "../Translated";
import { formatDate, localizeTimestamps } from "../../utils/timeFormatter";

interface ChatListItemProps {
  chat: Chat;
  isActive: boolean;
  onClick: () => void;
  onDelete: (chatId: string) => void;
}

export function ChatListItem({
  chat,
  isActive,
  onClick,
  onDelete,
}: ChatListItemProps) {
  const { t, i18n } = useTranslation(['chat', 'common']);

  // Format timestamp
  const formatTime = (timestamp: string | null) => {
    if (!timestamp) return t('chat:sidebar.noMessages');

    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return t('chat:sidebar.justNow');
    if (diffMins < 60) return t('chat:sidebar.minutesAgo', { count: diffMins });
    if (diffHours < 24) return t('chat:sidebar.hoursAgo', { count: diffHours });
    if (diffDays < 7) return t('chat:sidebar.daysAgo', { count: diffDays });

    return formatDate(date, i18n.language, {
      month: "short",
      day: "numeric",
    });
  };

  return (
    <div
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      className={`
        w-full px-3 py-3 rounded-xl text-left transition-all duration-200
        group relative cursor-pointer
        ${
          isActive
            ? "bg-gradient-to-r from-blue-500/20 to-indigo-500/20 border border-blue-300/50 shadow-lg"
            : "hover:bg-white/60 border border-transparent hover:border-gray-200/50"
        }
      `}
    >
      {/* Active indicator */}
      {isActive && (
        <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-8 bg-gradient-to-b from-blue-500 to-indigo-500 rounded-r-full" />
      )}

      <div className="flex items-start gap-3">
        {/* Icon */}
        <div
          className={`
          flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center
          transition-all duration-200
          ${
            isActive
              ? "bg-gradient-to-br from-blue-500 to-indigo-500 text-white shadow-md"
              : "bg-gray-100/80 text-gray-600 group-hover:bg-gray-200/80"
          }
        `}
        >
          <MessageSquare size={18} />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Title */}
          <h3
            className={`
            text-sm font-semibold mb-1 truncate
            ${isActive ? "text-gray-900" : "text-gray-800 group-hover:text-gray-900"}
          `}
          >
            <Translated
              text={chat.title}
              precomputed={chat.title_zh ?? null}
              render={(translated) =>
                localizeTimestamps(translated, i18n.language, {
                  hour: "2-digit",
                  minute: "2-digit",
                })
              }
            />
          </h3>

          {/* Preview */}
          {chat.last_message_preview && (
            <p className="text-xs text-gray-600 line-clamp-2 mb-1">
              <Translated
                text={chat.last_message_preview}
                precomputed={chat.last_message_preview_zh ?? null}
              />
            </p>
          )}

          {/* Timestamp & Actions */}
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1 text-xs text-gray-500">
              <Clock size={12} />
              <span>{formatTime(chat.last_message_at || null)}</span>
            </div>

            {/* Delete Button */}
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete(chat.chat_id);
              }}
              className="opacity-0 group-hover:opacity-100 p-1 hover:bg-red-50 rounded transition-all"
              title={t('chat:sidebar.deleteChat')}
            >
              <Trash2 size={14} className="text-gray-400 hover:text-red-500" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
