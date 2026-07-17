/**
 * ChatInput Component
 *
 * Provides a text input field and a send button for users to interact with the chatbot.
 */

import React from "react";
import { useTranslation } from "react-i18next";
import { Send, Square } from "lucide-react";

interface ChatInputProps {
  message: string;
  setMessage: (message: string) => void;
  onSendMessage: () => void;
  onCancelMessage: () => void;
  isPending: boolean;
  canCancel: boolean;
  currentSymbol: string | null;
}

export const ChatInput: React.FC<ChatInputProps> = ({
  message,
  setMessage,
  onSendMessage,
  onCancelMessage,
  isPending,
  canCancel,
  currentSymbol,
}) => {
  const { t } = useTranslation(["chat", "common"]);

  return (
    <div className="flex-shrink-0 border-t border-gray-200 px-4 py-3 bg-white">
      <div className="flex gap-3">
        <div className="flex-1">
          <input
            data-testid="chat-composer"
            type="text"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                onSendMessage();
              }
            }}
            placeholder={
              currentSymbol
                ? t("chat:input.placeholderWithSymbol", {
                    symbol: currentSymbol,
                  })
                : t("chat:input.placeholderWithoutSymbol")
            }
            className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-shadow"
            disabled={isPending}
          />
        </div>
        {canCancel ? (
          <button
            data-testid="chat-stop"
            type="button"
            onClick={onCancelMessage}
            className="rounded-xl bg-red-600 px-5 py-3 text-white shadow-sm transition-all hover:bg-red-700 hover:shadow-md"
            title={t("chat:input.stop")}
          >
            <Square className="h-5 w-5 fill-current" />
          </button>
        ) : (
          <button
            data-testid="chat-send"
            onClick={onSendMessage}
            disabled={!message.trim() || isPending}
            className="bg-gradient-to-r from-blue-500 to-blue-600 text-white px-5 py-3 rounded-xl hover:from-blue-600 hover:to-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm hover:shadow-md"
            title={t("chat:input.sendTooltip")}
          >
            <Send className="h-5 w-5" />
          </button>
        )}
      </div>
    </div>
  );
};
