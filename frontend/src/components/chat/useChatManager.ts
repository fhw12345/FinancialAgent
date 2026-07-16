/**
 * useChatManager Hook
 *
 * This hook manages the state of the chat messages. It provides a way
 * to add new messages to the chat history and initializes the chat
 * with a welcome message.
 */

import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import type { ChatMessage } from "../../types/api";

export const useChatManager = () => {
  const { t, i18n } = useTranslation("chat");

  const createWelcomeMessage = useCallback(
    (): ChatMessage => ({
      role: "assistant",
      content: `${t("welcome.title")}

${t("welcome.firstTime")}
${t("welcome.firstTimeHint")}

${t("welcome.agentMode")}
${t("welcome.assistantMode")}
${t("welcome.deepMode")}

💡 ${t("welcome.proTip")}`,
      timestamp: new Date().toISOString(),
    }),
    [t],
  );

  const [messages, setMessages] = useState<ChatMessage[]>(() => [
    createWelcomeMessage(),
  ]);
  const [chatId, setChatId] = useState<string | null>(null);

  // Update welcome message when language changes (only if it's the only message)
  useEffect(() => {
    setMessages((prev) => {
      // Only update if there's just the welcome message (no chat history)
      if (prev.length === 1 && prev[0].role === "assistant") {
        return [createWelcomeMessage()];
      }
      return prev;
    });
  }, [i18n.language, createWelcomeMessage]);

  return { messages, setMessages, chatId, setChatId };
};
